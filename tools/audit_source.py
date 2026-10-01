"""Check first-party release inputs for obsolete modules and hard-coded credentials."""
import ast
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INPUTS=[ROOT/'server.py',ROOT/'desktop.py',ROOT/'desktop_platform.py',ROOT/'desktop_close.py',ROOT/'storage.py',*sorted((ROOT/'static').glob('*'))]
OBSOLETE=('credentials.py','media_sources.py','media.js','instructions.html')
credential=re.compile(r'''(?ix)(?:api[_-]?key|client[_-]?secret|access[_-]?token|password)\s*[:=]\s*["'][a-z0-9_\-]{20,}["']''')
failures=[]
for name in OBSOLETE:
    if (ROOT/name).exists() or (ROOT/'static'/name).exists():failures.append('Obsolete module: '+name)
for path in INPUTS:
    if path.suffix not in ('.py','.js','.html','.css'):continue
    text=path.read_text(encoding='utf-8')
    if credential.search(text):failures.append('Credential-shaped literal in '+path.name)
    if re.search(r'kinopoisk|fanart|thetvdb|api\.themoviedb|openlibrary|comicvine',text,re.I):failures.append('Removed media provider in '+path.name)
    if path.suffix=='.py':ast.parse(text,filename=path.name)
if failures:raise SystemExit('\n'.join(failures))
print('Release source audit: no obsolete media providers or hard-coded credentials found.')
