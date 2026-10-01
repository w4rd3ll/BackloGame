"""Redistribute the earlier HLTB import; preserve its source as a tag."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from library_sync import status, checked

def migrate(data_dir):
    server.DATA = Path(data_dir).resolve()
    server.DB = server.DATA/'library.sqlite3'
    if not server.DB.exists(): raise ValueError('Database not found')
    backup=server.create_backup(automatic=False)
    changed=0
    with server.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        for name in ('Бэклог','Играю','Пройдено','Брошено'):
            db.execute('INSERT OR IGNORE INTO categories VALUES (?,(SELECT COALESCE(MAX(position),0)+1 FROM categories))',(name,))
        for gid,payload in db.execute('SELECT id,payload FROM games').fetchall():
            game=json.loads(payload)
            if game.get('status')!='HLTB' or not game.get('hltb_entries'):continue
            entries=game['hltb_entries']
            latest=max(entries,key=lambda r:str(r.get('date_updated') or ''))
            game['status']=status(latest)
            tags=[x.strip() for x in game.get('tags','').split(',') if x.strip()]+['HLTB']
            if any(checked(r.get('list_replay')) for r in entries):tags.append('Повторное прохождение')
            game['tags']=', '.join(dict.fromkeys(tags))
            dates=[str(r['date_complete'])[:10] for r in entries if r.get('date_complete') and not str(r['date_complete']).startswith('0000')]
            if dates:game['completed_at']=max(dates)
            db.execute('UPDATE games SET payload=? WHERE id=?',(json.dumps(game,ensure_ascii=False),gid))
            changed+=1
        if not any(json.loads(p).get('status')=='HLTB' for p, in db.execute('SELECT payload FROM games')):
            db.execute('DELETE FROM categories WHERE name=?',('HLTB',))
            row=db.execute('SELECT value FROM settings WHERE name=?',('hidden_categories',)).fetchone()
            if row:db.execute('UPDATE settings SET value=? WHERE name=?',(json.dumps([x for x in json.loads(row[0]) if x!='HLTB']),'hidden_categories'))
    print(json.dumps({'migrated':changed,'backup':backup}))

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: migrate_hltb_statuses.py DATA_DIR')
    migrate(sys.argv[1])
