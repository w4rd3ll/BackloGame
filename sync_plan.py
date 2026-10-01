"""Side-effect-free HLTB status reconciliation; transport is handled separately.

Links carry the statuses last acknowledged on each side. A preview never updates
these baselines: acknowledge only after the corresponding write succeeds.
"""
from collections import defaultdict

from library_sync import identity


def plan(local_games, remote_games, links):
    local = {str(g['id']): g for g in local_games}
    remote = {str(g['sync_key']): g for g in remote_games}
    linked_local, linked_remote = set(), set()
    changes = []
    for link in links:
        lid, rid = str(link['local_id']), str(link['remote_id'])
        if lid in linked_local or rid in linked_remote:
            raise ValueError('Duplicate synchronization link')
        linked_local.add(lid)
        linked_remote.add(rid)
        left, right = local.get(lid), remote.get(rid)
        change = {'local_id': lid, 'remote_id': rid}
        if left is None or right is None:
            # Removing a game on one side must not silently delete the other.
            changes.append(dict(change, action='missing', missing='local' if left is None else 'remote'))
            continue
        ls, rs = left['status'], right['status']
        if ls == rs:
            action = 'equal'
        elif 'local_status' not in link or 'remote_status' not in link:
            action = 'conflict'
        else:
            lc, rc = ls != link['local_status'], rs != link['remote_status']
            action = 'conflict' if lc == rc else ('push' if lc else 'pull')
        changes.append(dict(change, action=action, local_status=ls, remote_status=rs))

    left_by_title, right_by_title = defaultdict(list), defaultdict(list)
    for lid, game in local.items():
        if lid not in linked_local:
            left_by_title[identity(game)].append(lid)
    for rid, game in remote.items():
        if rid not in linked_remote:
            right_by_title[identity(game)].append(rid)
    for pair, rids in right_by_title.items():
        lids = left_by_title.get(pair, [])
        if len(lids) == len(rids) == 1:
            lid, rid = lids[0], rids[0]
            changes.append({'action': 'link', 'local_id': lid, 'remote_id': rid,
                            'local_status': local[lid]['status'], 'remote_status': remote[rid]['status']})
            linked_local.add(lid)
        elif lids or len(rids) > 1:
            changes.append({'action': 'ambiguous', 'local_ids': lids, 'remote_ids': rids})
            linked_local.update(lids)
        else:
            changes.append({'action': 'local_add', 'remote_id': rids[0]})
    for lid in local:
        if lid not in linked_local:
            # A Steam ID/title is not an HLTB catalog ID. Search and confirm the
            # catalog match before offering to create a remote playthrough.
            changes.append({'action': 'match_required', 'local_id': lid})
    return changes
