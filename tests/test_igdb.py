import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import server,catalog_tools,igdb


class IGDBTests(unittest.TestCase):
    def test_search_and_details_route_to_public_relay_without_credentials(self):
        game={'source_id':'igdb:1','title':'Portal','series':'Portal'}
        with patch.object(server,'remote',side_effect=[{'items':[game]},{'game':game}]) as remote:
            self.assertEqual(server.search_games('Portal','igdb'),[game])
            self.assertEqual(server.details('igdb:1'),game)
        self.assertTrue(all(url.args[0].startswith(igdb.RELAY) for url in remote.call_args_list))
        self.assertNotIn('secret',str(remote.call_args_list))
        with patch.object(server,'remote') as remote,self.assertRaises(ValueError):server.details('igdb:1;fields=*')
        remote.assert_not_called()

    def test_selected_igdb_fields_preserve_progress_notes_and_source(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(server,'DATA',Path(folder)),patch.object(server,'DB',Path(folder)/'library.sqlite3'):
            server.init_db()
            old=server.save_game({'title':'Portal','source_id':'hltb:1','platform':'PS3','status':'Пройдено','completed_at':'2019-01-01','notes':'mine','series':'Handwritten'})
            fresh={'source_id':'igdb:1','title':'Portal','description':'IGDB summary','series':'Portal','developer':'Valve'}
            with patch.object(server,'details',return_value=fresh):
                saved=catalog_tools.apply(server,{'id':old['id'],'fields':{'description':'igdb:1','series':'igdb:1'}})['game']
            for name in ['platform','status','completed_at','notes','source_id']:self.assertEqual(saved[name],old[name])
            self.assertEqual(saved['series'],'Portal');self.assertEqual(saved['description'],'IGDB summary')
            self.assertIn('igdb:1',saved['source_aliases'])

    def test_landscape_cover_uses_artwork_and_preserves_portrait(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(server,'DATA',Path(folder)),patch.object(server,'DB',Path(folder)/'library.sqlite3'):
            server.init_db();local='/covers/'+('a'*64)+'.jpg'
            (Path(folder)/'covers').mkdir();(Path(folder)/local.lstrip('/')).write_bytes(b'fixture')
            old=server.save_game({'title':'Portal','custom_covers':{'portrait':{'url':'https://example.com/portrait.jpg','local':local}}})
            fresh={'source_id':'igdb:1','title':'Portal','image':'https://example.com/portrait.jpg','landscape_image':'https://example.com/artwork.jpg','series':'Portal'}
            with patch.object(server,'details',return_value=fresh),patch.object(server,'archive_cover',return_value=local) as archive:
                saved=catalog_tools.apply(server,{'id':old['id'],'source':'igdb:1','mode':'cover','orientation':'landscape'})['game']
            archive.assert_called_once_with(fresh['landscape_image'])
            self.assertEqual(saved['custom_covers']['portrait'],old['custom_covers']['portrait'])
            self.assertEqual(saved['custom_covers']['landscape']['url'],fresh['landscape_image'])
