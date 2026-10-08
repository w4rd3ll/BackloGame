"""Public IGDB catalog relay; Twitch credentials never enter desktop storage."""
import re

RELAY='https://backlogame-steam.w4rdell.workers.dev/v1/igdb'


def search(store,query):
    query=query.strip()
    link=re.fullmatch(r'https://(?:www\.)?igdb\.com/games/([a-z0-9-]+)/?',query)
    if link:query=link[1].replace('-',' ')
    result=store.remote(store.api_url(RELAY+'/search',q=query[:150]))
    rows=result.get('items')
    if not isinstance(rows,list):raise ValueError('IGDB не вернул сведения')
    return rows


def details(store,source):
    if not re.fullmatch(r'igdb:[1-9]\d{0,9}',source):raise ValueError('Некорректный идентификатор IGDB')
    result=store.remote(store.api_url(RELAY+'/game',id=source.split(':')[1]))
    game=result.get('game')
    if not isinstance(game,dict) or game.get('source_id')!=source:raise ValueError('IGDB не вернул сведения об этой игре')
    return game
