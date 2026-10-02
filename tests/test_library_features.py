import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import server
from library_sync import Manager, hltb_game, parse_csv


class LibraryFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.data=Path(self.work.name)
        self.patches=[patch.object(server,'DATA',self.data),patch.object(server,'DB',self.data/'library.sqlite3')]
        for p in self.patches:p.start()
        server.init_db()
        server.manage_category({'action':'add','name':'Бэклог'})
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.work.cleanup()
    def done(self, manager, result):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            job=manager.inspect(result['job'])
            if job['state']!='running':
                self.assertEqual(job['state'],'done',job)
                return job
            time.sleep(.01)
        self.fail('Job did not finish')
    def test_series_default_and_partial_edits(self):
        for value in (None, '', '   ', '-', '; - ;'):
            game=server.save_game(dict(title='Default series', **({'series':value} if value is not None else {})))
            self.assertEqual(game['series'],'Без серии')
            with server.connection() as db:
                self.assertEqual(json.loads(db.execute('SELECT payload FROM games WHERE id=?',(game['id'],)).fetchone()[0])['series'],'Без серии')
        game=server.save_game({'title':'Portal','series':'Half-Life; Portal'})
        edited=server.save_game({'title':'Portal','notes':'Keep series'},game['id'])
        self.assertEqual(edited['series'],'Half-Life; Portal')
        cleared=server.save_game({'title':'Portal','series':''},game['id'])
        self.assertEqual(cleared['series'],'Без серии')

    def test_completed_date_default_and_validation(self):
        g=server.save_game({'title':'Test','status':'Пройдено'})
        self.assertRegex(g['completed_at'],r'^\d{4}-\d{2}-\d{2}$')
        with self.assertRaises(ValueError):server.save_game({'title':'Invalid','status':'Пройдено','completed_at':'2026-02-30'})
        with self.assertRaises(ValueError):server.save_game({'title':'Invalid','completed_at':'2026-10-01T10:00:00'})
        saved=server.save_game({'title':'Test','favorite':True},g['id'])
        self.assertEqual(saved['completed_at'],g['completed_at'])
    def test_steam_history_survives_restart_and_keeps_profiles_separate(self):
        first={'title':'Old','source_id':'steam:100'}
        newer={'title':'New','source_id':'steam:200'}
        manager=Manager(server)
        self.assertEqual(manager.steam_history('https://steamcommunity.com/id/test/',[first]),(set(),True))
        manager=Manager(server)
        self.assertEqual(manager.steam_history('test',[first,newer]),({'steam:200'},False))
        self.assertEqual(manager.steam_history('test',[first,newer]),(set(),False))
        self.assertEqual(manager.steam_history('other',[newer]),(set(),True))
        self.assertEqual(manager.steam_history('test',[]),(set(),False))
        self.assertEqual(manager.steam_history('test',[first,newer]),(set(),False))
        self.assertEqual(len(list(self.data.glob('steam-library-history*'))),1)
    def test_steam_failed_fetch_does_not_change_history(self):
        manager=Manager(server)
        manager.steam_history('test',[{'title':'Old','source_id':'steam:100'}])
        path=self.data/'steam-library-history.json'
        before=path.read_bytes()
        with patch('library_sync.fetch_steam',side_effect=ValueError('unavailable')):
            request=manager.preview({'provider':'steam','profile':'test','api_key':'test'})
            deadline=time.monotonic()+5
            while manager.inspect(request['job'])['state']=='running' and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(manager.inspect(request['job'])['state'],'error')
        self.assertEqual(path.read_bytes(),before)
    def test_steam_preview_marks_only_new_app_ids(self):
        manager=Manager(server)
        games=[{'title':'Same title','source_id':'steam:'+str(appid),'platform':'PC - Steam','status':'Хочу пройти','sync_provider':'steam'} for appid in (100,200)]
        manager.steam_history('test',games[:1])
        with patch('library_sync.fetch_steam',return_value=games):
            result=self.done(manager,manager.preview({'provider':'steam','profile':'test','api_key':'test'}))
        self.assertEqual([g['source_id'] for g in result['items'] if g['steam_new']],['steam:200'])
        self.assertEqual(result['steam_new_count'],1)
        self.assertEqual(result['items'][0]['source_id'],'steam:200')
        self.assertFalse(result['steam_baseline'])
    def test_steam_same_title_keeps_distinct_app_ids(self):
        manager=Manager(server)
        games=[{'title':'Same title','source_id':'steam:'+str(appid),'platform':'PC - Steam','status':'Хочу пройти','sync_provider':'steam'} for appid in (100,200)]
        with patch('library_sync.fetch_steam',return_value=games):
            job=manager.preview({'provider':'steam','profile':'test','api_key':'test'})
            preview=self.done(manager,job)
        self.assertEqual(len(preview['items']),2)
        result=self.done(manager,manager.apply({'preview':job['job'],'selected':[0,1]}))
        self.assertEqual(result['added'],2)
        self.assertEqual({g['source_id'] for g in server.library()},{'steam:100','steam:200'})
        self.assertTrue(all(g['tags']=='Steam' for g in server.library()))
    def test_steam_match_merges_tag_only_when_confirmed(self):
        old=server.save_game({'title':'Portal','source_id':'steam:400','platform':'PC - Steam','tags':'HLTB, Puzzle','status':'Пройдено','completed_at':'2001-01-01'})
        manager=Manager(server)
        game={'title':'Portal','source_id':'steam:400','platform':'PC - Steam','status':'Хочу пройти','sync_provider':'steam'}
        with patch('library_sync.fetch_steam',return_value=[game]):
            job=manager.preview({'provider':'steam','profile':'test','api_key':'test'})
            preview=self.done(manager,job)
        self.assertEqual(preview['items'][0]['tags'],'Steam')
        self.done(manager,manager.apply({'preview':job['job'],'selected':[0]}))
        self.assertEqual(server.library()[0]['tags'],'HLTB, Puzzle')
        self.done(manager,manager.apply({'preview':job['job'],'selected':[0],'choices':{'0':{'fields':['tags'],'overwrite':False}}}))
        saved=server.library()[0]
        self.assertEqual(saved['tags'],'HLTB, Puzzle, Steam')
        self.assertEqual(saved['id'],old['id'])
        self.assertEqual(saved['completed_at'],'2001-01-01')
    def test_steam_app_id_matches_renamed_game_on_custom_platform(self):
        old=server.save_game({'title':'My Portal title','source_id':'steam:400','platform':'My PC','notes':'keep me','status':'Играю'})
        manager=Manager(server)
        game={'title':'Portal','source_id':'steam:400','platform':'PC - Steam','status':'Хочу пройти','sync_provider':'steam'}
        with patch('library_sync.fetch_steam',return_value=[game]):
            preview=manager.preview({'provider':'steam','profile':'test','api_key':'test'})
            result=self.done(manager,preview)
        self.assertEqual(result['items'][0]['existing_id'],old['id'])
        self.done(manager,manager.apply({'preview':preview['job'],'selected':[0],'choices':{'0':{'fields':['tags'],'overwrite':False}}}))
        saved=server.library()
        self.assertEqual(len(saved),1)
        self.assertEqual(saved[0]['title'],'My Portal title')
        self.assertEqual(saved[0]['platform'],'My PC')
        self.assertEqual(saved[0]['notes'],'keep me')
        self.assertEqual(saved[0]['status'],'Играю')
        self.assertEqual(saved[0]['tags'],'Steam')
    def test_category_sort_and_view_round_trip(self):
        sorts={'favorites':{'field':'title','direction':1,'view':'compact'},'Пройдено':{'field':'completed_at','direction':-1,'view':'list'}}
        result=server.validate_settings({'category_sorts':sorts})
        self.assertEqual(result['category_sorts'],sorts)
        with self.assertRaises(ValueError):server.validate_settings({'category_sorts':{'all':{'field':'notes','direction':1}}})
    def test_import_does_not_invent_missing_completion_date(self):
        g=server.save_game({'title':'Unknown date','status':'Пройдено','sync_provider':'hltb','sync_status':'Пройдено','completed_at':''})
        self.assertEqual(g['completed_at'],'')
    def test_mapping_dates_replay_and_image_spaces(self):
        game=hltb_game({'id':1,'game_id':10,'custom_title':'Test','platform':'PC','list_backlog':1,'list_replay':1,'date_complete':'0000-00-00','release_world':'2001-00-00','game_image':'my cover.jpg'})
        self.assertEqual(game['status'],'Бэклог')
        self.assertEqual(game['completed_at'],'')
        self.assertEqual(game['release_date'],'2001')
        self.assertIn('Повторное прохождение',game['tags'])
        self.assertTrue(game['image'].endswith('my%20cover.jpg'))
        self.assertEqual(hltb_game({'custom_title':'Test','list_retired':1})['status'],'Брошено')
    def test_duplicate_requires_field_choice_and_preserves_favorites(self):
        old=server.save_game({'title':'Portal','platform':'PC - Steam','status':'Играю','notes':'mine','favorite':True})
        manager=Manager(server)
        csv='Title,Platform,Playing,Backlog,Completed,Completion Date,General Notes\nPortal,PC,,,X,2001-01-01,remote\n'
        preview=manager.preview({'provider':'hltb-csv','csv':csv})
        job=self.done(manager,preview)
        self.assertEqual(job['items'][0]['existing_id'],old['id'])
        result=self.done(manager,manager.apply({'preview':preview['job'],'selected':[0]}))
        self.assertEqual(result['skipped'],1)
        result=self.done(manager,manager.apply({'preview':preview['job'],'selected':[0],'choices':{'0':{'fields':['status','completed_at'],'overwrite':True}}}))
        self.assertEqual(result['updated'],1)
        updated=server.library()[0]
        self.assertEqual(updated['status'],'Пройдено')
        self.assertEqual(updated['completed_at'],'2001-01-01')
        self.assertEqual(updated['notes'],'mine')
        self.assertTrue(updated['favorite'])
        self.assertEqual(updated['manual_order'],old['manual_order'])
    def test_csv_replays_keep_latest_date_and_platforms_separate(self):
        manager=Manager(server)
        csv='Title,Platform,Playing,Backlog,Completed,Completion Date\nPortal,PC,,,X,2001-01-01\nPortal,PC,,,X,2002-01-01\nPortal,PS3,,,X,2003-01-01\n'
        preview=manager.preview({'provider':'hltb-csv','csv':csv})
        job=self.done(manager,preview)
        self.assertEqual(len(job['items']),2)
        self.assertEqual(job['items'][0]['completed_at'],'2002-01-01')
        self.done(manager,manager.apply({'preview':preview['job'],'selected':[0,1]}))
        self.assertEqual(len(server.library()),2)
        self.assertTrue(all(g['status']=='Пройдено' for g in server.library()))
    def test_preview_shows_newly_added_first_and_selection_matches(self):
        manager=Manager(server)
        csv='Title,Platform,Playing,Backlog,Completed,Added\nOld,PC,,,X,2001-01-01 12:00:00\nUnknown,PC,,,X,\nNewest,PC,,,X,2026-10-01 10:00:00\nOld,PC,,,X,2025-01-01 10:00:00\n'
        preview=manager.preview({'provider':'hltb-csv','csv':csv})
        job=self.done(manager,preview)
        self.assertEqual([g['title'] for g in job['items']],['Newest','Old','Unknown'])
        self.assertEqual(job['items'][1]['sync_added_at'],'2025-01-01 10:00:00')
        self.done(manager,manager.apply({'preview':preview['job'],'selected':[0]}))
        self.assertEqual([g['title'] for g in server.library()],['Newest'])


if __name__=='__main__':unittest.main()
