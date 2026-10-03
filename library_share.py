"""A self-contained, read-only HTML list for sharing selected library games."""
import base64
from datetime import date
from html import escape
import io
import re
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

SHARE_COVER_SIZE = (224, 300)
SHARE_COVER_QUALITY = 65


LABELS = {
    'ru': {'games':'Игр', 'platform':'Платформа', 'status':'Статус',
           'series':'Серия', 'genre':'Жанр', 'completed':'Пройдено',
           'released':'Выход', 'notes':'Заметка', 'unknown':'Не указана',
           'footer':'Список создан в BackloGame', 'empty':'Без обложки'},
    'en': {'games':'Games', 'platform':'Platform', 'status':'Status',
           'series':'Series', 'genre':'Genre', 'completed':'Completed',
           'released':'Released', 'notes':'Note', 'unknown':'Not specified',
           'footer':'Created with BackloGame', 'empty':'No cover'},
}
VALUES = {'Хочу пройти':'Want to play', 'Играю':'Playing', 'Перепрохожу':'Replaying',
          'Пройдено':'Completed', 'Бэклог':'Backlog', 'Отложено':'On hold',
          'Брошено':'Retired', 'Пока неизвестно':'Unknown', 'Без серии':'No series'}
CSS = """
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#10171c;color:#edf3f6;font:15px/1.5 'Segoe UI',system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:48px 24px}header{margin-bottom:32px;border-bottom:1px solid #2a3943;padding-bottom:24px}.brand{color:#50c8bd;font-weight:700;letter-spacing:.04em;font-size:13px}
h1{font-size:clamp(26px,5vw,42px);line-height:1.2;margin:12px 0;overflow-wrap:anywhere}.summary,footer{color:#9cabb6;font-size:13px}
.games{display:grid;gap:12px}.game{display:flex;gap:20px;background:#19242c;border:1px solid #2a3943;border-radius:12px;overflow:hidden;align-items:center;padding:14px}
.cover{width:112px;height:150px;object-fit:contain;border-radius:7px;background:#10171c;flex-shrink:0}.missing{display:flex;align-items:center;justify-content:center;color:#9cabb6;font-size:12px;text-align:center;padding:12px}
.body{min-width:0;flex:1}h2{font-size:19px;margin:0 0 10px;overflow-wrap:anywhere}.badges{display:flex;flex-wrap:wrap;gap:7px}.badge{border:1px solid #36515f;border-radius:6px;padding:3px 9px;font-size:12px}.status{color:#77d8cf}.done{color:#b6bdfb}.playing{color:#8fe0a3}
.details{display:flex;gap:6px 20px;flex-wrap:wrap;color:#b9c6ce;font-size:12px;margin:10px 0 0}.details span{overflow-wrap:anywhere}.note{white-space:pre-wrap;font-size:13px;color:#b9c6ce;border-top:1px solid #2a3943;margin:12px 0 0;padding-top:10px;overflow-wrap:anywhere}footer{margin-top:28px}
@media(max-width:550px){main{padding:28px 14px}.game{gap:12px;padding:10px}.cover{width:76px;height:104px}h2{font-size:16px}.details{gap:4px 12px}}
@media print{body{background:white;color:#17242c}.game{background:white;break-inside:avoid}.summary,footer,.details,.note{color:#43515a}.status{color:#14645d}.done{color:#41479c}.playing{color:#23733f}}
"""


def compressed_cover(raw):
    """A retina-sized WebP thumbnail; no original file or metadata is retained."""
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as source:
            source.seek(0)  # Animated artwork becomes a single still image.
            source.thumbnail(SHARE_COVER_SIZE, Image.Resampling.LANCZOS)
            image = ImageOps.exif_transpose(source)
            image.thumbnail(SHARE_COVER_SIZE, Image.Resampling.LANCZOS)
            mode = 'RGBA' if image.mode in ('RGBA', 'LA') or 'transparency' in image.info else 'RGB'
            image = image.convert(mode)
            image.info.clear()
            output = io.BytesIO()
            image.save(output, format='WEBP', quality=SHARE_COVER_QUALITY, method=4)
    return 'data:image/webp;base64,' + base64.b64encode(output.getvalue()).decode('ascii')


def local_cover(store, game, cache=None):
    cache = {} if cache is None else cache
    candidates = [game.get('custom_covers', {}).get('portrait', {}).get('local'),
                  game.get('image_local'), game.get('custom_covers', {}).get('landscape', {}).get('local')]
    for value in candidates:
        if isinstance(value, str) and value in cache:
            if cache[value]:
                return cache[value]
            continue
        if not isinstance(value, str) or not re.fullmatch(r'/covers/[a-f0-9]{64}\.(png|jpg|gif|webp)', value):
            continue
        path = (store.DATA / value.lstrip('/')).resolve()
        if not path.is_relative_to(store.DATA.resolve()) or not path.is_file():
            continue
        if path.stat().st_size > 128 * 1024 * 1024:
            continue
        try:
            encoded = compressed_cover(path.read_bytes())
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            cache[value] = ''
            continue
        cache[value] = encoded
        return encoded
    return ''


def export(store, data):
    ids = data.get('ids')
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10000 or any(type(gid) is not int for gid in ids):
        raise ValueError('Invalid shared game selection')
    title = data.get('title')
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError('Invalid shared list title')
    language = data.get('language', 'en')
    if not isinstance(language, str) or language not in LABELS or any(type(data.get(option, default)) is not bool for option, default in [('covers', True), ('notes', False)]):
        raise ValueError('Invalid sharing options')
    games = {game['id']: game for game in store.library()}
    selected = list(dict.fromkeys(ids))
    if any(gid not in games for gid in selected):
        raise ValueError('A selected game was deleted. Reopen the sharing dialog.')
    labels = LABELS[language]
    def value(text):
        return escape(VALUES.get(text, text) if language == 'en' else text)
    rows = []
    cover_cache = {}
    missing = 0
    for gid in selected:
        game = games[gid]
        image = local_cover(store, game, cover_cache) if data.get('covers', True) else ''
        if data.get('covers', True) and not image:
            missing += 1
        cover = f'<img class="cover" src="{image}" alt="">' if image else f'<div class="cover missing">{labels["empty"]}</div>' if data.get('covers', True) else ''
        status = game.get('status', '')
        tone = 'done' if status == 'Пройдено' else 'playing' if status in ('Играю', 'Перепрохожу') else ''
        details = []
        for field, label in [('series','series'), ('genre','genre'), ('release_date','released')]:
            if game.get(field):
                details.append(f'<span>{labels[label]}: {value(game[field])}</span>')
        completed = max(store.completion_dates(game), default='')
        if completed:
            details.append(f'<span>{labels["completed"]}: {escape(completed)}</span>')
        note = f'<p class="note">{escape(game["notes"])}</p>' if data.get('notes', False) and game.get('notes') else ''
        rows.append(f'<article class="game">{cover}<div class="body"><h2>{escape(game["title"])}</h2><div class="badges"><span class="badge">{value(game.get("platform") or "Пока неизвестно")}</span><span class="badge status {tone}">{value(status)}</span></div><div class="details">{"".join(details)}</div>{note}</div></article>')
    title = title.strip()
    document = f'<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'"><title>{escape(title)} — BackloGame</title><style>{CSS}</style></head><body><main><header><div class="brand">backloGGame</div><h1>{escape(title)}</h1><div class="summary">{labels["games"]}: {len(selected)} · {date.today().isoformat()}</div></header><section class="games">{"".join(rows)}</section><footer>{labels["footer"]}</footer></main></body></html>'
    filename = re.sub(r'[^\w-]+', '-', title, flags=re.UNICODE).strip('-')[:80] or 'games'
    return {'html':document, 'filename':f'BackloGame-{filename}-{date.today().isoformat()}.html', 'count':len(selected), 'missing_covers':missing}
