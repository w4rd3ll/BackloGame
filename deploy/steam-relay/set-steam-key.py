#!/usr/bin/python3
"""Run interactively as root; never echo or log the API key."""
import getpass
import os
from pathlib import Path
import re
import subprocess
import tempfile

if os.geteuid()!=0:raise SystemExit('Run as root')
key=getpass.getpass('Steam Web API key (hidden): ').strip()
if not re.fullmatch('[a-fA-F0-9]{32}',key):raise SystemExit('Invalid key format; nothing changed')
folder=Path('/etc/backlogame')
fd,name=tempfile.mkstemp(dir=folder)
try:
    with os.fdopen(fd,'w') as file:file.write(key+'\n')
    os.chmod(name,0o600)
    os.replace(name,folder/'steam-api-key')
finally:
    Path(name).unlink(missing_ok=True)
subprocess.run(['systemctl','restart','backlogame-steam.service'],check=True)
print('Key installed. Relay restarted.')
