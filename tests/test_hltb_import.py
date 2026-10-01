import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server

spec = importlib.util.spec_from_file_location('hltb_import', Path(__file__).parents[1] / 'tools/import_hltb_snapshot.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ImportTests(unittest.TestCase):
    def test_partial_release_dates(self):
        self.assertEqual(module.release('1993-00-00'), '1993')
        self.assertEqual(module.release('1993-10-00'), '1993-10')
        self.assertEqual(module.release('0000-00-00'), '')

    def test_merges_replays_and_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            snapshot = data / 'snapshot.json'
            entry = {'id': 42, 'game_id': 100, 'custom_title': 'Portal', 'platform': 'PC',
                     'list_comp': 1, 'date_added': '2020-01-01 12:00:00',
                     'date_complete': '2021-01-01', 'release_world': '2007-00-00'}
            snapshot.write_text(json.dumps({'games': [entry, dict(entry, id=43, date_complete='2022-01-01')]}))
            with patch.object(server, 'DATA', data), patch.object(server, 'DB', data/'library.sqlite3'):
                server.init_db()
                old = server.save_game({'title': 'Portal', 'platform': 'PC - Steam', 'source_id': 'steam:400',
                                        'notes': 'personal note', 'favorite': True, 'status': 'Играю'})
                with patch('sys.argv', ['import', str(snapshot), '--data-dir', str(data), '--apply']):
                    module.main()
                games = server.library()
                self.assertEqual(len(games), 1)
                game = games[0]
                for key in ('id', 'source_id', 'notes', 'favorite', 'manual_order', 'added_at', 'platform'):
                    self.assertEqual(game[key], old[key])
                self.assertEqual(game['status'], 'HLTB')
                self.assertEqual(game['hltb_previous_status'], 'Играю')
                self.assertEqual(len(game['hltb_entries']), 2)
                self.assertEqual(game['completed_at'], '2022-01-01')
                self.assertEqual(game['release_date'], '2007')
                self.assertEqual(len(server.backup_files()), 1)


if __name__ == '__main__':
    unittest.main()
