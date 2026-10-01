"""Read-only remote libraries and bounded, selectable imports into local storage."""
import csv
import hashlib
import gzip
import io
import json
import os
import re
import secrets
import threading
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

LIMIT = 10000
TTL = 1800


def request(url, body=None):
    headers = {'User-Agent': 'BackloGame/0.1', 'Accept': 'application/json,text/html,text/xml'}
    headers['Accept-Encoding'] = 'gzip'
    if body is not None:
        headers['Content-Type'] = 'application/json'
        headers['Referer'] = 'https://howlongtobeat.com/'
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read(8_000_001)
            encoding = response.headers.get('Content-Encoding', '').lower()
    except (OSError, urllib.error.URLError) as exc:
        # Do not expose request URLs: Steam keys are query parameters.
        raise ValueError('Не удалось загрузить профиль. Проверь доступность списка и подключение; для HLTB можно использовать CSV.') from None
    if len(raw) > 8_000_000:
        raise ValueError('Список слишком большой')
    if encoding == 'gzip':
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                raw = compressed.read(8_000_001)
        except (OSError, EOFError):
            raise ValueError('Источник вернул повреждённый ответ') from None
        if len(raw) > 8_000_000:
            raise ValueError('Список слишком большой')
    return raw.decode('utf-8-sig')


def profile_name(value, provider):
    value = str(value or '').strip()
    if '://' in value:
        url = urllib.parse.urlsplit(value)
        host = 'steamcommunity.com' if provider == 'steam' else 'howlongtobeat.com'
        pattern = r'/(id|profiles)/([^/]+)/?' if provider == 'steam' else r'/(user)/([^/]+)(?:/games)?/?'
        match = re.fullmatch(pattern, url.path)
        if url.scheme != 'https' or url.netloc.lower() not in (host, 'www.'+host) or not match:
            raise ValueError('Вставь ссылку на профиль Steam или HLTB')
        value = urllib.parse.unquote(match[2])
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', value):
        raise ValueError('Вставь ссылку на профиль Steam или HLTB')
    return value


def normalized(value):
    value = unicodedata.normalize('NFKC', str(value)).casefold().replace('®', '').replace('™', '')
    return ' '.join(re.findall(r'\w+', value))


def platform_key(value):
    key = normalized(value)
    if key in ('pc', 'pc steam', 'steam', 'windows', 'linux', 'mac', 'macos'):
        return 'pc'
    return key


def identity(game):
    return normalized(game['title']), platform_key(game.get('platform', ''))


def checked(value):
    return str(value or '').strip().casefold() in ('x', '1', 'true', 'yes')


def status(row):
    if checked(row.get('list_playing')): return 'Играю'
    if checked(row.get('list_comp')): return 'Пройдено'
    if checked(row.get('list_retired')): return 'Брошено'
    return 'Бэклог' if checked(row.get('list_backlog')) else 'Хочу пройти'


def hltb_game(row, csv_mode=False):
    title = str(row.get('custom_title') or row.get('game_name') or '').strip()
    platform = str(row.get('platform') or 'Пока неизвестно').strip()
    if not title or len(title) > 300 or len(platform) > 300:
        raise ValueError('Некорректная запись в списке игр')
    game_id = str(row.get('game_id') or '')
    entry_id = str(row.get('id') or '')
    # CSV contains no IDs. Title/platform matching links it to online entries.
    key = entry_id if entry_id.isdigit() else hashlib.sha256((normalized(title)+'|'+platform_key(platform)).encode()).hexdigest()[:24]
    image = str(row.get('game_image') or '')
    if image in ('.', '..') or any(c in image for c in '/\\') or any(ord(c) < 32 for c in image): image = ''
    release = str(row.get('release_world') or '')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', release) and not release.startswith('0000'):
        release = release[:4] if release[5:7]=='00' else release[:7] if release[8:]=='00' else release
        try: datetime.fromisoformat(release+('-01-01' if len(release)==4 else '-01' if len(release)==7 else ''))
        except ValueError: release = ''
    else: release = ''
    return {
        'title': title, 'platform': platform, 'status': status(row),
        'source_id': 'hltb:'+key, 'sync_provider': 'hltb', 'sync_key': key,
        'provider': 'HLTB CSV' if csv_mode else 'HowLongToBeat',
        'source_url': 'https://howlongtobeat.com/game/'+game_id if game_id.isdigit() else '',
        'image': 'https://howlongtobeat.com/games/'+urllib.parse.quote(image, safe='') if image else '',
        'notes': str(row.get('play_notes') or '')[:20000],
        'completed_at': str(row.get('date_complete') or '')[:10] if not str(row.get('date_complete') or '').startswith('0000') else '',
        'sync_added_at': str(row.get('date_added') or '')[:32],
        'sync_status': status(row),
        'hltb_game_id': game_id,
        'hltb_url': 'https://howlongtobeat.com/game/'+game_id if game_id.isdigit() else '',
        'started_at': str(row.get('date_start') or '')[:10] if not str(row.get('date_start') or '').startswith('0000') else '',
        'hltb_updated_at': str(row.get('date_updated') or '')[:32],
        'tags': 'HLTB' + (', Повторное прохождение' if checked(row.get('list_replay')) else ''),
        'release_date':release,
    }


def parse_csv(text):
    if not isinstance(text, str) or len(text) > 10_000_000:
        raise ValueError('Файл больше 10 МБ')
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff'), newline=''))
        required = {'Title', 'Platform', 'Completed', 'Playing', 'Backlog'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Это не CSV-экспорт списка игр HLTB')
        games = []
        for row in reader:
            if len(games) >= LIMIT: raise ValueError('Список слишком большой')
            if None in row: raise ValueError('Некорректная запись в списке игр')
            if not str(row.get('Title') or '').strip(): continue
            games.append(hltb_game({
                'custom_title': row['Title'], 'platform': row['Platform'],
                'list_playing': row.get('Playing'), 'list_comp': row.get('Completed'),
                'list_backlog': row.get('Backlog'), 'list_replay': row.get('Replay'),
                'list_retired': row.get('Retired'), 'play_notes': row.get('General Notes'),
                'date_complete': row.get('Completion Date'), 'date_added': row.get('Added'),
                'date_start': row.get('Start Date'), 'date_updated': row.get('Updated'),
            }, csv_mode=True))
        return games
    except csv.Error:
        raise ValueError('Это не CSV-экспорт списка игр HLTB') from None


def fetch_hltb(profile, progress=lambda *_: None, *, raw=False):
    name = profile_name(profile, 'hltb')
    text = request('https://howlongtobeat.com/user/'+urllib.parse.quote(name))
    match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
    try:
        user = json.loads(match[1])['props']['pageProps']['userData']
        uid = int(user['user_id'])
        playstyle = user.get('set_playstyle') or 'comp_all'
    except (TypeError, KeyError, ValueError):
        raise ValueError('HLTB изменил страницу профиля или список закрыт. Используй CSV-экспорт.') from None
    games = []
    start = time.monotonic()
    for offset in range(0, LIMIT, 500):
        if time.monotonic()-start > 90: raise ValueError('Загрузка списка заняла слишком долго. Попробуй CSV.')
        payload = {
            'user_id': uid, 'toggleType': 'Multi List',
            'lists': ['playing','backlog','replays','custom','custom2','custom3','completed','retired'],
            'set_playstyle': playstyle, 'name': '', 'platform': {'mode':'include','values':[]},
            'storefront': {'mode':'include','values':[]}, 'sortBy':'', 'sortFlip':0, 'view':'',
            'random':0, 'limit':500 if offset == 0 else f'{offset},500', 'currentUserHome':False,
        }
        result = json.loads(request(f'https://howlongtobeat.com/api/user/{uid}/games/list', payload))
        data = result.get('data', {})
        rows = data.get('gamesList')
        if not isinstance(rows, list) or not isinstance(data.get('total'), int):
            raise ValueError('HLTB изменил формат списка. Используй CSV-экспорт.')
        games.extend(rows if raw else (hltb_game(row) for row in rows))
        progress(len(games), data['total'])
        if len(games) >= data['total']: return games
        if not rows: raise ValueError('HLTB вернул неполный список. Попробуй CSV.')
    raise ValueError('Список слишком большой')


def fetch_steam(profile, key):
    name = profile_name(profile, 'steam')
    key = str(key or '').strip()
    if not re.fullmatch(r'[a-fA-F0-9]{32}', key):
        raise ValueError('Для Steam нужен личный Web API key. Ключ используется только для этого запроса и не сохраняется.')
    if re.fullmatch(r'765\d{14}', name):
        steam_id = name
    else:
        try:
            steam_id = ET.fromstring(request('https://steamcommunity.com/id/'+urllib.parse.quote(name)+'/?xml=1')).findtext('steamID64')
        except ET.ParseError:
            steam_id = None
        if not steam_id or not re.fullmatch(r'\d{17}', steam_id):
            raise ValueError('Steam не вернул ID профиля')
    query = urllib.parse.urlencode({'key':key,'steamid':steam_id,'include_appinfo':1,'include_played_free_games':1,'skip_unvetted_apps':0})
    data = json.loads(request('https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?'+query)).get('response', {})
    if 'game_count' not in data:
        raise ValueError('Steam не вернул библиотеку. Проверь API key и публичность игровой информации.')
    rows = data.get('games', [])
    if not isinstance(rows, list) or len(rows) != data['game_count'] or len(rows) > LIMIT:
        raise ValueError('Steam вернул неполный список')
    return [{'title':str(row.get('name') or row['appid']), 'source_id':'steam:'+str(row['appid']),
             'source_url':f"https://store.steampowered.com/app/{row['appid']}/",
             'image':f"https://cdn.akamai.steamstatic.com/steam/apps/{row['appid']}/header.jpg",
             'platform':'PC - Steam', 'status':'Хочу пройти','provider':'Steam','tags':'Steam',
             'sync_provider':'steam','sync_key':str(row['appid']), 'sync_status':'Хочу пройти',
             'steam_playtime':str(row.get('playtime_forever',0))} for row in rows]


def fetch_steam_relay(profile, base):
    name = profile_name(profile, 'steam')
    url = base.rstrip('/')+'/v1/steam/library?'+urllib.parse.urlencode({'profile':name})
    try: rows = json.loads(request(url)).get('games')
    except (ValueError,TypeError): raise ValueError('Steam-сервис недоступен. Попробуй позже или используй личный API key.') from None
    if not isinstance(rows,list) or len(rows)>LIMIT: raise ValueError('Steam-сервис вернул некорректный список')
    result=[]
    seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Steam-сервис вернул некорректный список')
        match=re.fullmatch(r'steam:(\d{1,10})',str(row.get('source_id','')))
        title=str(row.get('title') or '').strip()
        if not match or not title or len(title)>300:raise ValueError('Steam-сервис вернул некорректный список')
        appid=match[1]
        if appid in seen:continue
        seen.add(appid)
        # Never trust URLs or private fields supplied by a configured relay.
        result.append({'title':title,'source_id':'steam:'+appid,'source_url':'https://store.steampowered.com/app/'+appid+'/',
                       'image':'https://cdn.akamai.steamstatic.com/steam/apps/'+appid+'/header.jpg',
                       'platform':'PC - Steam','status':'Хочу пройти','provider':'Steam','tags':'Steam','sync_provider':'steam','sync_key':appid,'sync_status':'Хочу пройти'})
    return result


class Manager:
    def __init__(self, store):
        self.store = store
        self.jobs = {}
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()

    def _job(self, callback):
        with self.lock:
            now = time.monotonic()
            self.jobs = {k:v for k,v in self.jobs.items() if now-v['created'] < TTL or v['state']=='running'}
            if sum(v['state']=='running' for v in self.jobs.values()) >= 3:
                raise ValueError('Дождись окончания текущей загрузки')
            key = secrets.token_urlsafe(24)
            job = {'created':now,'state':'running','current':0,'total':0,'items':[],'error':''}
            self.jobs[key] = job
        def work():
            try:
                callback(job)
                with self.lock: job['state'] = 'done'
            except Exception as exc:
                # Upstream exceptions must never include API keys/URLs.
                message = str(exc) if isinstance(exc, ValueError) else 'Не удалось завершить импорт. Повтори попытку.'
                with self.lock: job.update(state='error',error=message)
        threading.Thread(target=work, daemon=True).start()
        return {'job':key}

    def inspect(self, key):
        with self.lock:
            job = self.jobs.get(key)
            if not job or time.monotonic()-job['created'] > TTL and job['state'] != 'running':
                raise ValueError('Список устарел. Загрузи его снова.')
            return {k:v for k,v in job.items() if k not in ('created','records')}

    def steam_history(self, profile, games):
        """One atomically replaced file, separate histories for each profile."""
        path = self.store.DATA / 'steam-library-history.json'
        profile = profile_name(profile,'steam').casefold()
        with self.lock:
            try:
                history = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1,'profiles':{}}
                accounts = history['profiles']
                previous = accounts.get(profile)
                known = previous['games'] if previous else {}
                if not isinstance(accounts,dict) or not isinstance(known,dict) or any(not isinstance(value,dict) for value in known.values()): raise ValueError()
            except (ValueError,KeyError,TypeError):
                raise ValueError('Не удалось прочитать сохранённый список Steam. Файл не изменён.') from None
            now = datetime.now().isoformat(timespec='seconds')
            new_ids = set()
            updated = dict(known)
            for game in games:
                key = game['source_id']
                if previous is not None and key not in known: new_ids.add(key)
                updated[key] = {'title':game['title'],'first_seen':known.get(key,{}).get('first_seen',now)}
            accounts[profile] = {'checked_at':now,'games':updated}
            path.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as output:
                temporary = output.name
                json.dump(history,output,ensure_ascii=False,indent=2)
            try: os.replace(temporary,path)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
            return new_ids, previous is None

    def preview(self, data):
        provider = data.get('provider')
        if provider not in ('steam','hltb','hltb-csv'): raise ValueError('Неизвестный источник библиотеки')
        # Only the running worker receives the key; it is not persisted in jobs/settings.
        def load(job):
            def progress(current,total):
                with self.lock: job.update(current=current,total=total)
            if provider=='steam':
                relay = self.store.settings().get('steam_relay_url','')
                games = fetch_steam(data.get('profile'), data.get('api_key')) if data.get('api_key') or not relay else fetch_steam_relay(data.get('profile'),relay)
                for game in games:
                    game['tags'] = ', '.join(dict.fromkeys([tag.strip() for tag in (game.get('tags','')+',Steam').split(',') if tag.strip()]))
            elif provider=='hltb':
                raw = fetch_hltb(data.get('profile'), progress, raw=True)
                groups = {}
                for row in raw:
                    pair = identity(hltb_game(row))
                    groups.setdefault(pair, []).append(row)
                games = []
                for entries in groups.values():
                    entries.sort(key=lambda r:str(r.get('date_updated') or ''))
                    game = hltb_game(entries[-1])
                    dates = [str(r.get('date_complete'))[:10] for r in entries if r.get('date_complete') and not str(r['date_complete']).startswith('0000')]
                    added = [str(r.get('date_added') or '') for r in entries]
                    game.update(hltb_entries=entries, completed_at=max(dates) if dates else '', sync_added_at=max(added))
                    games.append(game)
            else: games = parse_csv(data.get('csv'))
            consolidated = {}
            for game in games:
                pair = ('steam',game['source_id']) if provider=='steam' else identity(game)
                if pair in consolidated:
                    previous = consolidated[pair]
                    date = max(previous.get('completed_at',''),game.get('completed_at',''))
                    added = max(previous.get('sync_added_at',''),game.get('sync_added_at',''))
                    previous.update({k:v for k,v in game.items() if v})
                    previous['completed_at'] = date
                    previous['sync_added_at'] = added
                else: consolidated[pair] = game
            games = list(consolidated.values())
            new_ids, baseline = self.steam_history(data.get('profile'),games) if provider=='steam' else (set(),False)
            existing = self.store.library()
            by_source = {g['source_id']:g for g in existing if g.get('source_id')}
            by_title = {}
            for g in existing: by_title.setdefault(identity(g), []).append(g)
            seen = set()
            records = []
            for game in games:
                pair = identity(game)
                unique = ('steam',game['source_id']) if provider=='steam' else pair
                if unique in seen: continue
                seen.add(unique)
                exact = by_source.get(game.get('source_id'))
                candidates = [exact] if exact and (provider=='steam' or identity(exact)==pair) else by_title.get(pair, [])
                if provider=='steam':
                    candidates = [g for g in candidates if not str(g.get('source_id','')).startswith('steam:') or g['source_id']==game['source_id']]
                old = candidates[0] if len(candidates)==1 else None
                records.append(dict(game, existing_id=old['id'] if old else None,
                                    steam_new=game.get('source_id') in new_ids,
                                    ambiguous=len(candidates)>1, existing=old or {},
                                    can_update=bool(old)))
            if provider in ('hltb','hltb-csv'):
                records.sort(key=lambda game:game.get('sync_added_at',''),reverse=True)
            elif provider=='steam':
                records.sort(key=lambda game:game['steam_new'],reverse=True)
            with self.lock:
                job.update(records=records, items=records, current=len(games),total=len(games),
                           steam_baseline=baseline,steam_new_count=len(new_ids),
                           repeated=len(games)-len(records))
        return self._job(load)

    def apply(self, data):
        with self.lock:
            preview = self.jobs.get(data.get('preview'))
            if not preview or preview['state'] != 'done' or 'records' not in preview or time.monotonic()-preview['created'] > TTL:
                raise ValueError('Список устарел. Загрузи его снова.')
            indices = data.get('selected')
            if not isinstance(indices, list) or not indices or any(type(i) is not int or i<0 or i>=len(preview['records']) for i in indices):
                raise ValueError('Выбери игры')
            records = [(i,dict(preview['records'][i])) for i in dict.fromkeys(indices)]
        choices = data.get('choices', {})
        allowed = {'status','completed_at','platform','image','description','notes','release_date','tags'}
        if not isinstance(choices,dict) or any(not isinstance(c,dict) or not isinstance(c.get('fields',[]),list) or any(f not in allowed for f in c.get('fields',[])) or type(c.get('overwrite',False)) is not bool for c in choices.values()):
            raise ValueError('Некорректные изменения')
        if not self.write_lock.acquire(blocking=False): raise ValueError('Дождись окончания текущего импорта')
        chosen_status = data.get('status', '__source__')
        favorites = data.get('favorite') is True
        def save(job):
            try:
                job.update(total=len(records),added=0,skipped=0,updated=0)
                self.store.create_backup(automatic=False)
                if any(game.get('sync_provider')=='hltb' for _,game in records):
                    with self.store.connection() as db:
                        for name in ('Бэклог','Играю','Пройдено','Брошено'):
                            db.execute('INSERT OR IGNORE INTO categories VALUES (?,(SELECT COALESCE(MAX(position),0)+1 FROM categories))',(name,))
                for index, (record_index, game) in enumerate(records):
                    with self.store.MUTATION_LOCK:
                        current = self.store.library()
                        matches = [g for g in current if identity(game)==identity(g)]
                        if game.get('sync_provider')=='steam':
                            matches = [g for g in matches if not str(g.get('source_id','')).startswith('steam:') or g['source_id']==game['source_id']]
                            exact = next((g for g in current if g.get('source_id')==game['source_id']),None)
                            if exact: matches = [exact]
                        old = next((g for g in matches if g['id']==game.get('existing_id')),None) or (matches[0] if len(matches)==1 else None)
                    if len(matches)>1 and old is None:
                        raise ValueError('Неоднозначное совпадение. Сопоставь игры вручную.')
                    target_status = game['status'] if chosen_status=='__source__' else chosen_status
                    if target_status not in self.store.category_names(): target_status=self.store.settings()['default_category']
                    if old:
                        choice = choices.get(str(record_index), {})
                        fields = choice.get('fields', [])
                        if fields:
                            patch = {'title':old['title']}
                            for field in fields:
                                value = target_status if field=='status' else game.get(field,'')
                                if field=='tags':
                                    value = ', '.join(dict.fromkeys([x.strip() for x in (old.get('tags','')+','+str(value)).split(',') if x.strip()]))
                                if value and (field=='tags' or choice.get('overwrite') or not old.get(field)):
                                    patch[field] = value
                            patch.update({k:game[k] for k in ('hltb_entries','hltb_game_id','hltb_url','hltb_updated_at','sync_added_at','sync_status') if k in game})
                            with self.store.MUTATION_LOCK: self.store.save_game(patch,old['id'])
                            job['updated'] += 1
                        else: job['skipped'] += 1
                    else:
                        for key in ('existing_id','can_update','existing','ambiguous'):game.pop(key,None)
                        with self.store.MUTATION_LOCK: self.store.save_game(dict(game,status=target_status,favorite=favorites))
                        job['added'] += 1
                    with self.lock: job['current']=index+1
            finally:
                self.write_lock.release()
        try: return self._job(save)
        except Exception:
            self.write_lock.release()
            raise
