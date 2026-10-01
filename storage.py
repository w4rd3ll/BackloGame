"""Persistent user data, independent from the application bundle."""
from pathlib import Path
import os
import sys


def user_data_directory():
    override=os.environ.get('BACKLOGAME_DATA_DIR') or os.environ.get('MY_GAMES_DATA_DIR')
    if override:return Path(override).expanduser().resolve()
    base=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    return base/'data'

