"""Public IGDB catalog relay; Twitch credentials never enter desktop storage."""
import json
import os
from pathlib import Path
import re
import subprocess

RELAY='https://backlogame-steam.w4rdell.workers.dev/v1/igdb'


def windows_json(url):
    """Use the Windows TLS stack for the public catalog relay when available."""
    if not url.startswith((RELAY+'/search?',RELAY+'/game?')):
        raise ValueError('Invalid IGDB relay URL')
    curl=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'/'curl.exe'
    try:
        result=subprocess.run(
            [str(curl),'--disable','--proto','=https','--silent','--fail',
             '--connect-timeout','10','--max-time','20','--max-filesize','131072',
             '--header','Accept: application/json',url],
            stdin=subprocess.DEVNULL,capture_output=True,timeout=22,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Не удалось подключиться к IGDB') from exc
    if result.returncode==22:
        raise ValueError('IGDB сейчас недоступен')
    if result.returncode:
        raise ValueError('Не удалось подключиться к IGDB')
    if len(result.stdout)>131072:
        raise ValueError('IGDB не вернул сведения')
    try:
        body=json.loads(result.stdout)
    except (UnicodeError,ValueError) as exc:
        raise ValueError('IGDB не вернул сведения') from exc
    if not isinstance(body,dict):raise ValueError('IGDB не вернул сведения')
    return body



def search(store,query):
    query=query.strip()
    link=re.fullmatch(r'https://(?:www\.)?igdb\.com/games/([a-z0-9-]+)/?',query)
    if link:query=link[1].replace('-',' ')
    result=store.remote(store.api_url(RELAY+'/search',q=query[:150]),windows_tls=True)
    rows=result.get('items')
    if not isinstance(rows,list):raise ValueError('IGDB не вернул сведения')
    return rows


def details(store,source):
    if not re.fullmatch(r'igdb:[1-9]\d{0,9}',source):raise ValueError('Некорректный идентификатор IGDB')
    result=store.remote(store.api_url(RELAY+'/game',id=source.split(':')[1]),windows_tls=True)
    game=result.get('game')
    if not isinstance(game,dict) or game.get('source_id')!=source:raise ValueError('IGDB не вернул сведения об этой игре')
    return game
