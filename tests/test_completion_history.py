import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import server


class CompletionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch.object(server, 'DATA', root), patch.object(server, 'DB', root/'library.sqlite3')]
        for item in self.patches: item.start()
        server.init_db()

    def tearDown(self):
        for item in self.patches: item.stop()
        self.temp.cleanup()

    def test_replay_appends_and_deletion_updates_latest(self):
        game = server.save_game({'title':'Portal','status':'Пройдено','completed_at':'2020-01-01'})
        self.assertEqual(game['completion_dates'], ['2020-01-01'])
        server.save_game({'title':'Portal','status':'Перепрохожу'}, game['id'])
        game = server.save_game({'title':'Portal','status':'Пройдено','completed_at':'2026-10-02'}, game['id'])
        self.assertEqual(game['completion_dates'], ['2020-01-01','2026-10-02'])
        game = server.save_game({'title':'Portal','completion_dates':['2020-01-01']},game['id'])
        self.assertEqual(game['completed_at'],'2020-01-01')
        game = server.save_game({'title':'Portal','completion_dates':[]},game['id'])
        self.assertEqual(game['completed_at'],'')
        self.assertEqual(server.library()[0]['completion_dates'],[])

    def test_legacy_hltb_dates_remain_but_deleted_dates_do_not_reappear(self):
        game = {'title':'Legacy','status':'Пройдено','added_at':'2020-01-01',
                'completed_at':'2021-01-01','hltb_entries':[{'date_complete':'2022-01-01'},{'date_complete':'0000-00-00'}]}
        import json
        with server.connection() as db:
            gid = db.execute('INSERT INTO games(payload) VALUES (?)',(json.dumps(game),)).lastrowid
        self.assertEqual(server.library()[0]['completion_dates'],['2021-01-01','2022-01-01'])
        server.save_game({'title':'Legacy','completion_dates':[]},gid)
        self.assertEqual(server.library()[0]['completion_dates'],[])

    def test_invalid_history_and_same_day_replay(self):
        with self.assertRaises(ValueError): server.save_game({'title':'Bad','completion_dates':['2026-02-30']})
        game=server.save_game({'title':'Same day','status':'Пройдено','completed_at':'2026-01-01'})
        server.save_game({'title':game['title'],'status':'Перепрохожу'},game['id'])
        game=server.save_game({'title':game['title'],'status':'Пройдено','completed_at':'2026-01-01'},game['id'])
        self.assertEqual(len(game['completion_dates']),2)

    def test_replaying_category_is_seeded_once_and_can_be_removed(self):
        self.assertIn('Перепрохожу',server.category_names())
        server.manage_category({'action':'delete','name':'Перепрохожу','replacement':'Хочу пройти'})
        server.init_db()
        self.assertNotIn('Перепрохожу',server.category_names())

    def test_merge_keeps_manual_replays_and_repeated_import_is_idempotent(self):
        self.assertEqual(server.merge_completion_dates(['2020-01-01']*2,['2020-01-01','2022-01-01']),['2020-01-01','2020-01-01','2022-01-01'])
        game={'completed_at':'2020-01-01','hltb_entries':[{'date_complete':'2020-01-01'},{'date_complete':'2020-01-01'}]}
        self.assertEqual(server.completion_dates(game),['2020-01-01','2020-01-01'])
