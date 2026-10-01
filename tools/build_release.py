"""Build the clean portable release; never read or overwrite the personal copy."""
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT.parent / 'BackloGame-Release'


def main():
    database = RELEASE / 'data' / 'library.sqlite3'
    if database.exists():
        with sqlite3.connect(database) as db:
            if db.execute('SELECT COUNT(*) FROM games').fetchone()[0]:
                raise SystemExit('Release contains games. Move its data elsewhere before building a public release.')
    subprocess.run([sys.executable,str(ROOT/'tools'/'audit_source.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'tools'/'collect_licenses.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', str(ROOT / 'BackloGame.spec')], cwd=ROOT, check=True)
    bundle = ROOT / 'dist' / 'BackloGame'
    if not (bundle / 'BackloGame.exe').is_file():
        raise SystemExit('Missing executable')
    RELEASE.mkdir(exist_ok=True)
    for item in bundle.iterdir():
        target = RELEASE / item.name
        if item.is_dir():
            # Drop stale packaged files, restricted to this exact release directory.
            if target.exists():
                if target.resolve().parent != RELEASE.resolve():
                    raise SystemExit('Unsafe release path')
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    (RELEASE / 'data').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'docs' / 'PORTABLE.txt', RELEASE / 'README.txt')
    shutil.copy2(ROOT / 'docs' / 'THIRD_PARTY.md', RELEASE / 'THIRD_PARTY.md')
    shutil.copytree(ROOT / 'docs' / 'licenses', RELEASE / 'licenses', dirs_exist_ok=True)
    print('Ready:', RELEASE / 'BackloGame.exe')


if __name__ == '__main__':
    main()
