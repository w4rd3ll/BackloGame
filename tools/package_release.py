"""Package only public binaries and notices; never include any data directory."""
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT.parent / 'BackloGame-Release'
sys.path.insert(0,str(ROOT))
from version import VERSION


def main():
    subprocess.run([sys.executable, str(ROOT/'tools/audit_source.py')], check=True)
    if not (RELEASE/'BackloGame.exe').is_file():
        raise SystemExit('Build the Windows release first.')
    inputs = ['BackloGame.exe', '_internal', 'licenses', 'README.txt', 'THIRD_PARTY.md']
    files = []
    for name in inputs:
        entry = RELEASE/name
        if not entry.exists():
            raise SystemExit('Missing release input: '+name)
        for path in ([entry] if entry.is_file() else sorted(entry.rglob('*'))):
            if path.is_symlink() or not path.resolve().is_relative_to(RELEASE.resolve()):
                raise SystemExit('Unsafe package input: '+str(path))
            if path.is_file():
                files.append(path)
    archive = ROOT/'dist'/f'BackloGame-{VERSION}-windows-x64-portable.zip'
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in files:
            package.write(path, 'BackloGame/'+path.relative_to(RELEASE).as_posix())
    with zipfile.ZipFile(archive) as package:
        assert not any('/data/' in path or '/WebView2/' in path for path in package.namelist())
        assert package.testzip() is None
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n', encoding='ascii')
    print(archive)
    print('SHA256:', digest)


if __name__ == '__main__':
    main()
