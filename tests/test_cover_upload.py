import io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import server,steamgriddb
class CoverUploadTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory();self.root=Path(self.work.name)
        self.patches=[patch.object(server,'DATA',self.root),patch.object(server,'DB',self.root/'library.sqlite3'),patch.object(server,'TRASH',{})]
        for p in self.patches:p.start()
        server.init_db();self.game=server.save_game({'title':'Portal','notes':'Keep notes','description':'Keep description','status':'Играю','series':'Portal'})
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.work.cleanup()
    def image(self,format='PNG',color='red'):
        output=io.BytesIO();Image.new('RGB',(16,24),color).save(output,format=format);return output.getvalue()
    def test_formats_and_round_trip_without_network(self):
        for fmt,ext in [('PNG','png'),('JPEG','jpg'),('GIF','gif'),('WEBP','webp')]:
            raw=self.image(fmt)
            with patch.object(server.urllib.request,'urlopen',side_effect=AssertionError('No network')):
                game=server.upload_cover(self.game['id'],'portrait',raw)['game']
                edited=server.save_game({'title':game['title'],'notes':'Keep notes','custom_covers':game['custom_covers']},game['id'])
            cover=edited['custom_covers']['portrait'];self.assertEqual(cover['url'],cover['local']);self.assertTrue(cover['local'].endswith('.'+ext));self.assertEqual((self.root/cover['local'].lstrip('/')).read_bytes(),raw)
            self.assertEqual(game['description'],'Keep description');self.assertEqual(game['status'],'Играю')
    def test_replace_shared_orientation_backup_reset(self):
        raw=self.image();portrait=server.upload_cover(self.game['id'],'portrait',raw)['game'];old=portrait['custom_covers']['portrait']['local']
        server.upload_cover(self.game['id'],'landscape',raw)
        updated=server.upload_cover(self.game['id'],'portrait',self.image(color='blue'))['game']
        self.assertTrue((self.root/old.lstrip('/')).exists(),'Other orientation still uses file')
        self.assertNotEqual(updated['custom_covers']['portrait']['local'],old)
        replaced=server.upload_cover(self.game['id'],'landscape',self.image(color='green'))['game']
        self.assertFalse((self.root/old.lstrip('/')).exists(),'Unreferenced old cover removed')
        name=server.create_backup()
        with zipfile.ZipFile(self.root/'backups'/name) as archive:
            for cover in replaced['custom_covers'].values():self.assertEqual(archive.read(cover['local'].lstrip('/')),(self.root/cover['local'].lstrip('/')).read_bytes())
        reset=steamgriddb.reset(server,{'id':self.game['id'],'orientation':'portrait'})['game'];self.assertNotIn('portrait',reset['custom_covers']);self.assertIn('landscape',reset['custom_covers'])
        server.restore_backup((self.root/'backups'/name).read_bytes());restored=server.library()[0];self.assertEqual(restored['custom_covers'],replaced['custom_covers'])
    def test_corrupt_invalid_missing_and_size_limit(self):
        before=server.library()
        for gid,orientation,raw in [(self.game['id'],'portrait',b'not image'),(self.game['id'],'bad',self.image()),(999,'portrait',self.image()),(self.game['id'],'portrait',b'')]:
            with self.assertRaises(ValueError):server.upload_cover(gid,orientation,raw)
        with patch.object(server,'settings',return_value={'cover_max_mb':12}):
            with self.assertRaisesRegex(ValueError,'12'):server.upload_cover(self.game['id'],'portrait',b'x'*(12*1024*1024+1))
        self.assertEqual(server.library(),before)
    def test_binary_http_upload_and_auth(self):
        import threading,urllib.request,urllib.error
        http=server.LocalServer(('127.0.0.1',0),server.Handler)
        worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
        url=f'http://127.0.0.1:{http.server_port}/api/covers/upload?id={self.game['id']}&orientation=landscape'
        raw=self.image()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/cover-upload.js') as response:self.assertIn(b'openCoverUpload',response.read())
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(url,data=raw,headers={'Content-Type':'application/octet-stream'}))
            self.assertEqual(error.exception.code,403)
            error.exception.close()
            req=urllib.request.Request(url,data=raw,headers={'Content-Type':'application/octet-stream','X-Library-Token':server.TOKEN})
            with urllib.request.urlopen(req) as response:result=json.load(response)
            self.assertIn('landscape',result['game']['custom_covers'])
            local=result['game']['custom_covers']['landscape']['local']
            with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}'+local) as response:self.assertEqual(response.read(),raw)
        finally:http.shutdown();http.server_close();worker.join()
    def test_animated_gif_bytes_preserved(self):
        output=io.BytesIO();Image.new('RGB',(16,24),'red').save(output,format='GIF',save_all=True,append_images=[Image.new('RGB',(16,24),'blue')],duration=100,loop=0)
        raw=output.getvalue();game=server.upload_cover(self.game['id'],'portrait',raw)['game'];local=self.root/game['custom_covers']['portrait']['local'].lstrip('/')
        self.assertEqual(local.read_bytes(),raw)
        with Image.open(local) as image:self.assertEqual(image.n_frames,2)
if __name__=='__main__':unittest.main()
