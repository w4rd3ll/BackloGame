"""GitHub release checks and bounded, verified portable updates."""
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from version import VERSION

REPOSITORY = 'w4rd3ll/BackloGame'
RELEASE_API = 'https://api.github.com/repos/'+REPOSITORY+'/releases/latest'
RELEASES_URL = 'https://github.com/'+REPOSITORY+'/releases'
MAX_PACKAGE = 300_000_000
INPUTS = ('BackloGame.exe','_internal','licenses','README.txt','THIRD_PARTY.md')


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value))
    if not match: raise ValueError('Unsupported release version')
    return tuple(int(part) for part in match.groups())


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        parts=urllib.parse.urlsplit(url)
        if parts.scheme!='https' or parts.hostname not in ('github.com','api.github.com','release-assets.githubusercontent.com','objects.githubusercontent.com') or parts.username or parts.password:
            raise ValueError('Unsafe update redirect')
        return super().redirect_request(req,fp,code,msg,headers,url)


def open_remote(url):
    request=urllib.request.Request(url,headers={'User-Agent':'BackloGame/'+VERSION,'Accept':'application/vnd.github+json'})
    return urllib.request.build_opener(GitHubRedirect()).open(request,timeout=30)


def latest_release():
    try:
        with open_remote(RELEASE_API) as response:
            raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError('Release metadata too large')
        release=json.loads(raw)
    except (OSError,ValueError) as error:
        if isinstance(error,urllib.error.HTTPError) and error.code==404:return None
        raise ValueError('Could not check updates. Check your connection and try again.') from None
    tag=release.get('tag_name','')
    version_tuple(tag)
    if release.get('draft') or release.get('prerelease'):raise ValueError('Only stable releases are supported')
    name='BackloGame-'+tag.lstrip('v')+'-windows-x64-portable.zip'
    asset=next((item for item in release.get('assets',[]) if item.get('name')==name),None)
    digest=(asset or {}).get('digest') or ''
    url=(asset or {}).get('browser_download_url') or ''
    expected='https://github.com/'+REPOSITORY+'/releases/download/'+tag+'/'+name
    if asset and (url!=expected or not re.fullmatch(r'sha256:[a-f0-9]{64}',digest) or not isinstance(asset.get('size'),int) or not 0<asset['size']<=MAX_PACKAGE):
        asset=None
    return {'version':tag.lstrip('v'),'notes':str(release.get('body') or '')[:30000],
            'url':RELEASES_URL+'/tag/'+tag,'asset':asset}


def unpack_verified(archive, destination):
    """No data, links, traversal, case aliases or unknown top-level entries."""
    with zipfile.ZipFile(archive) as package:
        total=0;seen=set()
        for entry in package.infolist():
            path=PurePosixPath(entry.filename)
            if '\\' in entry.filename or ':' in entry.filename or path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='BackloGame':
                raise ValueError('Unsafe update package')
            if len(path.parts)==1:
                if not entry.is_dir():raise ValueError('Invalid package root')
                continue
            if path.parts[1] not in INPUTS or stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Unsafe update package')
            if any(part.endswith((' ','.')) or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part) for part in path.parts):raise ValueError('Unsafe Windows path')
            key=str(path).casefold()
            if key in seen:raise ValueError('Duplicate update path')
            seen.add(key);total+=entry.file_size
            if total>1_000_000_000 or len(seen)>20000:raise ValueError('Update package too large')
        package.extractall(destination)
    root=destination/'BackloGame'
    if not (root/'BackloGame.exe').is_file() or not (root/'_internal').is_dir():raise ValueError('Incomplete update package')
    return root


class UpdateManager:
    def __init__(self, data):
        self.data=Path(data);self.lock=threading.RLock();self.release=None;self.stage=None
        self.state={'current':VERSION,'state':'idle','latest':'','available':False,'notes':'','error':'','downloaded':0,'total':0,'url':RELEASES_URL,'can_install':False}
        self.checked=0
        try:
            result=json.loads((self.data/'update-result.json').read_text(encoding='utf-8-sig'))
            if result.get('status')=='failed':self.state['previous_failed']=True
        except (OSError,ValueError,AttributeError):pass

    def status(self):
        with self.lock:return dict(self.state)

    def start(self, operation):
        with self.lock:
            if self.state['state'] in ('checking','downloading'):return self.status()
            if operation=='check' and time.monotonic()-self.checked<60:return self.status()
            if operation=='download' and (not self.release or not self.state['available'] or not self.release['asset']):raise ValueError('No verified update package is available')
            self.state.update(state='checking' if operation=='check' else 'downloading',error='')
        def work():
            try:
                if operation=='check':
                    release=latest_release()
                    with self.lock:
                        self.release=release;self.checked=time.monotonic()
                        self.state.update(state='checked',latest=release['version'] if release else '',available=bool(release and version_tuple(release['version'])>version_tuple(VERSION)),notes=release['notes'] if release else '',url=release['url'] if release else RELEASES_URL,verified=bool(release and release['asset']))
                else:self.download()
            except Exception as error:
                with self.lock:self.state.update(state='error',error=str(error)[:300] if isinstance(error,ValueError) else 'Could not download the update. Try again.')
        threading.Thread(target=work,daemon=True).start()
        return self.status()

    def download(self):
        cache=self.data/'updates';cache.mkdir(exist_ok=True)
        stage=cache/'staging'
        if not cache.resolve().is_relative_to(self.data.resolve()) or not stage.resolve().is_relative_to(cache.resolve()):raise ValueError('Unsafe update staging path')
        if stage.exists():shutil.rmtree(stage)
        stage.mkdir();archive=stage/'package.zip';asset=self.release['asset'];hasher=hashlib.sha256();count=0
        try:
            with open_remote(asset['browser_download_url']) as response,archive.open('wb') as output:
                while chunk:=response.read(131072):
                    count+=len(chunk)
                    if count>asset['size'] or count>MAX_PACKAGE:raise ValueError('Update size does not match')
                    output.write(chunk);hasher.update(chunk)
                    with self.lock:self.state.update(downloaded=count,total=asset['size'])
            if count!=asset['size'] or 'sha256:'+hasher.hexdigest()!=asset['digest']:raise ValueError('Update checksum does not match')
            self.stage=unpack_verified(archive,stage)
            archive.unlink()
            with self.lock:self.state.update(state='ready',can_install=bool(getattr(sys,'frozen',False) and sys.platform=='win32'))
        except Exception:
            shutil.rmtree(stage);self.stage=None;raise

    def launch_install(self):
        if self.state['state']!='ready' or not self.state['can_install'] or not self.stage:raise ValueError('Automatic installation is available in the Windows portable app')
        root=Path(sys.executable).resolve().parent
        with tempfile.NamedTemporaryFile(dir=root,prefix='.update-write-check-'):pass
        script=Path(__file__).resolve().parent/'update-portable.ps1'
        if not script.is_file():raise ValueError('Update helper is missing')
        config=self.stage.parent/'install.json'
        config.write_text(json.dumps({'root':str(root),'stage':str(self.stage.resolve()),'pid':os.getpid(),'data':str(self.data.resolve())}),encoding='utf-8')
        # Copy the helper outside _internal before the old bundle is moved.
        helper=config.parent/'apply.ps1';shutil.copy2(script,helper)
        subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper),'-Config',str(config)],creationflags=subprocess.CREATE_NO_WINDOW)
        with self.lock:self.state.update(state='installing',can_install=False)
