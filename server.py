"""Local personal game library. Python standard library only."""
from __future__ import annotations
import argparse
import html
import json
import math
import hashlib
import re
import secrets
import socket
import os
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from storage import user_data_directory
import zipfile
import tempfile
import io
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from contextlib import contextmanager, closing
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DB = DATA / 'library.sqlite3'
TOKEN = secrets.token_urlsafe(32)
STATUSES = ['Хочу пройти', 'Играю', 'Пройдено', 'Отложено', 'Брошено']
DEFAULT_PLATFORMS = ['Пока неизвестно','PC','Steam Deck','PlayStation 5','PlayStation 4','Xbox Series X/S','Xbox One','Nintendo Switch','Nintendo Switch 2','Android','iOS','Эмулятор']
DEFAULT_SETTINGS = {'hidden_categories': [], 'show_card_notes': True, 'default_category': 'Хочу пройти', 'language': 'en'}
CACHE = {}
CACHE_LOCK = threading.Lock()
MUTATION_LOCK = threading.RLock()
TRASH = {}


def remote(url):
    with CACHE_LOCK:
        cached = CACHE.get(url)
        if cached and time.monotonic() - cached[0] < 1800:
            return cached[1]
    request = urllib.request.Request(url, headers={'User-Agent': 'BackloGame/0.1 (personal desktop game library)', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.load(response)
    with CACHE_LOCK:
        if len(CACHE) > 300:
            CACHE.clear()
        CACHE[url] = (time.monotonic(), result)
    return result


def api_url(base, **params):
    return base + '?' + urllib.parse.urlencode(params)


def clean(value):
    text = re.sub(r'<(?:br\s*/?|/p|/div|/h[1-6]|/li)>', '\n\n', str(value or ''), flags=re.I)
    return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', html.unescape(re.sub('<[^>]+>', '', text))).strip()


def is_russian(text):
    letters = re.findall(r'[A-Za-zА-Яа-яЁё]', text)
    return bool(letters) and len(re.findall(r'[А-Яа-яЁё]', text)) / len(letters) > .2


def wiki_page(lang, **selector):
    payload = remote(api_url(f'https://{lang}.wikipedia.org/w/api.php', action='query', prop='extracts|pageimages|pageprops|langlinks', explaintext=1, piprop='original', pilicense='any', lllang='ru', redirects=1, format='json', **selector))
    return next(iter(payload.get('query', {}).get('pages', {}).values()))


def wiki_description(text):
    # Include introduction and gameplay, without importing the plot/spoilers section.
    sections = re.split(r'\n\s*==\s*([^=\n]+?)\s*==\s*\n', text)
    chosen = [sections[0].strip()]
    for index in range(1, len(sections) - 1, 2):
        if sections[index].strip().lower() in ('игровой процесс', 'геймплей', 'gameplay'):
            chosen.append('Игровой процесс\n\n' + sections[index + 1].strip())
    return '\n\n'.join(x for x in chosen if x)[:14000]


def localized_wiki_page(lang, **selector):
    page = wiki_page(lang, **selector)
    if lang != 'ru':
        translated = next((x['*'] for x in page.get('langlinks', []) if x['lang'] == 'ru'), None)
        if translated:
            return 'ru', wiki_page('ru', titles=translated)
    return lang, page


def russian_description_for_title(title):
    base = re.split(r'\s+[-–—]\s+(?:Remastered|Complete Edition|Definitive Edition|Deluxe Edition)', title, flags=re.I)[0]
    candidates = search_games(base, 'wikipedia')
    normalize = lambda value: re.sub(r'[^a-z0-9а-яё]', '', re.sub(r'\s*\([^)]*\)', '', value.lower()))
    for candidate in candidates:
        if normalize(candidate['title']) == normalize(base):
            match = re.fullmatch(r'wiki:(en|ru):(\d+)', candidate['source_id'])
            lang, page = localized_wiki_page(match[1], pageids=match[2])
            text = wiki_description(page.get('extract', ''))
            if lang == 'ru' and is_russian(text):
                return text, f'https://ru.wikipedia.org/?curid={page["pageid"]}'
    return '', ''


def steam_app_id(query):
    value = query.strip()
    if re.fullmatch(r'(?:steam:)?\d{1,10}', value):
        return value.split(':')[-1]
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in ('http', 'https') and parsed.hostname in ('store.steampowered.com', 'www.store.steampowered.com'):
        match = re.match(r'^/app/(\d{1,10})(?:/|$)', parsed.path)
        if match:
            return match[1]
    return None


def steam_result(appid):
    payload = remote(api_url('https://store.steampowered.com/api/appdetails/', appids=appid, l='russian', cc='us'))
    result = payload.get(str(appid), {})
    if not result.get('success'):
        raise ValueError('Steam не вернул игру с таким App ID. Проверьте ссылку или номер.')
    data = result['data']
    kind = data.get('type', 'unknown')
    label = {'game':'Игра', 'dlc':'Дополнение', 'music':'Саундтрек', 'demo':'Демо', 'video':'Видео'}.get(kind, 'Тип не проверен')
    return {'source_id': f'steam:{appid}', 'title': data['name'], 'image': data.get('header_image', ''), 'steam_type':kind, 'provider': 'Steam · ' + label, 'source_url': f'https://store.steampowered.com/app/{appid}/'}


def title_key(title):
    return re.sub(r'[^a-z0-9а-яё]', '', title.lower())


def remote_html(url):
    key = ('html', url)
    with CACHE_LOCK:
        cached = CACHE.get(key)
        if cached and time.monotonic() - cached[0] < 1800:
            return cached[1]
    request = urllib.request.Request(url, headers={'User-Agent': 'BackloGame/0.1 (personal desktop game library)', 'Accept': 'text/html'})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            content = response.read(4_000_001)
            if len(content) > 4_000_000:
                raise ValueError('Страница Metacritic слишком большая.')
            result = content.decode('utf-8')
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise ValueError('Metacritic временно ограничил доступ. Попробуй позже или добавь игру вручную.') from exc
        raise
    with CACHE_LOCK:
        if len(CACHE) > 300:
            CACHE.clear()
        CACHE[key] = (time.monotonic(), result)
    return result


def metacritic_slug(value):
    parsed = urllib.parse.urlparse(value.strip())
    if parsed.scheme in ('http', 'https') and parsed.hostname in ('metacritic.com', 'www.metacritic.com'):
        match = re.fullmatch(r'/game/([a-z0-9-]+)(?:/(?:details|critic-reviews|user-reviews))?/?', parsed.path)
        if match:
            return match[1]
    return None


def metacritic_details(slug):
    if not re.fullmatch(r'[a-z0-9-]+', slug):
        raise ValueError('Некорректная ссылка Metacritic')
    url = f'https://www.metacritic.com/game/{slug}/'
    page = remote_html(url)
    for raw in re.findall(r'<script\b[^>]*\btype=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', page, re.I | re.S):
        try:
            payload = json.loads(raw)
        except ValueError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict) and item.get('@type') == 'VideoGame' and item.get('name'):
                image = item.get('image', '')
                if isinstance(image, dict):
                    image = image.get('url', '')
                platforms = item.get('gamePlatform', [])
                genre = item.get('genre', [])
                return {'source_id': 'metacritic:' + slug, 'title': clean(item['name']),
                        'description': clean(item.get('description', ''))[:14000], 'description_language': 'original',
                        'description_url': url, 'image': image if isinstance(image, str) else '',
                        'release_date': str(item.get('datePublished', ''))[:10],
                        'available_platforms': ', '.join(platforms) if isinstance(platforms, list) else str(platforms),
                        'genre': ', '.join(genre) if isinstance(genre, list) else str(genre),
                        'source_url': url, 'provider': 'Metacritic'}
    raise ValueError('Metacritic не вернул карточку игры. Проверь ссылку или добавь игру вручную.')


def metacritic_search(query):
    page = remote_html('https://www.metacritic.com/search/' + urllib.parse.quote(query, safe='') + '/')
    results = []
    # Only search result anchors: navigation and related-game links are excluded.
    for attrs, body in re.findall(r'<a\b([^>]*)>(.*?)</a>', page, re.I | re.S):
        if not re.search(r'\bclass=[\"\'][^\"\']*\bc-search-item\b', attrs):
            continue
        path = re.search(r'\bhref=[\"\'](/game/[a-z0-9-]+/)[\"\']', attrs)
        title = re.search(r'<p\b[^>]*\bclass=[\"\'][^\"\']*\bc-search-item__title\b[^>]*>(.*?)</p>', body, re.I | re.S)
        if not path or not title:
            continue
        slug = path[1].split('/')[2]
        if any(x['source_id'] == 'metacritic:' + slug for x in results):
            continue
        image = re.search(r'<img\b[^>]*\bsrc=[\"\']([^\"\']+)', body, re.I)
        results.append({'source_id': 'metacritic:' + slug, 'title': clean(title[1]),
                        'image': html.unescape(image[1]) if image else '', 'provider': 'Metacritic',
                        'source_url': 'https://www.metacritic.com' + path[1]})
    words = set(re.findall(r'[a-z0-9а-яё]+', query.lower())) - {'of', 'the', 'and'}
    def missing_words(item):
        return len(words - set(re.findall(r'[a-z0-9а-яё]+', item['title'].lower())))
    if len(words) >= 4:
        results = [item for item in results if missing_words(item) <= len(words) // 4]
    results.sort(key=lambda item: (title_key(item['title']) != title_key(query), missing_words(item)))
    return results[:30]


def wiki_is_list(title):
    return bool(re.match(r'^(?:lists?\s+of\b|спис(?:ок|ки)\b|перечень\b)', title, re.I))


def steam_title_fallback(query, existing):
    if any(title_key(x['title']) == title_key(query) for x in existing):
        return existing
    language = 'ru' if re.search('[а-яА-ЯёЁ]', query) else 'en'
    payload = remote(api_url('https://www.wikidata.org/w/api.php', action='wbsearchentities', search=query, language=language, limit=5, format='json'))
    found = []
    for item in payload.get('search', []):
        if title_key(query) not in (title_key(item.get('label', '')), title_key(item.get('match', {}).get('text', ''))):
            continue
        for appid in claims(entity(item['id']), 'P1733')[:2]:
            appid = str(appid)
            if appid.isdigit() and not any(x['source_id'] == f'steam:{appid}' for x in existing + found):
                try:
                    game = steam_result(appid)
                    game['qid'] = item['id']
                    game['provider'] = game.get('provider', 'Steam') + ' · найдено через Wikidata'
                    found.append(game)
                except (OSError, ValueError, KeyError):
                    pass
        if found:
            break
    return found + existing


def search_games(query, provider='steam', include_extras=False):
    query = query.strip()[:1000]
    if not query:
        return []
    if provider not in ('steam','wikipedia','metacritic'):
        raise ValueError('Неизвестный каталог игр')
    appid = steam_app_id(query)
    if appid:
        return [steam_result(appid)]
    slug = metacritic_slug(query)
    if slug:
        return [metacritic_details(slug)]
    query = query[:150]
    if provider == 'metacritic':
        return metacritic_search(query)
    if provider == 'steam':
        payload = remote(api_url('https://store.steampowered.com/api/storesearch/', term=query, l='russian', cc='us'))
        results = [{'source_id': 'steam:' + str(x['id']), 'title': x['name'], 'image': x.get('tiny_image', ''), 'provider': 'Steam'} for x in payload.get('items', []) if x.get('type') == 'app']
        def classify(item):
            try:
                checked = steam_result(item['source_id'].split(':')[1])
                return dict(item, **checked)
            except (OSError, ValueError, KeyError):
                return dict(item, steam_type='unknown', provider='Steam · Тип не проверен')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(classify, results))
        try:
            results = steam_title_fallback(query, results)
        except (OSError, ValueError, KeyError):
            pass
        if not include_extras:
            results = [item for item in results if item.get('steam_type', 'unknown') in ('game','unknown')]
        # Confirmed games precede extras and exact titles precede editions.
        results.sort(key=lambda item:(item.get('steam_type') != 'game', title_key(item['title']) != title_key(query)))
        return results
    lang = 'ru' if re.search('[а-яА-Я]', query) else 'en'
    payload = remote(api_url(f'https://{lang}.wikipedia.org/w/api.php', action='query', generator='search', gsrsearch=query, gsrlimit=15, prop='extracts|pageimages|pageprops', exintro=1, explaintext=1, exsentences=3, piprop='original', pilicense='any', format='json'))
    pages = sorted(payload.get('query', {}).get('pages', {}).values(), key=lambda x: x.get('index', 999))
    return [{'source_id': f'wiki:{lang}:{x["pageid"]}', 'title': x['title'], 'description': x.get('extract', ''), 'image': x.get('original', {}).get('source', ''), 'qid': x.get('pageprops', {}).get('wikibase_item', ''), 'provider': 'Wikipedia', 'source_url': f'https://{lang}.wikipedia.org/?curid={x["pageid"]}'} for x in pages if not wiki_is_list(x['title'])]


def entity(qid):
    if not re.fullmatch(r'Q\d+', qid):
        raise ValueError('Некорректный идентификатор Wikidata')
    return remote(f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json')['entities'][qid]


def claims(data, prop):
    return [x['mainsnak']['datavalue']['value'] for x in data.get('claims', {}).get(prop, []) if 'datavalue' in x.get('mainsnak', {}) and x.get('rank') != 'deprecated']


def label(data):
    labels = data.get('labels', {})
    return labels.get('ru', labels.get('en', labels.get('mul', {}))).get('value', data.get('id', ''))


def enrich_wikidata(game):
    data = entity(game['qid'])
    dates = claims(data, 'P577')
    if dates:
        game['release_date'] = min(x['time'][1:11] for x in dates if x['time'].startswith('+'))
        # Wikidata precision 9 is a year, 10 is a month, 11 is a day.
        precision = min(x.get('precision', 11) for x in dates)
        if precision < 11:
            game['release_date'] = game['release_date'][:4 if precision < 10 else 7]
    series = claims(data, 'P179')
    if series:
        game['series_qid'] = series[0]['id']
        game['series'] = label(entity(series[0]['id']))
    game['title'] = game.get('title') or label(data)
    if not game.get('description'):
        game['description'] = data.get('descriptions', {}).get('ru', data.get('descriptions', {}).get('en', {})).get('value', '')
    for prop, field in [('P136', 'genre'), ('P400', 'available_platforms')]:
        ids = [x['id'] for x in claims(data, prop)][:8]
        if ids:
            payload = remote(api_url('https://www.wikidata.org/w/api.php', action='wbgetentities', ids='|'.join(ids), props='labels', languages='ru|en', format='json'))
            game[field] = ', '.join(label(x) for x in payload.get('entities', {}).values())
    if not game.get('image'):
        images = claims(data, 'P18')
        if images:
            game['image'] = 'https://commons.wikimedia.org/wiki/Special:FilePath/' + urllib.parse.quote(images[0]) + '?width=600'
    game['source_url'] = game.get('source_url') or f'https://www.wikidata.org/wiki/{game["qid"]}'
    return game


def details(source_id):
    game = {'source_id': source_id}
    if source_id.startswith('metacritic:'):
        return metacritic_details(source_id.split(':', 1)[1])
    if re.fullmatch(r'steam:\d+', source_id):
        appid = source_id.split(':')[1]
        payload = remote(api_url('https://store.steampowered.com/api/appdetails/', appids=appid, l='russian', cc='us'))
        result = payload.get(appid, {})
        if not result.get('success'):
            raise ValueError('Steam не вернул сведения об этой игре')
        data = result['data']
        release = data.get('release_date', {})
        game.update(title=data['name'], description=clean(data.get('about_the_game') or data.get('detailed_description') or data.get('short_description'))[:14000], image=data.get('header_image', ''), genre=', '.join(x['description'] for x in data.get('genres', [])), available_platforms=', '.join(k for k, v in data.get('platforms', {}).items() if v), release_label=release.get('date', ''), release_date='', developer=', '.join(data.get('developers', [])), source_url=f'https://store.steampowered.com/app/{appid}/')
        # Request an English date for a stable parse; release year alone stays useful.
        en = remote(api_url('https://store.steampowered.com/api/appdetails/', appids=appid, l='english', cc='us')).get(appid, {}).get('data', {})
        game['original_title'] = en.get('name', data['name'])
        game['description_url'] = game['source_url']
        if not is_russian(game['description']) or len(game['description']) < 700:
            try:
                description, url = russian_description_for_title(game['original_title'])
                if description and (len(description) > len(game['description']) or not is_russian(game['description'])):
                    game.update(description=description, description_url=url)
            except (OSError, KeyError, ValueError):
                pass
        game['description_language'] = 'ru' if is_russian(game['description']) else 'original'
        raw = en.get('release_date', {}).get('date', '')
        for fmt in ('%d %b, %Y', '%b %d, %Y', '%d %B, %Y', '%B %d, %Y'):
            try:
                game['release_date'] = datetime.strptime(raw, fmt).date().isoformat()
                break
            except ValueError:
                pass
        if not game['release_date'] and re.fullmatch(r'\d{4}', raw):
            game['release_date'] = raw
        return game
    match = re.fullmatch(r'wiki:(en|ru):(\d+)', source_id)
    if match:
        lang, pageid = match.groups()
        lang, page = localized_wiki_page(lang, pageids=pageid)
        game.update(title=page['title'], description=wiki_description(page.get('extract', '')), description_language='ru' if lang == 'ru' else 'original', image=page.get('original', {}).get('source', ''), qid=page.get('pageprops', {}).get('wikibase_item', ''), source_url=f'https://{lang}.wikipedia.org/?curid={page["pageid"]}')
        game['description_url'] = game['source_url']
        if game['qid']:
            try:
                enrich_wikidata(game)
            except (OSError, ValueError, KeyError):
                game['metadata_warning'] = 'Дополнительные сведения Wikidata сейчас недоступны. Их можно заполнить вручную.'
        return game
    if re.fullmatch(r'wd:Q\d+', source_id):
        game['qid'] = source_id[3:]
        data = entity(game['qid'])
        game['title'] = label(data)
        wiki = data.get('sitelinks', {}).get('ruwiki')
        if wiki:
            page = wiki_page('ru', titles=wiki['title'])
            game.update(description=wiki_description(page.get('extract', '')), description_language='ru', description_url=f'https://ru.wikipedia.org/?curid={page["pageid"]}')
        return enrich_wikidata(game)
    raise ValueError('Неизвестный источник игры')


@contextmanager
def connection():
    db = sqlite3.connect(DB, timeout=10)
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    DATA.mkdir(parents=True,exist_ok=True)
    with connection() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY, source_id TEXT UNIQUE, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS platforms (name TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY, position INTEGER NOT NULL)')
        if not db.execute('SELECT 1 FROM settings WHERE name=?', ('categories_seeded',)).fetchone():
            names = list(STATUSES)
            names.extend(json.loads(row[0]).get('status', '') for row in db.execute('SELECT payload FROM games').fetchall())
            for index, name in enumerate(dict.fromkeys(x for x in names if x)):
                db.execute('INSERT OR IGNORE INTO categories VALUES (?,?)', (name,index))
            db.execute('INSERT INTO settings VALUES (?,?)', ('categories_seeded','true'))
        if 'manual_order' not in [row[1] for row in db.execute('PRAGMA table_info(games)')]:
            db.execute('ALTER TABLE games ADD COLUMN manual_order INTEGER NOT NULL DEFAULT 0')
            for index, (gid,) in enumerate(db.execute('SELECT id FROM games ORDER BY id').fetchall()):
                db.execute('UPDATE games SET manual_order=? WHERE id=?', (index + 1, gid))
        if not db.execute('SELECT 1 FROM settings WHERE name=?', ('platform_defaults_seeded',)).fetchone():
            db.executemany('INSERT OR IGNORE INTO platforms(name) VALUES (?)', [(x,) for x in DEFAULT_PLATFORMS])
            db.execute('INSERT INTO settings VALUES (?,?)', ('platform_defaults_seeded', 'true'))
        for (payload,) in db.execute('SELECT payload FROM games').fetchall():
            platform = json.loads(payload).get('platform', '').strip()
            if platform:
                db.execute('INSERT OR IGNORE INTO platforms(name) VALUES (?)', (platform,))


def library():
    with connection() as db:
        return [dict(json.loads(payload), id=gid, manual_order=order) for gid, payload, order in db.execute('SELECT id,payload,manual_order FROM games ORDER BY manual_order,id')]


def platform_names():
    with connection() as db:
        return [row[0] for row in db.execute('SELECT name FROM platforms ORDER BY name')]


def settings():
    with connection() as db:
        result = dict(DEFAULT_SETTINGS, **{name: json.loads(value) for name, value in db.execute('SELECT name,value FROM settings') if name in DEFAULT_SETTINGS})
        names = [x[0] for x in db.execute('SELECT name FROM categories ORDER BY position,name')]
        if result['default_category'] not in names:
            result['default_category'] = names[0]
        return result


def category_names():
    with connection() as db:
        return [x[0] for x in db.execute('SELECT name FROM categories ORDER BY position,name')]


def validate_settings(data, allowed_categories=None):
    if not isinstance(data, dict):
        raise ValueError('Некорректные настройки')
    result = {}
    if 'language' in data:
        if data['language'] not in ('en', 'ru'):
            raise ValueError('Unsupported interface language')
        result['language'] = data['language']
    if 'hidden_categories' in data:
        values = data['hidden_categories']
        if not isinstance(values, list) or any(x not in (allowed_categories or category_names()) + ['favorites','not-favorites'] for x in values):
            raise ValueError('Неизвестная категория')
        result['hidden_categories'] = list(dict.fromkeys(values))
    if 'show_card_notes' in data:
        if not isinstance(data['show_card_notes'], bool):
            raise ValueError('Некорректный параметр заметок')
        result['show_card_notes'] = data['show_card_notes']
    if 'default_category' in data:
        if data['default_category'] not in (allowed_categories or category_names()):
            raise ValueError('Неизвестная категория для новых игр')
        result['default_category'] = data['default_category']
    return result


def reorder_game(gid, target, after=False):
    if not isinstance(gid, int) or not isinstance(target, int) or not isinstance(after, bool):
        raise ValueError('Некорректный порядок')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        ids = [x[0] for x in db.execute('SELECT id FROM games ORDER BY manual_order,id')]
        if gid not in ids or target not in ids:
            raise ValueError('Игра уже удалена; обновите библиотеку')
        if gid == target:
            return
        ids.remove(gid)
        ids.insert(ids.index(target) + int(after), gid)
        db.executemany('UPDATE games SET manual_order=? WHERE id=?', [(i + 1, value) for i, value in enumerate(ids)])


def manage_platform(data):
    action = data.get('action')
    name = str(data.get('name', '')).strip()
    if not name or len(name) > 300:
        raise ValueError('Укажите название платформы (до 300 символов)')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if action == 'add':
            db.execute('INSERT OR IGNORE INTO platforms(name) VALUES (?)', (name,))
            return
        if name == 'Пока неизвестно':
            raise ValueError('Платформу «Пока неизвестно» нельзя изменить или удалить')
        if not db.execute('SELECT 1 FROM platforms WHERE name=?', (name,)).fetchone():
            raise ValueError('Платформа уже удалена')
        replacement = str(data.get('replacement', '')).strip()
        if action not in ('rename','delete') or not replacement or len(replacement) > 300 or replacement.casefold() == name.casefold():
            raise ValueError('Укажите другое название или платформу для замены')
        if action == 'delete' and not db.execute('SELECT 1 FROM platforms WHERE name=?', (replacement,)).fetchone():
            raise ValueError('Выберите существующую платформу для замены')
        db.execute('INSERT OR IGNORE INTO platforms(name) VALUES (?)', (replacement,))
        for gid, payload in db.execute('SELECT id,payload FROM games').fetchall():
            game = json.loads(payload)
            if game.get('platform', '').casefold() == name.casefold():
                game['platform'] = replacement
                db.execute('UPDATE games SET payload=? WHERE id=?', (json.dumps(game, ensure_ascii=False), gid))
        for (old_name,) in db.execute('SELECT name FROM platforms').fetchall():
            if old_name.casefold() == name.casefold():
                db.execute('DELETE FROM platforms WHERE name=?', (old_name,))


def manage_category(data):
    action = data.get('action')
    name = str(data.get('name', '')).strip()
    if not name or len(name) > 100 or name in ('favorites','not-favorites','Все игры'):
        raise ValueError('Укажите название категории до 100 символов')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        names = [x[0] for x in db.execute('SELECT name FROM categories ORDER BY position,name')]
        if action == 'add':
            if any(x.casefold() == name.casefold() for x in names):
                raise ValueError('Такая категория уже есть')
            db.execute('INSERT INTO categories VALUES (?,(SELECT COALESCE(MAX(position),0)+1 FROM categories))', (name,))
            return
        if name not in names:
            raise ValueError('Категория уже удалена')
        replacement = str(data.get('replacement', '')).strip()
        if action not in ('rename','delete') or not replacement or len(replacement) > 100 or replacement in ('favorites','not-favorites','Все игры') or name == replacement:
            raise ValueError('Укажите другую категорию')
        if action == 'delete' and (len(names) < 2 or replacement not in names):
            raise ValueError('Оставьте хотя бы одну категорию и выберите категорию для переноса')
        if action == 'rename' and replacement not in names:
            position = db.execute('SELECT position FROM categories WHERE name=?', (name,)).fetchone()[0]
            db.execute('INSERT INTO categories VALUES (?,?)', (replacement,position))
        for gid, payload in db.execute('SELECT id,payload FROM games').fetchall():
            game = json.loads(payload)
            if game.get('status') == name:
                game['status'] = replacement
                db.execute('UPDATE games SET payload=? WHERE id=?', (json.dumps(game,ensure_ascii=False),gid))
        db.execute('DELETE FROM categories WHERE name=?', (name,))
        for key, value in db.execute('SELECT name,value FROM settings').fetchall():
            if key == 'default_category' and json.loads(value) == name:
                db.execute('UPDATE settings SET value=? WHERE name=?', (json.dumps(replacement,ensure_ascii=False),key))
            elif key == 'hidden_categories':
                hidden = json.loads(value)
                hidden = [replacement if x == name and action == 'rename' else x for x in hidden if x != name or action == 'rename']
                db.execute('UPDATE settings SET value=? WHERE name=?', (json.dumps(list(dict.fromkeys(hidden)),ensure_ascii=False),key))
        if name == DEFAULT_SETTINGS['default_category'] and not db.execute('SELECT 1 FROM settings WHERE name=?',('default_category',)).fetchone():
            db.execute('INSERT INTO settings VALUES (?,?)',('default_category',json.dumps(replacement,ensure_ascii=False)))


FIELDS = {'source_id', 'title', 'original_title', 'image', 'description', 'qid', 'series_qid', 'series', 'genre', 'release_date', 'release_label', 'developer', 'available_platforms', 'source_url', 'platform', 'status', 'notes', 'tags', 'priority', 'added_at', 'favorite'}
FIELDS.update({'description_url', 'description_language'})
FIELDS.add('thumbnail_crop')
FIELDS.add('image_local')


def validate(data, allowed_statuses=None):
    result = {k: str(v or '').strip() for k, v in data.items() if k in FIELDS and k not in ('favorite', 'thumbnail_crop')}
    if data.get('media_type') not in (None, '', 'game'):
        raise ValueError('В библиотеку можно добавлять только игры')
    if 'thumbnail_crop' in data:
        crop = data['thumbnail_crop']
        if crop is not None:
            if not isinstance(crop, dict) or not isinstance(crop.get('image'), str) or len(crop['image']) > 20000:
                raise ValueError('Некорректная область миниатюры')
            for key in ('x', 'y', 'width', 'height'):
                value = crop.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError('Некорректная область миниатюры')
            if crop['width'] <= 0 or crop['height'] <= 0 or crop['x'] + crop['width'] > 1.000001 or crop['y'] + crop['height'] > 1.000001:
                raise ValueError('Область миниатюры выходит за обложку')
            crop = {key: crop[key] for key in ('x', 'y', 'width', 'height', 'image')}
        result['thumbnail_crop'] = crop
    local = result.get('image_local', '')
    if local and (not re.fullmatch(r'/covers/[a-f0-9]{64}\.(?:png|jpg|gif|webp)', local) or not (DATA / local.lstrip('/')).is_file()):
        result['image_local'] = ''
    if 'favorite' in data:
        if not isinstance(data['favorite'], bool):
            raise ValueError('Избранное должно быть true или false')
        result['favorite'] = data['favorite']
    if not result.get('title'):
        raise ValueError('Укажите название игры')
    if len(result['title']) > 300 or any(len(v) > 20000 for v in result.values() if isinstance(v, str)):
        raise ValueError('Слишком длинное поле')
    if result.get('status', settings()['default_category']) not in (allowed_statuses or category_names()):
        raise ValueError('Неизвестный статус')
    for field in ('image', 'source_url'):
        if result.get(field) and not result[field].startswith(('https://', 'http://')):
            raise ValueError('Ссылки должны начинаться с https:// или http://')
    date = result.get('release_date', '')
    if date:
        if not re.fullmatch(r'\d{4}(-\d{2})?(-\d{2})?', date):
            raise ValueError('Дата выхода: ГГГГ, ГГГГ-ММ или ГГГГ-ММ-ДД')
        datetime.fromisoformat(date + ('-01-01' if len(date) == 4 else '-01' if len(date) == 7 else ''))
    if result.get('added_at'):
        datetime.fromisoformat(result['added_at'].replace('Z', '+00:00'))
    return result


def archive_cover(url):
    if not url:
        return ''
    parts = urllib.parse.urlsplit(url)
    if parts.hostname == 'upload.wikimedia.org':
        query = [(k,v) for k,v in urllib.parse.parse_qsl(parts.query) if not k.startswith('utm_')]
        url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    request = urllib.request.Request(url, headers={'User-Agent':'BackloGame/0.1', 'Cache-Control':'no-cache'})
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read(12 * 1024 * 1024 + 1)
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError('Обложка больше 12 МБ')
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        extension = 'png'
    elif raw.startswith(b'\xff\xd8\xff'):
        extension = 'jpg'
    elif raw[:6] in (b'GIF87a', b'GIF89a'):
        extension = 'gif'
    elif raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        extension = 'webp'
    else:
        raise ValueError('Источник не вернул изображение PNG, JPEG, GIF или WebP')
    name = hashlib.sha256(raw).hexdigest() + '.' + extension
    directory = DATA / 'covers'
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / name
    if not destination.exists():
        temporary = directory / (name + '.' + secrets.token_hex(6) + '.tmp')
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return '/covers/' + name


def update_cover(gid, steam=False):
    game = next((g for g in library() if g['id'] == gid), None)
    if not game:
        raise ValueError('Игра уже удалена')
    url = game.get('image', '')
    if steam:
        match = re.fullmatch(r'steam:(\d+)', game.get('source_id', ''))
        if not match:
            raise ValueError('У этой игры нет Steam App ID')
        appid = match[1]
        # A fresh request also picks up a changed CDN URL.
        request = urllib.request.Request(api_url('https://store.steampowered.com/api/appdetails/', appids=appid, l='russian', cc='us'), headers={'User-Agent':'BackloGame/0.1', 'Cache-Control':'no-cache'})
        with urllib.request.urlopen(request, timeout=15) as response:
            entry = json.load(response).get(appid, {})
        if not entry.get('success') or not entry.get('data', {}).get('header_image'):
            raise ValueError('Steam не вернул обложку; сохранённая копия остаётся')
        url = entry['data']['header_image']
    if not url:
        raise ValueError('У игры нет обложки')
    local = archive_cover(url)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT payload FROM games WHERE id=?', (gid,)).fetchone()
        if not row:
            raise ValueError('Игра уже удалена')
        current = json.loads(row[0])
        if current.get('image') != game.get('image'):
            raise ValueError('Обложка была изменена; повторите обновление')
        if (current.get('image_local') and current['image_local'] != local) or current.get('image') != url:
            current['thumbnail_crop'] = None
        current.update(image=url, image_local=local)
        db.execute('UPDATE games SET payload=? WHERE id=?', (json.dumps(current, ensure_ascii=False), gid))
    return next(g for g in library() if g['id'] == gid)


def save_game(data, gid=None, db=None):
    record = validate(data, allowed_statuses=[x[0] for x in db.execute('SELECT name FROM categories')] if db is not None else None)
    # Download before opening a write transaction; ordinary edits reuse the archive.
    previous_image = next((g for g in library() if g['id'] == gid), {}) if gid is not None else {}
    image = record.get('image', previous_image.get('image', ''))
    old_local = previous_image.get('image_local', '')
    archived = old_local if image == previous_image.get('image') and old_local and (DATA / old_local.lstrip('/')).is_file() else ''
    if gid is None:
        archived = record.get('image_local', '')
    if image and not archived and (gid is None or image != previous_image.get('image')):
        try:
            archived = archive_cover(image)
        except (OSError, ValueError):
            pass  # The library entry still saves; the settings screen can retry.
    if 'image' in record or archived:
        record['image_local'] = archived
    own = db is None
    db = db or sqlite3.connect(DB, timeout=10)
    try:
        if gid is not None:
            row = db.execute('SELECT payload FROM games WHERE id=?', (gid,)).fetchone()
            if not row:
                raise ValueError('Игра уже удалена')
            previous = json.loads(row[0])
            record = dict(previous, **record)
            if record.get('thumbnail_crop') and record['thumbnail_crop']['image'] != record.get('image'):
                record['thumbnail_crop'] = None
            record['added_at'] = previous['added_at']
            db.execute('UPDATE games SET source_id=?,payload=? WHERE id=?', (record.get('source_id') or None, json.dumps(record, ensure_ascii=False), gid))
        else:
            if not record.get('added_at'):
                record['added_at'] = datetime.now(timezone.utc).isoformat()
            record.setdefault('platform', 'Пока неизвестно')
            record.setdefault('status', settings()['default_category'])
            record.setdefault('favorite', False)
            cursor = db.execute('INSERT INTO games(source_id,payload,manual_order) VALUES (?,?,(SELECT COALESCE(MAX(manual_order),0)+1 FROM games))', (record.get('source_id') or None, json.dumps(record, ensure_ascii=False)))
            gid = cursor.lastrowid
        if record.get('platform'):
            db.execute('INSERT OR IGNORE INTO platforms(name) VALUES (?)', (record['platform'],))
        if own:
            db.commit()
        return dict(record, id=gid, manual_order=db.execute('SELECT manual_order FROM games WHERE id=?', (gid,)).fetchone()[0])
    except Exception:
        if own:
            db.rollback()
        raise
    finally:
        if own:
            db.close()



BACKUP_LIMIT = 10

def backup_files():
    folder = DATA / 'backups'
    return sorted(folder.glob('library-*.zip'), reverse=True) if folder.exists() else []

def create_backup(automatic=False):
    folder = DATA / 'backups'
    folder.mkdir(exist_ok=True)
    today = datetime.now().strftime('%Y%m%d')
    if automatic and any(p.name.startswith('library-' + today) for p in backup_files()):
        return None
    name = 'library-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.zip'
    with tempfile.TemporaryDirectory(dir=DATA) as work:
        snapshot = Path(work) / 'library.sqlite3'
        with closing(sqlite3.connect(DB)) as source, closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
        pending = folder / (name + '.tmp')
        try:
            with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, 'library.sqlite3')
                with closing(sqlite3.connect(snapshot)) as db:
                    images = {json.loads(row[0]).get('image_local', '') for row in db.execute('SELECT payload FROM games')}
                for image in sorted(images):
                    if re.fullmatch(r'/covers/[a-f0-9]{64}\.(?:png|jpg|gif|webp)', image) and (DATA / image.lstrip('/')).is_file():
                        archive.write(DATA / image.lstrip('/'), image.lstrip('/'))
            pending.replace(folder / name)
        finally:
            pending.unlink(missing_ok=True)
    for old in backup_files()[BACKUP_LIMIT:]:
        old.unlink()
    return name

def backup_path(name):
    if not isinstance(name, str) or not re.fullmatch(r'library-\d{8}-\d{6}-\d{6}\.zip', name):
        raise ValueError('Некорректное имя копии')
    path = DATA / 'backups' / name
    if not path.is_file():
        raise ValueError('Копия не найдена')
    return path

def restore_backup(raw):
    # Read and validate the entire archive before changing the live library.
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive, tempfile.TemporaryDirectory(dir=DATA) as work:
            entries = archive.infolist()
            if len(entries)>20001 or sum(x.file_size for x in entries)>1_000_000_000:
                raise ValueError('Слишком большая копия')
            names = [x.filename for x in entries]
            if len(names)!=len(set(names)) or 'library.sqlite3' not in names or any(n!='library.sqlite3' and not re.fullmatch(r'covers/[a-f0-9]{64}\.(?:png|jpg|gif|webp)',n) for n in names):
                raise ValueError('Неизвестный формат копии')
            snapshot=Path(work)/'library.sqlite3'
            snapshot.write_bytes(archive.read('library.sqlite3'))
            with closing(sqlite3.connect(snapshot)) as source:
                if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise ValueError('Копия повреждена')
                layouts={'games':['id','source_id','payload','manual_order'],'platforms':['name'],'categories':['name','position'],'settings':['name','value']}
                rows={}
                for table,columns in layouts.items():
                    if [x[1] for x in source.execute('PRAGMA table_info('+table+')')]!=columns:
                        raise ValueError('Несовместимая копия')
                    rows[table]=source.execute('SELECT * FROM '+table).fetchall()
                categories=[r[0] for r in rows['categories']]
                if not categories: raise ValueError('В копии нет категорий')
                for row in rows['games']:
                    game=json.loads(row[2])
                    validate(game,allowed_statuses=categories)
                    image=game.get('image_local','')
                    if image and image.lstrip('/') not in names: raise ValueError('В копии отсутствует обложка')
                validate_settings({k:json.loads(v) for k,v in rows['settings'] if k in DEFAULT_SETTINGS},allowed_categories=categories)
            covers={n:archive.read(n) for n in names if n.startswith('covers/')}
            if any(hashlib.sha256(content).hexdigest()!=Path(name).stem for name,content in covers.items()):
                raise ValueError('Обложка в копии повреждена')
            create_backup()
            for name,content in covers.items():
                path=DATA/name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(content)
            with connection() as db:
                for table,columns in layouts.items():
                    db.execute('DELETE FROM '+table)
                    db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in columns)+')',rows[table])
            TRASH.clear()
    except (zipfile.BadZipFile, sqlite3.DatabaseError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Копия повреждена или имеет неизвестный формат') from exc
    return {'ok':True}

def delete_game(gid):
    now=time.monotonic()
    for key,(expires,_) in list(TRASH.items()):
        if expires<now: TRASH.pop(key,None)
    with connection() as db:
        row=db.execute('SELECT * FROM games WHERE id=?',(int(gid),)).fetchone()
        if not row: raise ValueError('Игра уже удалена')
        db.execute('DELETE FROM games WHERE id=?',(int(gid),))
    key=secrets.token_urlsafe(24)
    TRASH[key]=(now+600,row)
    return {'ok':True,'undo':key}

def undo_delete(key):
    entry=TRASH.get(key)
    if not entry or entry[0]<time.monotonic(): raise ValueError('Время отмены истекло')
    row=entry[1]
    with connection() as db:
        # A newer manually added game may already occupy the deleted ID.
        gid=row[0] if not db.execute('SELECT 1 FROM games WHERE id=?',(row[0],)).fetchone() else None
        db.execute('INSERT INTO games VALUES (?,?,?,?)',(gid,*row[1:]))
    TRASH.pop(key,None)
    return {'ok':True}

def bulk_update(data):
    ids=data.get('ids')
    patch=data.get('patch')
    if not isinstance(ids,list) or not ids or len(ids)>20000 or any(type(x)!=int for x in ids): raise ValueError('Выбери игры')
    if not isinstance(patch,dict) or not patch or set(patch)-{'status','platform','favorite'}: raise ValueError('Некорректные изменения')
    with connection() as db:
        for gid in set(ids):
            row=db.execute('SELECT payload FROM games WHERE id=?',(gid,)).fetchone()
            if not row: raise ValueError('Одна из игр уже удалена')
            game=json.loads(row[0])
            save_game(dict(title=game['title'],**patch),gid,db=db)
    return {'updated':len(set(ids))}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def reply(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            return self.reply({'error': 'Используйте локальный адрес приложения'}, 403)
        parts = urllib.parse.urlparse(self.path)
        args = urllib.parse.parse_qs(parts.query)
        try:
            if parts.path == '/api/library':
                return self.reply({'games': library(), 'platforms': platform_names(), 'categories': category_names(), 'settings': settings(), 'token': TOKEN, 'app': 'backlogame', 'data_directory': str(DATA.resolve())})
            if parts.path == '/api/backups':
                return self.reply({'limit':BACKUP_LIMIT,'items':[{'name':p.name,'size':p.stat().st_size} for p in backup_files()]})
            if parts.path == '/api/backup-download':
                path=backup_path(args.get('name',[''])[0])
                raw=path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','application/zip')
                self.send_header('Content-Disposition','attachment; filename='+path.name)
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if parts.path == '/api/search':
                return self.reply({'items': search_games(args.get('q', [''])[0], args.get('provider', ['steam'])[0], args.get('include_extras', ['0'])[0] == '1')})
            if parts.path == '/api/details':
                return self.reply(details(args.get('source', [''])[0]))
            if parts.path == '/api/export':
                return self.reply({'version': 1, 'games': library(), 'platforms': platform_names(), 'categories': category_names(), 'settings': settings()})
            if re.fullmatch(r'/covers/[a-f0-9]{64}\.(?:png|jpg|gif|webp)', parts.path):
                path = DATA / parts.path.lstrip('/')
                if not path.is_file():
                    return self.reply({'error':'Обложка не найдена'}, 404)
                raw = path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', {'.png':'image/png','.jpg':'image/jpeg','.gif':'image/gif','.webp':'image/webp'}[path.suffix])
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
                self.end_headers()
                self.wfile.write(raw)
                return
            files = {'/rutracker-icon.png':'rutracker-icon.png','/i18n.js':'i18n.js','/desktop.js':'desktop.js','/app-icon.png':'app-icon.png','/app-icon.ico':'app-icon.ico','/favicon.ico':'app-icon.ico','/': 'index.html', '/app.js': 'app.js', '/enhancements.js': 'enhancements.js', '/thumbnail.js': 'thumbnail.js', '/style.css': 'style.css'}
            if parts.path not in files:
                return self.reply({'error': 'Не найдено'}, 404)
            path = ROOT / 'static' / files[parts.path]
            raw = path.read_bytes()
            self.send_response(200)
            mime = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css', 'png':'image/png', 'ico':'image/vnd.microsoft.icon'}[path.suffix[1:]]
            self.send_header('Content-Type', mime + ('; charset=utf-8' if path.suffix in ('.html','.js','.css') else ''))
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' https: http: data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)
        except ValueError as exc:
            self.reply({'error': str(exc)[:300]}, 502)
        except (OSError, KeyError):
            self.reply({'error': 'Каталог недоступен или не вернул сведения. Попробуйте позже; ручное добавление работает без интернета.'}, 502)

    def do_POST(self):
        with MUTATION_LOCK:
            self._post()

    def _post(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            return self.reply({'error': 'Используйте локальный адрес приложения'}, 403)
        if self.headers.get('X-Library-Token') != TOKEN:
            return self.reply({'error': 'Обновите страницу приложения'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if self.path == '/api/backup-upload':
                if length<=0 or length>200_000_000: raise ValueError('Максимальный размер копии — 200 МБ')
                return self.reply(restore_backup(self.rfile.read(length)))
            if length > 10_000_000:
                raise ValueError('Файл больше 10 МБ')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Ожидался объект JSON')
            if self.path == '/api/desktop-close' and getattr(self.server,'desktop_close',None):
                self.server.desktop_close()
                return self.reply({'ok':True})
            if self.path == '/api/desktop-smoke' and getattr(self.server,'desktop_smoke',None):
                self.server.desktop_smoke(data)
                return self.reply({'ok':True})
            if self.path == '/api/backup-create':
                return self.reply({'name':create_backup()})
            if self.path == '/api/backup-restore':
                return self.reply(restore_backup(backup_path(data.get('name')).read_bytes()))
            if self.path in ('/api/save','/api/bulk','/api/delete','/api/undo-delete','/api/reorder','/api/settings','/api/platforms','/api/categories','/api/import','/api/covers/cache','/api/covers/refresh'):
                create_backup(automatic=True)
            if self.path == '/api/bulk':
                return self.reply(bulk_update(data))
            if self.path == '/api/undo-delete':
                return self.reply(undo_delete(data.get('undo')))
            if self.path == '/api/save':
                return self.reply(save_game(data['game'], data.get('id')))
            if self.path in ('/api/covers/cache', '/api/covers/refresh'):
                return self.reply(update_cover(data['id'], steam=self.path.endswith('/refresh')))
            if self.path == '/api/reorder':
                reorder_game(data['id'], data['target'], data.get('after', False))
                return self.reply({'ok': True})
            if self.path == '/api/settings':
                values = validate_settings(data)
                with connection() as db:
                    db.executemany('INSERT OR REPLACE INTO settings(name,value) VALUES (?,?)', [(k,json.dumps(v,ensure_ascii=False)) for k,v in values.items()])
                return self.reply(settings())
            if self.path == '/api/platforms':
                manage_platform(data)
                return self.reply({'ok': True})
            if self.path == '/api/categories':
                manage_category(data)
                return self.reply({'ok': True})
            if self.path == '/api/delete':
                return self.reply(delete_game(data['id']))
            if self.path == '/api/import':
                if data.get('version') != 1 or not isinstance(data.get('games'), list) or len(data['games']) > 20000:
                    raise ValueError('Неизвестный формат библиотеки')
                # Validate before mutating; all imported rows share one transaction.
                categories = data.get('categories', [])
                if not isinstance(categories,list) or any(not isinstance(x,str) or not x.strip() or len(x)>100 or x in ('favorites','not-favorites','Все игры') for x in categories):
                    raise ValueError('Некорректные категории')
                allowed = list(dict.fromkeys(category_names() + categories))
                games = [validate(x, allowed_statuses=allowed) for x in data['games']]
                platforms = data.get('platforms', [])
                preferences = validate_settings(data.get('settings', {}), allowed_categories=allowed)
                if not isinstance(platforms, list) or any(not isinstance(x, str) or not x.strip() or len(x) > 300 for x in platforms):
                    raise ValueError('Некорректный список платформ')
                added = skipped = 0
                with connection() as db:
                    for name in categories:
                        db.execute('INSERT OR IGNORE INTO categories VALUES (?,(SELECT COALESCE(MAX(position),0)+1 FROM categories))',(name,))
                    db.executemany('INSERT OR REPLACE INTO settings(name,value) VALUES (?,?)', [(k,json.dumps(v,ensure_ascii=False)) for k,v in preferences.items()])
                    for platform in platforms:
                        db.execute('INSERT OR IGNORE INTO platforms(name) VALUES (?)', (platform.strip(),))
                    for game in games:
                        if game.get('source_id') and db.execute('SELECT 1 FROM games WHERE source_id=?', (game['source_id'],)).fetchone():
                            skipped += 1
                            continue
                        save_game(game, db=db)
                        added += 1
                return self.reply({'added': added, 'skipped': skipped})
            return self.reply({'error': 'Не найдено'}, 404)
        except sqlite3.IntegrityError:
            self.reply({'error': 'Эта игра уже есть в библиотеке'}, 409)
        except (ValueError, KeyError, TypeError) as exc:
            self.reply({'error': str(exc)}, 400)
        except urllib.error.HTTPError as exc:
            message = 'Источник временно ограничил загрузку. Повторите сохранение обложек позже.' if exc.code == 429 else 'Источник не отдал обложку или сведения (HTTP ' + str(exc.code) + '). Сохранённая копия остаётся.'
            self.reply({'error':message, 'upstream_status':exc.code}, 502)
        except OSError as exc:
            self.reply({'error': 'Не удалось выполнить запрос. Проверьте соединение и повторите.', 'detail': str(exc)[:200]}, 502)


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        # Windows otherwise permits multiple servers to bind the same address.
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def configure_data(directory=None):
    global DATA, DB
    DATA=(Path(directory) if directory else user_data_directory()).resolve()
    DATA.mkdir(parents=True, exist_ok=True)
    DB=DATA/'library.sqlite3'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--data-dir',type=Path)
    args = parser.parse_args()
    configure_data(args.data_dir)
    init_db()
    try:
        server = LocalServer(('127.0.0.1', args.port), Handler)
    except OSError:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/library', timeout=2) as response:
                if json.load(response).get('app') == 'backlogame':
                    if not args.no_browser:
                        webbrowser.open(f'http://127.0.0.1:{args.port}')
                    print('BackloGame is already running.')
                    return
        except (OSError, ValueError):
            pass
        print('Port is busy. Choose another: python server.py --port 8766')
        return
    address = f'http://127.0.0.1:{args.port}'
    print(f'BackloGame: {address}\nLibrary: {DB}\nCtrl+C to stop.')
    if not args.no_browser:
        threading.Timer(.6, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
