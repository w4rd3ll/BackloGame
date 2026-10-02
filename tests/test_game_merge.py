import json
from pathlib import Path
import tempfile
import unittest
import time
from unittest.mock import patch
import server
import game_merge
from library_sync import Manager, hltb_game


class GameMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.patches=[patch.object(server,'DATA',root),patch.object(server,'DB',root/'library.sqlite3')]
        for item in self.patches:item.start()
        server.init_db()
        server.manage_category({'action':'add','name':'Бэклог'})
        self.first=server.save_game({'title':'Alone in the Dark (2008)','source_id':'hltb:123','platform':'PS3','status':'Пройдено','completed_at':'2019-06-14','notes':'Old note','favorite':True,'description':'PS3 description','tags':'HLTB'})
        self.second=server.save_game({'title':'Alone in the Dark (2008)','source_id':'steam:259170','platform':'PC - Steam','status':'Бэклог','notes':'New note','tags':'Steam'})
        self.data={'ids':[self.first['id'],self.second['id']],'primary':self.first['id'],'current':self.second['id']}

    def tearDown(self):
        game_merge.UNDO.clear()
        for item in self.patches:item.stop()
        self.temp.cleanup()

    def merge(self):
        preview=game_merge.preview(server,self.data)
        return game_merge.apply(server,dict(self.data,signature=preview['signature']))

    def test_merge_history_metadata_backup_and_exact_undo(self):
        before=server.library()
        result=self.merge()
        game=server.library()[0]
        self.assertEqual(len(server.library()),1)
        self.assertEqual(game['platform'],'PC - Steam')
        self.assertEqual(game['status'],'Бэклог')
        self.assertEqual(game['playthroughs'],[{'date':'2019-06-14','platform':'PS3'}])
        self.assertTrue(game['favorite'])
        self.assertEqual(game['notes'],'Old note\n\nNew note')
        self.assertEqual(set(game['source_aliases']),{'hltb:123','steam:259170'})
        self.assertEqual(len(game['merge_archive']),2)
        self.assertTrue(list((server.DATA/'backups').glob('*.zip')))
        game_merge.undo(server,{'undo':result['undo']})
        self.assertEqual(server.library(),before)

    def test_stale_preview_and_undo_after_edit_are_refused(self):
        preview=game_merge.preview(server,self.data)
        server.save_game({'title':self.first['title'],'notes':'Changed'},self.first['id'])
        with self.assertRaises(ValueError):game_merge.apply(server,dict(self.data,signature=preview['signature']))
        result=self.merge()
        server.save_game({'title':self.first['title'],'notes':'Edited merged'},result['id'])
        with self.assertRaises(ValueError):game_merge.undo(server,{'undo':result['undo']})
        self.assertEqual(len(server.library()),1)

    def test_platform_change_and_new_playthrough_do_not_rewrite_history(self):
        result=self.merge()
        game=server.save_game({'title':self.first['title'],'status':'Перепрохожу'},result['id'])
        game=server.save_game({'title':self.first['title'],'status':'Пройдено','completed_at':'2026-10-02'},result['id'])
        self.assertEqual(game['playthroughs'],[{'date':'2019-06-14','platform':'PS3'},{'date':'2026-10-02','platform':'PC - Steam'}])
        game=server.save_game({'title':self.first['title'],'playthroughs':[game['playthroughs'][0]]},result['id'])
        self.assertEqual(game['completed_at'],'2019-06-14')
        restored=server.validate(json.loads(json.dumps(game)))
        self.assertEqual(restored['merge_archive'],game['merge_archive'])

    def test_legacy_hltb_platform_migration_and_repeat_merge(self):
        old={'platform':'Steam','hltb_entries':[{'platform':'PS3','date_complete':'2019-06-14'}],'completed_at':'2019-06-14'}
        history=server.playthroughs(old)
        self.assertEqual(history,[{'date':'2019-06-14','platform':'PS3'}])
        self.assertEqual(server.merge_playthroughs(history,history),history)
        self.assertEqual(len(server.merge_playthroughs(history,[{'date':'2019-06-14','platform':'Steam'}])),2)

    def test_repeat_steam_and_hltb_import_match_merged_sources(self):
        row={'id':77,'game_id':123,'custom_title':self.first['title'],'platform':'PS3','list_comp':1,'date_complete':'2019-06-14'}
        incoming=hltb_game(row)
        server.save_game({'title':self.first['title'],'source_id':incoming['source_id']},self.first['id'])
        result=self.merge()
        def done(manager,response):
            for _ in range(300):
                job=manager.inspect(response['job'])
                if job['state'] in ('done','error'):break
                time.sleep(.01)
            self.assertEqual(job['state'],'done',job)
            return job
        manager=Manager(server)
        with patch('library_sync.fetch_steam',return_value=[dict(title=self.second['title'],source_id=self.second['source_id'],platform='PC',status='Бэклог',sync_provider='steam')]):
            response=manager.preview({'provider':'steam','profile':'https://steamcommunity.com/id/test','api_key':'test'})
            job=done(manager,response)
            self.assertEqual(job['items'][0]['existing_id'],result['id'])
            done(manager,manager.apply({'preview':response['job'],'selected':[0],'choices':{'0':{'fields':['tags']}}}))
        replay=dict(row,id=78,date_complete='2021-01-01',date_updated='2021-01-01')
        with patch('library_sync.fetch_hltb',return_value=[row,replay]):
            response=manager.preview({'provider':'hltb','profile':'test'})
            job=done(manager,response)
            self.assertEqual(job['items'][0]['existing_id'],result['id'])
            done(manager,manager.apply({'preview':response['job'],'selected':[0],'choices':{'0':{'fields':['completed_at']}}}))
        game=server.library()[0]
        self.assertEqual(len(server.library()),1)
        self.assertEqual(game['platform'],'PC - Steam')
        self.assertEqual(game['status'],'Бэклог')
        self.assertEqual(game['playthroughs'],[{'date':'2019-06-14','platform':'PS3'},{'date':'2021-01-01','platform':'PS3'}])
