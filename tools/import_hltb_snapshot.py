"""Import a public HLTB snapshot into an explicitly selected portable database.

One card per title/platform; keep every playthrough in hltb_entries. Existing
cards retain their source ID, notes, favorites, cover and manual order.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from library_sync import hltb_game, identity


def release(value):
    value = str(value or '')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) or value.startswith('0000'):
        return ''
    value = value[:4] if value[5:7] == '00' else value[:7] if value[8:] == '00' else value
    datetime.fromisoformat(value + ('-01-01' if len(value) == 4 else '-01' if len(value) == 7 else ''))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    server.DATA = args.data_dir.resolve()
    server.DB = server.DATA / 'library.sqlite3'
    if not server.DB.is_file():
        raise ValueError('The destination database does not exist')
    rows = json.loads(args.snapshot.read_text(encoding='utf-8'))['games']
    groups = defaultdict(list)
    for row in rows:
        converted = hltb_game(row)
        groups[(converted['title'], converted['platform'])].append(row)
    old_by_pair = defaultdict(list)
    for game in server.library():
        old_by_pair[identity(game)].append(game)
    for title, platform in groups:
        if len(old_by_pair[identity({'title': title, 'platform': platform})]) > 1:
            raise ValueError('Ambiguous existing title/platform; resolve before import')
    matches = sum(bool(old_by_pair[identity({'title': t, 'platform': p})]) for t, p in groups)
    print(json.dumps({'records': len(rows), 'cards': len(groups), 'matched': matches,
                      'new': len(groups)-matches, 'apply': args.apply}), flush=True)
    if not args.apply:
        return
    backup = server.create_backup(automatic=False)
    print('Backup: ' + backup, flush=True)
    images = {}
    for (title, platform), entries in groups.items():
        old = old_by_pair.get(identity({'title': title, 'platform': platform}))
        if not old:
            image = hltb_game(entries[-1])['image']
            if image:
                images[image] = ''
    failures = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(server.archive_cover, image): image for image in images}
        for count, future in enumerate(as_completed(futures), 1):
            try:
                images[futures[future]] = future.result()
            except (OSError, ValueError):
                failures += 1
            if count % 50 == 0 or count == len(futures):
                print(f'Covers: {count}/{len(futures)}; unavailable: {failures}', flush=True)
    # All writes happen in one transaction. Re-read each existing payload here,
    # preserving edits made while covers were downloading.
    added = moved = 0
    with server.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO categories VALUES (?,(SELECT COALESCE(MAX(position),0)+1 FROM categories))', ('HLTB',))
        current = defaultdict(list)
        for gid, payload in db.execute('SELECT id,payload FROM games'):
            game = json.loads(payload)
            current[identity(game)].append((gid, game))
        order = db.execute('SELECT COALESCE(MAX(manual_order),0) FROM games').fetchone()[0]
        for (title, platform), entries in groups.items():
            entries = sorted(entries, key=lambda r: (str(r.get('date_updated') or ''), str(r.get('id') or '')))
            latest = entries[-1]
            converted = hltb_game(latest)
            pair = identity(converted)
            matches = current.get(pair, [])
            if len(matches) > 1:
                raise ValueError('Ambiguous title/platform after concurrent edit')
            old = matches[0][1] if matches else None
            if old:
                game = dict(old)
                if game.get('status') != 'HLTB':
                    game['hltb_previous_status'] = game.get('status', '')
            else:
                game = dict(converted, favorite=False)
                dates = [str(r.get('date_added') or '') for r in entries if r.get('date_added')]
                game['added_at'] = min(dates) if dates else datetime.now().isoformat()
                image = game.get('image', '')
                game['image_local'] = images.get(image, '')
            game.update(status='HLTB', hltb_entries=entries, hltb_game_id=str(latest.get('game_id') or ''),
                        hltb_url=converted['source_url'], sync_status=converted['sync_status'],
                        sync_added_at=converted['sync_added_at'],
                        hltb_updated_at=str(latest.get('date_updated') or ''))
            dates = [str(r.get('date_complete') or '') for r in entries
                     if r.get('date_complete') and not str(r['date_complete']).startswith('0000')]
            if dates:
                game['completed_at'] = max(dates)
            if not game.get('release_date'):
                game['release_date'] = release(latest.get('release_world'))
            payload = json.dumps(game, ensure_ascii=False)
            if old:
                db.execute('UPDATE games SET payload=? WHERE id=?', (payload, matches[0][0]))
                moved += 1
            else:
                order += 1
                cursor = db.execute('INSERT INTO games(source_id,payload,manual_order) VALUES (?,?,?)',
                                    (game['source_id'], payload, order))
                current[pair].append((cursor.lastrowid, game))
                added += 1
            db.execute('INSERT OR IGNORE INTO platforms(name) VALUES (?)', (game['platform'],))
    imported = [g for g in server.library() if g.get('status') == 'HLTB']
    assert len(imported) == len(groups)
    assert sum(len(g['hltb_entries']) for g in imported) == len(rows)
    with server.connection() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    print(json.dumps({'added': added, 'moved': moved, 'hltb_category': len(imported),
                      'playthroughs': sum(len(g['hltb_entries']) for g in imported),
                      'total_library': len(server.library()), 'cover_failures': failures}), flush=True)


if __name__ == '__main__':
    main()
