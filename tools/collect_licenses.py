"""Collect bundled Python dependencies' own license notices for distribution."""
import importlib.metadata
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'docs' / 'licenses'
out.mkdir(parents=True, exist_ok=True)
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.is_file():
    shutil.copy2(python_license, out / 'Python-LICENSE.txt')
for package in ('pywebview','pythonnet','clr_loader','bottle','proxy_tools','typing_extensions','cffi','pycparser'):
    dist = importlib.metadata.distribution(package)
    for path in dist.files or []:
        if any(word in Path(str(path)).name.lower() for word in ('license','copying','notice')):
            source = Path(dist.locate_file(path))
            if source.is_file() and source.stat().st_size < 500000:
                shutil.copy2(source, out / (package + '-' + source.name))
