"""Explicit, reversible merges of two local game cards."""
import hashlib
import json
import secrets
import time

UNDO = {}


def preview(store, data):
    ids = data.get('ids')
    if not isinstance(ids,list) or len(ids)!=2 or any(type(x)!=int for x in ids) or len(set(ids))!=2:
        raise ValueError('Select exactly two games')
    library = store.library()
    selected = [next((g for g in library if g['id']==gid),None) for gid in ids]
    if any(g is None for g in selected):raise ValueError('A selected game no longer exists')
    primary = next((g for g in selected if g['id']==data.get('primary',ids[0])),None)
    current = next((g for g in selected if g['id']==data.get('current',ids[1])),None)
    if not primary or not current:raise ValueError('Invalid merge selection')
    other = next(g for g in selected if g['id']!=primary['id'])
    merged = dict(primary,platform=current.get('platform','Пока неизвестно'),status=current['status'])
    for field in ('description','genre','release_date','release_label','developer','original_title'):
        if not merged.get(field) and other.get(field):merged[field]=other[field]
    if not (merged.get('image') or merged.get('image_local')):
        for field in ('image','image_local','thumbnail_crop'):
            if field in other:merged[field]=other[field]
    for field, separator in [('tags',','),('series',';')]:
        merged[field] = (separator+' ').join(dict.fromkeys(x.strip() for g in selected for x in (g.get(field) or '').split(separator) if x.strip()))
    merged['notes']='\n\n'.join(dict.fromkeys(g['notes'] for g in selected if g.get('notes')))
    merged['favorite']=any(g.get('favorite') for g in selected)
    merged['custom_covers']=dict(other.get('custom_covers',{}),**primary.get('custom_covers',{}))
    merged['playthroughs']=store.merge_playthroughs(*(store.playthroughs(g) for g in selected))
    merged=store.with_completion_dates(merged)
    merged['source_aliases']=list(dict.fromkeys(x for g in selected for x in [g.get('source_id'),*g.get('source_aliases',[])] if x))
    entries={str(row.get('id') or json.dumps(row,sort_keys=True)):row for g in selected for row in g.get('hltb_entries',[])}
    if entries:merged['hltb_entries']=list(entries.values())
    for field in ('hltb_game_id','hltb_url','hltb_updated_at'):
        if not merged.get(field) and other.get(field):merged[field]=other[field]
    # Preserve all conflicting metadata and references without recursively nesting archives.
    archive=[]
    for game in selected:
        archive.extend(game.get('merge_archive',[]))
        archive.append({k:v for k,v in game.items() if k!='merge_archive'})
    if len(archive)>100:raise ValueError('Merge archive is too large')
    merged['merge_archive']=archive
    store.validate(merged)
    signature=hashlib.sha256(json.dumps(selected,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'game':merged,'signature':signature,'removed':other['id']}


def apply(store,data):
    result=preview(store,data)
    if data.get('signature')!=result['signature']:raise ValueError('The games changed. Review the preview again.')
    store.create_backup()
    game=result['game']
    with store.connection() as db:
        original=db.execute('SELECT * FROM games WHERE id IN (?,?)',data['ids']).fetchall()
        db.execute('DELETE FROM games WHERE id=?',(result['removed'],))
        payload={k:v for k,v in game.items() if k not in ('id','manual_order')}
        db.execute('UPDATE games SET source_id=?,payload=? WHERE id=?',(game.get('source_id') or None,json.dumps(payload,ensure_ascii=False),game['id']))
    key=secrets.token_urlsafe(24)
    for expired,(until,*_) in list(UNDO.items()):
        if until<time.monotonic():UNDO.pop(expired,None)
    if len(UNDO)>=20:UNDO.pop(next(iter(UNDO)))
    UNDO[key]=(time.monotonic()+600,original,game['id'],payload,str(store.DB))
    return {'id':game['id'],'undo':key}


def undo(store,data):
    key=data.get('undo');entry=UNDO.get(key)
    if not entry or entry[0]<time.monotonic():raise ValueError('Undo expired. Restore the backup instead.')
    _,original,gid,expected,database=entry
    if database!=str(store.DB):raise ValueError('Undo belongs to another library')
    with store.connection() as db:
        now=db.execute('SELECT payload FROM games WHERE id=?',(gid,)).fetchone()
        if not now or json.loads(now[0])!=expected:raise ValueError('The merged game was edited. Restore the backup instead.')
        if any(row[0]!=gid and db.execute('SELECT 1 FROM games WHERE id=?',(row[0],)).fetchone() for row in original):raise ValueError('A game ID is already in use')
        db.execute('DELETE FROM games WHERE id=?',(gid,))
        db.executemany('INSERT INTO games VALUES (?,?,?,?)',original)
    UNDO.pop(key,None)
    return {'ok':True}
