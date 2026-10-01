"""Check first-party release inputs for obsolete modules and hard-coded credentials."""
import ast
import ipaddress
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','data','backups','build','dist','__pycache__'}
INPUTS=[path for path in ROOT.rglob('*') if path.is_file() and not EXCLUDED.intersection(path.relative_to(ROOT).parts) and path.relative_to(ROOT).parts[:2]!=('tests','output')]
OBSOLETE=('credentials.py','media_sources.py','media.js','instructions.html')
credential=re.compile(r'''(?ix)(?:api[_-]?key|client[_-]?secret|access[_-]?token|password)\s*[:=]\s*["'][a-z0-9_\-]{20,}["']''')
failures=[]
for name in OBSOLETE:
    if (ROOT/name).exists() or (ROOT/'static'/name).exists():failures.append('Obsolete module: '+name)
for path in INPUTS:
    if path.suffix not in ('.py','.js','.mjs','.cjs','.html','.css','.md','.json','.yml','.yaml','.sh','.cmd','.ps1','.conf','.service','.timer','.spec','.txt'):continue
    text=path.read_text(encoding='utf-8')
    for address in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])',text):
        try: public=ipaddress.ip_address(address).is_global
        except ValueError: continue
        if public: failures.append('Public server IP literal in '+str(path.relative_to(ROOT)))
    if credential.search(text):failures.append('Credential-shaped literal in '+path.name)
    if path.name not in ('audit_source.py','test_library.py') and re.search(r'kinopoisk|fanart|thetvdb|api\.themoviedb|openlibrary|comicvine',text,re.I):failures.append('Removed media provider in '+path.name)
    if path.suffix=='.py':ast.parse(text,filename=path.name)
if failures:raise SystemExit('\n'.join(failures))
print('Release source audit: no obsolete media providers, hard-coded credentials or public server IPs found.')
