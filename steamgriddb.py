"""SteamGridDB artwork; credentials stay outside library exports and backups."""
import json
import re
import secrets
import time
import urllib.request
import urllib.parse
import urllib.error

GALLERIES={}


def key_path(store):
    return store.DATA/'.steamgriddb-key'


def configured(store):
    return key_path(store).is_file() and bool(key_path(store).read_text(encoding='utf-8').strip())


def set_key(store,data):
    value=data.get('key')
    if not isinstance(value,str) or value.strip() and not re.fullmatch(r'[a-zA-Z0-9_-]{16,128}',value.strip()):raise ValueError('Некорректный ключ SteamGridDB')
    path=key_path(store)
    if value.strip():
        path.parent.mkdir(parents=True,exist_ok=True)
        pending=path.with_suffix('.tmp')
        pending.write_text(value.strip(),encoding='utf-8')
        pending.replace(path)
    else:path.unlink(missing_ok=True)
    return {'configured':configured(store)}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def request(store,path,**query):
    if not configured(store):raise ValueError('Добавь ключ SteamGridDB в настройках источников')
    url='https://www.steamgriddb.com/api/v2/'+path
    if query:url+='?'+urllib.parse.urlencode(query)
    key=key_path(store).read_text(encoding='utf-8').strip()
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+key,'User-Agent':'BackloGame','Accept':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=25) as response:
            raw=response.read(5_000_001)
        if len(raw)>5_000_000:raise ValueError('SteamGridDB: ответ слишком большой')
        result=json.loads(raw)
        if not result.get('success'):raise ValueError('SteamGridDB не вернул результаты')
        return result.get('data',[])
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code in (401,403):raise ValueError('SteamGridDB: проверь API-ключ') from None
        if exc.code==429:raise ValueError('SteamGridDB: слишком много запросов, попробуй позже') from None
        if exc.code==404:return []
        raise ValueError('SteamGridDB: HTTP '+str(exc.code)) from None
    except (OSError,json.JSONDecodeError):raise ValueError('SteamGridDB сейчас недоступен') from None


def search(store,data):
    query=data.get('query','')
    if not isinstance(query,str) or not query.strip():raise ValueError('Укажите название игры')
    rows=request(store,'search/autocomplete/'+urllib.parse.quote(query.strip()[:150],safe=''))
    return {'items':[{'id':row['id'],'title':row['name']} for row in rows if type(row.get('id')) is int and isinstance(row.get('name'),str)]}


def grids(store,data):
    orientation=data.get('orientation')
    if orientation not in ('portrait','landscape'):raise ValueError('Invalid artwork orientation')
    kind=data.get('kind','game');gid=data.get('game')
    if kind not in ('game','steam') or type(gid)!=int or gid<=0:raise ValueError('Invalid artwork game')
    page=data.get('page',0)
    if type(page)!=int or not 0<=page<=100:raise ValueError('Invalid artwork page')
    rows=request(store,f'grids/{kind}/{gid}',dimensions='600x900' if orientation=='portrait' else '460x215,920x430',types='static',page=page)
    items=[]
    for row in rows:
        if type(row.get('id')) is not int or row['id']<=0:continue
        url=urllib.parse.urlsplit(row.get('url',''))
        if url.scheme!='https' or not (url.hostname or '').endswith('.steamgriddb.com'):continue
        width,height=row.get('width',0),row.get('height',0)
        if not isinstance(width,int) or not isinstance(height,int) or not width or not height or (width<height)!=(orientation=='portrait'):continue
        if row.get('mime') not in (None,'image/jpeg','image/png','image/webp'):continue
        thumb=urllib.parse.urlsplit(row.get('thumb') or row['url'])
        preview=row.get('thumb') if thumb.scheme=='https' and (thumb.hostname or '').endswith('.steamgriddb.com') else row['url']
        items.append({'id':row['id'],'url':row['url'],'thumb':preview,'width':width,'height':height,'author':str((row.get('author') or {}).get('name') or '')[:300],'score':row.get('score',0)})
    for token,(until,*_) in list(GALLERIES.items()):
        if until<time.monotonic():GALLERIES.pop(token,None)
    if len(GALLERIES)>=100:GALLERIES.pop(next(iter(GALLERIES)))
    token=secrets.token_urlsafe(24)
    GALLERIES[token]=(time.monotonic()+1800,str(store.DB),orientation,items)
    return {'items':items,'gallery':token,'more':len(rows)>=50}


def game(store,gid):
    if type(gid)!=int:raise ValueError('Invalid game ID')
    found=next((g for g in store.library() if g['id']==gid),None)
    if not found:raise ValueError('Игра уже удалена')
    return found


def apply(store,data):
    old=game(store,data.get('id'));gallery=GALLERIES.get(data.get('gallery'))
    if not gallery or gallery[0]<time.monotonic() or gallery[1]!=str(store.DB):raise ValueError('Список обложек устарел. Загрузи его снова.')
    row=next((row for row in gallery[3] if row['id']==data.get('asset')),None)
    if not row:raise ValueError('Выбери обложку из списка')
    local=store.archive_cover(row['url'])
    covers=dict(old.get('custom_covers',{}));covers[gallery[2]]={'url':row['url'],'local':local,'asset':row['id'],'author':row['author']}
    with store.MUTATION_LOCK:
        if game(store,old['id'])!=old:raise ValueError('The game changed. Try again.')
        store.create_backup(automatic=True)
        saved=store.save_game({'title':old['title'],'custom_covers':covers,**({'thumbnail_crop':None} if gallery[2]=='landscape' else {})},old['id'])
    return {'game':saved}


def reset(store,data):
    old=game(store,data.get('id'));orientation=data.get('orientation')
    if orientation not in ('portrait','landscape'):raise ValueError('Invalid artwork orientation')
    covers=dict(old.get('custom_covers',{}));covers.pop(orientation,None)
    store.create_backup(automatic=True)
    return {'game':store.save_game({'title':old['title'],'custom_covers':covers},old['id'])}
