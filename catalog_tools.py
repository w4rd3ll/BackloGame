"""Catalog enrichment without replacing a game's progress or source identity."""
import re


def key(store, title):
    title = re.sub(r'\((\d{4}) (?:video|computer) game\)',r'(\1)',title,flags=re.I)
    title = re.sub(r'\((?:video|computer) game\)','',title,flags=re.I)
    return store.title_key(title)


def find_series(store, game):
    """Only accept an exact game article with a declared Wikidata series."""
    qid=game.get('qid')
    appid=next((source.split(':')[1] for source in [game.get('source_id'),*game.get('source_aliases',[])] if source and re.fullmatch(r'steam:\d+',source)),None)
    candidates=[game] if qid else store.search_games(game.get('original_title') or game['title'],'wikipedia')
    for item in candidates[:8]:
        if not item.get('qid'):continue
        titles={key(store,game['title']),key(store,game.get('original_title') or game['title'])}
        base=lambda title:key(store,re.sub(r'\(\d{4}(?: (?:video|computer) game)?\)','',title,flags=re.I))
        matching_title=key(store,item['title']) in titles or base(item['title']) in {base(game['title']),base(game.get('original_title') or game['title'])}
        if not qid and not matching_title and not appid:continue
        data=store.entity(item['qid'])
        # Platform and/or Steam ID claims distinguish games from films and series.
        if not store.claims(data,'P400') and not store.claims(data,'P1733'):continue
        steam_ids=store.claims(data,'P1733')
        if appid and steam_ids and appid not in steam_ids:continue
        if not qid and not matching_title and not (appid and appid in steam_ids):continue
        if not qid and key(store,item['title']) not in titles:
            expected=re.search(r'\((\d{4})\)',game['title'])
            expected=expected[1] if expected else (game.get('release_date') or '')[:4]
            candidate=re.search(r'\((\d{4})',item['title'])
            if not (appid and appid in steam_ids) and (not expected or not candidate or candidate[1]!=expected):continue
        series=store.claims(data,'P179')
        if series:
            names=[store.label(store.entity(row['id'])) for row in series]
            return {'series':'; '.join(dict.fromkeys(names)),'qid':item['qid'],'series_qid':series[0]['id']}
    return {}


def enriched_details(store, source):
    game=store.details(source)
    if not game.get('series'):
        try:game.update(find_series(store,game))
        except (OSError,ValueError,KeyError):pass
    return game


def existing(store,gid):
    if type(gid)!=int:raise ValueError('Invalid game ID')
    game=next((g for g in store.library() if g['id']==gid),None)
    if not game:raise ValueError('Игра уже удалена')
    return game


def apply(store,data):
    if 'fields' in data:return apply_fields(store,data)
    old=existing(store,data.get('id'))
    mode=data.get('mode','metadata')
    if mode not in ('metadata','cover','series'):raise ValueError('Invalid update mode')
    orientation=data.get('orientation')
    if orientation is not None and (mode!='cover' or orientation not in ('portrait','landscape')):raise ValueError('Invalid artwork orientation')
    fresh=find_series(store,old) if mode=='series' else store.details(data.get('source','')) if mode=='cover' else enriched_details(store,data.get('source',''))
    if mode=='series' and not fresh.get('series'):return {'game':old,'changed':False}
    patch={'title':old['title']}
    if mode in ('metadata','cover'):
        if not fresh.get('image') and mode=='cover':raise ValueError('У игры нет обложки')
        if fresh.get('image'):
            # Fail before changing metadata if the alternative cover cannot be archived.
            local=store.archive_cover(fresh['image'])
            if orientation:
                covers=dict(old.get('custom_covers',{}));covers[orientation]={'url':fresh['image'],'local':local,'author':'','asset':None}
                patch['custom_covers']=covers
                if orientation=='landscape':patch['thumbnail_crop']=None
            else:patch.update(image=fresh['image'],image_local=local)
        aliases=list(dict.fromkeys([*old.get('source_aliases',[]),old.get('source_id'),fresh.get('source_id')]))
        patch['source_aliases']=[value for value in aliases if value]
    if mode=='metadata':
        for field in ('description','description_language','description_url','genre','developer','available_platforms','release_date','release_label','original_title','qid'):
            if fresh.get(field):patch[field]=fresh[field]
        patch['description_url']=fresh.get('description_url') or fresh.get('source_url','')
    # Handwritten and multiple-series values always win.
    if store.has_no_series(old.get('series')) and fresh.get('series'):
        patch.update({field:fresh[field] for field in ('series','series_qid','qid') if fresh.get(field)})
    with store.MUTATION_LOCK:
        current=existing(store,old['id'])
        if current!=old:raise ValueError('The game changed. Try again.')
        store.create_backup(automatic=True)
        saved=store.save_game(patch,old['id'])
    return {'game':saved,'changed':True}


def apply_fields(store,data):
    """One atomic save of explicitly selected fields from several catalogs."""
    old=existing(store,data.get('id'))
    fields=data.get('fields')
    allowed={'title','description','genre','developer','available_platforms','release_date','series','image'}
    if data.get('mode','metadata')!='metadata' or not isinstance(fields,dict) or not fields or set(fields)-allowed:
        raise ValueError('Invalid catalog field selection')
    if any(not isinstance(source,str) or not re.fullmatch(r'(?:steam|metacritic|wiki):[^\s]{1,500}',source) for source in fields.values()):
        raise ValueError('Invalid catalog source')
    fresh={source:enriched_details(store,source) for source in dict.fromkeys(fields.values())}
    patch={'title':old['title']}
    for field,source in fields.items():
        item=fresh[source]
        value=item.get(field)
        if not value and not (field=='release_date' and item.get('release_label')):
            raise ValueError('Selected catalog field is empty')
        if field=='image':
            patch.update(image=value,image_local=store.archive_cover(value))
            if old.get('custom_covers',{}).get('portrait'):
                patch['custom_covers']=dict(old['custom_covers'],portrait={'url':value,'local':patch['image_local'],'author':'','asset':None})
        elif field=='description':
            patch.update(description=value,description_language=item.get('description_language',''),description_url=item.get('description_url') or item.get('source_url',''))
        elif field=='release_date':
            patch.update(release_date=value or '',release_label=item.get('release_label',''))
        elif field=='series':
            patch.update(series=value,series_qid=item.get('series_qid',''))
            if item.get('qid'):patch['qid']=item['qid']
        elif field=='title':
            patch.update(title=value,original_title=item.get('original_title') or value)
        else:patch[field]=value
    patch['source_aliases']=list(dict.fromkeys(value for value in [*old.get('source_aliases',[]),old.get('source_id'),*fresh] if value))
    with store.MUTATION_LOCK:
        if existing(store,old['id'])!=old:raise ValueError('The game changed. Try again.')
        store.create_backup(automatic=True)
        saved=store.save_game(patch,old['id'])
    return {'game':saved,'changed':True}


def automatic(store,data):
    old=existing(store,data.get('id'))
    if data.get('mode')=='series':
        if not store.has_no_series(old.get('series')):return {'game':old,'changed':False}
        return apply(store,dict(data,mode='series'))
    provider=data.get('provider','metacritic')
    if provider=='auto':
        error=None
        for candidate in ('steam','metacritic','wikipedia'):
            try:
                result=automatic(store,dict(data,provider=candidate))
                if result['changed']:return result
            except (OSError,ValueError,KeyError) as exc:error=exc
        if error:raise ValueError('Каталоги не вернули доступную обложку. Попробуй выбрать вручную.')
        return {'game':old,'changed':False}
    if provider not in ('steam','metacritic','wikipedia'):raise ValueError('Неизвестный каталог игр')
    prefix={'steam':'steam:','metacritic':'metacritic:','wikipedia':'wiki:'}[provider]
    known=[source for source in [old.get('source_id'),*old.get('source_aliases',[])] if source and source.startswith(prefix)]
    sources=known[:1]
    if not sources:
        items=store.search_games(old.get('original_title') or old['title'],provider)
        exact=[item for item in items if key(store,item['title']) in {key(store,old['title']),key(store,old.get('original_title') or old['title'])}]
        if len(exact)!=1:return {'game':old,'changed':False}
        sources=[exact[0]['source_id']]
    return apply(store,dict(data,mode='cover',source=sources[0]))
