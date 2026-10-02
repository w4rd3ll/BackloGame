import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import updater
import desktop_platform


class UpdaterTests(unittest.TestCase):
    def test_semver_and_no_downgrade(self):
        self.assertGreater(updater.version_tuple('v0.10.0'),updater.version_tuple('0.9.1'))
        with self.assertRaises(ValueError):updater.version_tuple('v0.2.0-beta')

    def test_dll_error_has_unblock_help(self):
        help=desktop_platform.startup_help('win32',RuntimeError('Failed to resolve Python.Runtime.Loader.Initialize'))
        self.assertIn('Unblock',help)
        self.assertNotIn('WebView2',help)

    def test_offline_check_is_recoverable(self):
        with patch.object(updater,'open_remote',side_effect=OSError('offline')):
            with self.assertRaisesRegex(ValueError,'Could not check updates'):
                updater.latest_release()

    def test_interrupted_download_preserves_existing_data(self):
        class Interrupted(io.BytesIO):
            def read(self,size=-1):
                raise OSError('interrupted')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'library.sqlite3').write_bytes(b'existing library')
            manager=updater.UpdateManager(root)
            manager.release={'asset':{'size':100,'digest':'sha256:'+'0'*64,'browser_download_url':'https://github.com/example'}}
            with patch.object(updater,'open_remote',return_value=Interrupted()),self.assertRaises(OSError):
                manager.download()
            self.assertEqual((root/'library.sqlite3').read_bytes(),b'existing library')
            self.assertFalse((root/'updates/staging').exists())

    def make_zip(self,path,files):
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,body in files.items():archive.writestr(name,body)

    def test_rejects_data_traversal_and_windows_aliases(self):
        for bad in ['../outside','BackloGame/data/library.sqlite3','BackloGame/_internal/CON.txt','BackloGame/_internal/bad:stream']:
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);self.make_zip(root/'test.zip',{bad:b'test'})
                with self.assertRaises(ValueError):updater.unpack_verified(root/'test.zip',root/'out')
                self.assertFalse((root/'outside').exists())

    def test_download_checks_digest_and_cleans_failed_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.make_zip(root/'fixture.zip',{'BackloGame/BackloGame.exe':b'fixture','BackloGame/_internal/test.txt':b'runtime'})
            raw=(root/'fixture.zip').read_bytes();manager=updater.UpdateManager(root)
            manager.release={'asset':{'size':len(raw),'digest':'sha256:'+hashlib.sha256(raw).hexdigest(),'browser_download_url':'https://github.com/example'}}
            with patch.object(updater,'open_remote',return_value=io.BytesIO(raw)):manager.download()
            self.assertEqual(manager.state['state'],'ready')
            manager.release['asset']['digest']='sha256:'+'0'*64
            with patch.object(updater,'open_remote',return_value=io.BytesIO(raw)),self.assertRaises(ValueError):manager.download()
            self.assertFalse((root/'updates/staging').exists())

    @unittest.skipUnless(sys.platform=='win32','Windows update helper')
    def test_real_powershell_replacement_preserves_data_and_one_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);app=base/'app';stage=base/'stage';data=app/'data'
            for root in [app,stage]:
                (root/'_internal').mkdir(parents=True)
                (root/'BackloGame.exe').write_bytes(b'old' if root==app else b'new')
                (root/'_internal/runtime.txt').write_text('old' if root==app else 'new')
            data.mkdir();(data/'library.sqlite3').write_bytes(b'user-data')
            (app/'.update-rollback').mkdir();(app/'.update-rollback/previous.txt').write_text('stale')
            config=base/'install.json';config.write_text(json.dumps({'root':str(app),'stage':str(stage),'pid':2147483647,'data':str(data)}))
            subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(updater.__file__).with_name('update-portable.ps1')),'-Config',str(config),'-NoRestart'],check=True,capture_output=True)
            self.assertEqual((app/'BackloGame.exe').read_bytes(),b'new')
            self.assertEqual((app/'.update-rollback/BackloGame.exe').read_bytes(),b'old')
            self.assertFalse((app/'.update-rollback/previous.txt').exists())
            self.assertEqual((data/'library.sqlite3').read_bytes(),b'user-data')

    @unittest.skipUnless(sys.platform=='win32','Windows update helper')
    def test_locked_runtime_rolls_back_replaced_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);app=base/'app';stage=base/'stage';data=app/'data'
            for root in [app,stage]:
                (root/'_internal').mkdir(parents=True)
                (root/'BackloGame.exe').write_bytes(b'old' if root==app else b'new')
                (root/'_internal/runtime.txt').write_text('old' if root==app else 'new')
            data.mkdir();config=base/'install.json'
            config.write_text(json.dumps({'root':str(app),'stage':str(stage),'pid':2147483647,'data':str(data)}))
            with (app/'_internal/runtime.txt').open('rb'):
                subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(updater.__file__).with_name('update-portable.ps1')),'-Config',str(config),'-NoRestart'],check=True,capture_output=True)
            self.assertEqual((app/'BackloGame.exe').read_bytes(),b'old')
            self.assertEqual((app/'_internal/runtime.txt').read_text(),'old')
            self.assertEqual(json.loads((data/'update-result.json').read_text(encoding='utf-8-sig'))['status'],'failed')

    @unittest.skipUnless(sys.platform=='win32','Windows update helper')
    def test_locked_file_never_partially_moves_runtime_even_on_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);app=base/'app';stage=base/'stage';data=app/'data'
            for root in [app,stage]:
                (root/'_internal/nested').mkdir(parents=True)
                (root/'BackloGame.exe').write_bytes(b'old' if root==app else b'new')
                for i in range(50):
                    (root/f'_internal/nested/{i:03}.dll').write_bytes((b'old' if root==app else b'new')+str(i).encode())
            data.mkdir();(data/'library.sqlite3').write_bytes(b'library')
            before={str(p.relative_to(app)):p.read_bytes() for p in app.rglob('*') if p.is_file()}
            config=base/'install.json'
            config.write_text(json.dumps({'root':str(app),'stage':str(stage),'pid':2147483647,'data':str(data)}))
            with (app/'_internal/nested/049.dll').open('rb'):
                for _ in range(2):
                    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(updater.__file__).with_name('update-portable.ps1')),'-Config',str(config),'-NoRestart','-WaitSeconds','0'],check=True,capture_output=True)
                    for relative,content in before.items():
                        self.assertEqual((app/relative).read_bytes(),content,relative)
                    self.assertEqual(json.loads((data/'update-result.json').read_text(encoding='utf-8-sig'))['status'],'failed')

    @unittest.skipUnless(sys.platform=='win32','Windows update helper')
    def test_other_instance_blocks_update_before_any_file_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);app=base/'app';stage=base/'stage';data=app/'data'
            for root in [app,stage]:(root/'_internal').mkdir(parents=True)
            data.mkdir();(app/'_internal/runtime.dll').write_bytes(b'original')
            (stage/'BackloGame.exe').write_bytes(b'new');(stage/'_internal/runtime.dll').write_bytes(b'new')
            (app/'.update-rollback').mkdir();(app/'.update-rollback/keep.txt').write_bytes(b'previous rollback')
            build=base/'build.ps1'
            build.write_text("Add-Type -TypeDefinition 'public class UpdateFixture {public static void Main(){System.Threading.Thread.Sleep(60000);}}' -OutputAssembly '"+str(app/'BackloGame.exe').replace("'","''")+"' -OutputType ConsoleApplication")
            subprocess.run(['powershell.exe','-NoProfile','-File',str(build)],check=True,capture_output=True)
            exe=(app/'BackloGame.exe').read_bytes()
            process=subprocess.Popen([str(app/'BackloGame.exe')],creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                config=base/'install.json';config.write_text(json.dumps({'root':str(app),'stage':str(stage),'pid':2147483647,'data':str(data)}))
                subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(updater.__file__).with_name('update-portable.ps1')),'-Config',str(config),'-WaitSeconds','0'],check=True,capture_output=True)
                self.assertEqual((app/'BackloGame.exe').read_bytes(),exe)
                self.assertEqual((app/'_internal/runtime.dll').read_bytes(),b'original')
                self.assertEqual((app/'.update-rollback/keep.txt').read_bytes(),b'previous rollback')
                result=json.loads((data/'update-result.json').read_text(encoding='utf-8-sig'))
                self.assertEqual(result['status'],'failed');self.assertIn('Close all',result['error'])
                self.assertIsNone(process.poll())
            finally:process.terminate();process.wait(timeout=10)
