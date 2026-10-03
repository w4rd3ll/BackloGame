from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import server
import catalog_tools


class CatalogToolsTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        root=Path(self.work.name)
        self.patches=[patch.object(server,'DATA',root),patch.object(server,'DB',root/'library.sqlite3')]
        for item in self.patches:item.start()
        server.init_db()
        self.game=server.save_game({'title':'Portal','source_id':'hltb:123','status':'Пройдено','platform':'PS3','completed_at':'2019-01-01','notes':'mine','favorite':True})
        (root/'covers').mkdir()
        self.cover='/covers/'+('a'*64)+'.jpg'
        (root/self.cover.lstrip('/')).write_bytes(b'image fixture')

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.work.cleanup()

    def test_steam_keeps_its_description_without_wikipedia_fallback(self):
        for description in ('Short English description', 'Короткое русское описание'):
            payload={'400':{'success':True,'data':{'name':'Portal','about_the_game':description,'release_date':{'date':'Oct 10, 2007'},'genres':[],'platforms':{}}}}
            with self.subTest(description=description),patch.object(server,'remote',return_value=payload),patch.object(server,'russian_description_for_title') as wiki:
                game=server.details('steam:400')
            wiki.assert_not_called()
            self.assertEqual(game['description'],description)
            self.assertEqual(game['description_url'],'https://store.steampowered.com/app/400/')

    def test_comparison_apply_does_not_fill_series_from_another_catalog(self):
        with patch.object(server,'details',return_value={'title':'Portal Steam','description':'Steam description','source_url':'https://store.steampowered.com/app/400/'}),patch('catalog_tools.find_series') as wiki:
            result=catalog_tools.apply(server,{'id':self.game['id'],'fields':{'description':'steam:400'}})['game']
        wiki.assert_not_called()
        self.assertEqual(result['description'],'Steam description')
        self.assertEqual(result['description_url'],'https://store.steampowered.com/app/400/')

    def test_mixed_fields_preserve_unselected_data_and_progress(self):
        server.save_game({'title':'Portal','description':'mine','series':'Manual series','genre':'Old genre','release_date':'2007-01-01'},self.game['id'])
        entries={'steam:400':{'title':'Portal Steam','genre':'Puzzle','developer':'Valve','image':'unused'},'wiki:Portal':{'title':'Portal Wiki','description':'Wiki description','description_language':'ru','source_url':'https://example.com/wiki'},'metacritic:portal':{'title':'Portal MC','release_date':'2007-10-10','release_label':'Oct 10, 2007'}}
        with patch.object(server,'details',side_effect=lambda source:entries[source]) as details,patch.object(server,'archive_cover') as archive:
            result=catalog_tools.apply(server,{'id':self.game['id'],'fields':{'description':'wiki:Portal','genre':'steam:400','developer':'steam:400','release_date':'metacritic:portal'}})['game']
            self.assertEqual(details.call_count,3);archive.assert_not_called()
        self.assertEqual(result['title'],'Portal');self.assertEqual(result['description'],'Wiki description')
        self.assertEqual(result['description_language'],'ru');self.assertEqual(result['description_url'],'https://example.com/wiki')
        self.assertEqual(result['genre'],'Puzzle');self.assertEqual(result['release_date'],'2007-10-10')
        self.assertEqual(result['series'],'Manual series');self.assertEqual(result['source_id'],'hltb:123')
        for field in ('status','platform','completed_at','notes','favorite'):self.assertEqual(result[field],self.game[field])

    def test_selected_series_and_cover_replace_only_chosen_values(self):
        server.save_game({'title':'Portal','series':'Manual','custom_covers':{'portrait':{'url':'https://example.com/old','local':self.cover},'landscape':{'url':'https://example.com/wide','local':self.cover}}},self.game['id'])
        with patch.object(server,'details',return_value={'series':'Portal; Half-Life','image':'https://example.com/new'}),patch.object(server,'archive_cover',return_value=self.cover):
            result=catalog_tools.apply(server,{'id':self.game['id'],'fields':{'series':'wiki:Portal','image':'wiki:Portal'}})['game']
        self.assertEqual(result['series'],'Portal; Half-Life')
        self.assertEqual(result['custom_covers']['portrait']['url'],'https://example.com/new')
        self.assertEqual(result['custom_covers']['landscape']['url'],'https://example.com/wide')

    def test_failed_selected_source_or_cover_changes_nothing(self):
        before=server.library()
        for cover_failure in (False,True):
            with self.subTest(cover_failure=cover_failure),patch.object(server,'details',side_effect=lambda source:({'description':'new','image':'https://example.com/new'} if cover_failure or source=='steam:400' else (_ for _ in ()).throw(OSError('offline')))),patch.object(server,'archive_cover',side_effect=OSError('cover unavailable')):
                with self.assertRaises(OSError):catalog_tools.apply(server,{'id':self.game['id'],'fields':{'description':'steam:400','image':'wiki:Portal'}})
            self.assertEqual(server.library(),before)

    def test_invalid_or_empty_field_selection_never_fetches_catalogs(self):
        for fields in ({},{'status':'steam:400'},{'description':'hltb:123'},{'description':123}):
            with patch.object(server,'details') as details,self.assertRaises(ValueError):
                catalog_tools.apply(server,{'id':self.game['id'],'fields':fields})
            details.assert_not_called()
        with patch.object(server,'details',return_value={}),self.assertRaises(ValueError):
            catalog_tools.apply(server,{'id':self.game['id'],'fields':{'description':'steam:400'}})

    def test_metadata_update_preserves_crop_of_independent_custom_cover(self):
        url='https://cdn2.steamgriddb.com/grid/custom.png'
        crop={'image':url,'x':0,'y':.2,'width':1,'height':.35}
        server.save_game({'title':'Portal','custom_covers':{'portrait':{'url':url,'local':self.cover}},'thumbnail_crop':crop},self.game['id'])
        with patch.object(server,'details',return_value={'image':'https://example.com/new.jpg','source_id':'steam:400'}),patch.object(server,'archive_cover',return_value=self.cover),patch('catalog_tools.find_series',return_value={}):
            saved=catalog_tools.apply(server,{'id':self.game['id'],'source':'steam:400'})['game']
        self.assertEqual(saved['thumbnail_crop'],crop)

    def test_changed_base_image_invalidates_only_its_own_crop(self):
        url='https://example.com/old.jpg'
        server.save_game({'title':'Portal','image':url,'image_local':self.cover,'thumbnail_crop':{'image':url,'x':0,'y':.2,'width':1,'height':.35}},self.game['id'])
        with patch.object(server,'details',return_value={'image':'https://example.com/new.jpg','source_id':'steam:400'}),patch.object(server,'archive_cover',return_value=self.cover),patch('catalog_tools.find_series',return_value={}):
            saved=catalog_tools.apply(server,{'id':self.game['id'],'source':'steam:400'})['game']
        self.assertIsNone(saved['thumbnail_crop'])

    def test_full_editor_save_preserves_unchanged_original_hltb_record(self):
        import json
        with server.connection() as db:
            row=json.loads(db.execute('SELECT payload FROM games WHERE id=?',(self.game['id'],)).fetchone()[0])
            row['hltb_entries']=[{'id':123,'platform':'PS3','invested_pro':29880,'review_score':80,'list_custom':1}]
            db.execute('UPDATE games SET payload=? WHERE id=?',(json.dumps(row),self.game['id']))
        before=server.library()[0]
        saved=server.save_game(dict(before,description='Edited'),before['id'])
        self.assertEqual(saved['hltb_entries'],before['hltb_entries'])
        # Changing the incoming archive still goes through its normal whitelist.
        saved=server.save_game({'title':'Portal','hltb_entries':[{'id':999,'untrusted':{'nested':True}}]},before['id'])
        self.assertEqual(saved['hltb_entries'],[{'id':999}])

    def test_alternative_metadata_preserves_identity_progress_and_manual_series(self):
        server.save_game({'title':'Portal','series':'My series; Other'},self.game['id'])
        fresh={'title':'Changed title','source_id':'metacritic:portal','description':'new description','series':'Portal','image':'https://example.com/cover.jpg','source_url':'https://www.metacritic.com/game/portal/'}
        with patch.object(server,'details',return_value=fresh),patch.object(server,'archive_cover',return_value=self.cover),patch('catalog_tools.find_series',return_value={}):
            result=catalog_tools.apply(server,{'id':self.game['id'],'source':'metacritic:portal'})['game']
        self.assertEqual(result['source_id'],'hltb:123')
        self.assertEqual(result['title'],'Portal')
        self.assertEqual(result['notes'],'mine')
        self.assertTrue(result['favorite'])
        self.assertEqual(result['platform'],'PS3')
        self.assertEqual(result['playthroughs'],self.game['playthroughs'])
        self.assertEqual(result['series'],'My series; Other')
        self.assertEqual(result['description'],'new description')
        self.assertEqual(result['image_local'],self.cover)
        self.assertIn('metacritic:portal',result['source_aliases'])

    def test_unavailable_alternative_cover_preserves_saved_game(self):
        before=server.library()
        with patch.object(server,'details',return_value={'image':'https://example.com/bad.jpg'}),patch.object(server,'archive_cover',side_effect=OSError('offline')):
            with self.assertRaises(OSError):catalog_tools.apply(server,{'id':self.game['id'],'mode':'cover','source':'steam:400'})
        self.assertEqual(server.library(),before)

    def test_manual_catalog_choice_replaces_only_selected_cover_format(self):
        saved={'portrait':{'url':'https://cdn2.steamgriddb.com/grid/one.png','local':self.cover},'landscape':{'url':'https://cdn2.steamgriddb.com/grid/two.png','local':self.cover}}
        server.save_game({'title':'Portal','custom_covers':saved},self.game['id'])
        fresh={'image':'https://example.com/new.jpg','source_id':'metacritic:portal'}
        with patch.object(server,'details',return_value=fresh),patch.object(server,'archive_cover',return_value=self.cover):
            result=catalog_tools.apply(server,{'id':self.game['id'],'source':'metacritic:portal','mode':'cover','orientation':'portrait'})['game']
        self.assertEqual(result['custom_covers']['portrait']['url'],fresh['image'])
        self.assertEqual(result['custom_covers']['landscape']['url'],saved['landscape']['url'])
        self.assertEqual(result['playthroughs'],self.game['playthroughs'])

    def test_bulk_skips_ambiguous_matches_and_uses_fallback_source(self):
        with patch.object(server,'search_games',return_value=[{'title':'Portal','source_id':'steam:1'},{'title':'Portal','source_id':'steam:2'}]),patch.object(server,'details') as details:
            self.assertFalse(catalog_tools.automatic(server,{'id':self.game['id'],'provider':'steam'})['changed'])
            details.assert_not_called()
        def search(title,provider):
            if provider=='steam':raise OSError('offline')
            return [{'title':'Portal','source_id':'metacritic:portal'}]
        with patch.object(server,'search_games',side_effect=search),patch.object(server,'details',return_value={'image':'https://example.com/cover.jpg','source_id':'metacritic:portal'}),patch.object(server,'archive_cover',return_value=self.cover):
            self.assertTrue(catalog_tools.automatic(server,{'id':self.game['id'],'provider':'auto'})['changed'])

    def test_series_requires_game_relationship_and_never_overwrites_manual_value(self):
        game=dict(self.game,qid='Q1')
        entity={'claims':{'P400':[{'mainsnak':{'datavalue':{'value':{'id':'Q2'}}}}],'P179':[{'mainsnak':{'datavalue':{'value':{'id':'Q3'}}}}]}}
        with patch.object(server,'entity',side_effect=lambda qid:entity if qid=='Q1' else {'labels':{'en':{'value':'Portal'}}}):
            self.assertEqual(catalog_tools.find_series(server,game)['series'],'Portal')
        with patch.object(server,'entity',return_value={'claims':{'P179':entity['claims']['P179']}}):
            self.assertEqual(catalog_tools.find_series(server,game),{})
        server.save_game({'title':'Portal','series':'Handwritten'},game['id'])
        with patch('catalog_tools.find_series') as find:
            self.assertFalse(catalog_tools.automatic(server,{'id':game['id'],'mode':'series'})['changed'])
            find.assert_not_called()

    def test_new_cover_url_does_not_reuse_old_archive_from_form(self):
        server.save_game({'title':'Portal','image':'https://example.com/old.jpg','image_local':self.cover},self.game['id'])
        game=server.library()[0]
        with patch.object(server,'archive_cover',return_value=self.cover) as archive:
            server.save_game(dict(game,image='https://example.com/new.jpg'),game['id'])
            archive.assert_called_once_with('https://example.com/new.jpg')

    def test_series_can_match_a_different_article_title_only_with_verified_steam_id(self):
        game={'title':'The Ultimate Doom','source_id':'steam:2280'}
        article={'qid':'Q1','title':'Doom (1993 video game)'}
        claims={'P1733':[{'mainsnak':{'datavalue':{'value':'2280'}}}],
                'P179':[{'mainsnak':{'datavalue':{'value':{'id':'Q3'}}}}]}
        with patch.object(server,'search_games',return_value=[article]),patch.object(server,'entity',side_effect=lambda qid:{'claims':claims} if qid=='Q1' else {'labels':{'en':{'value':'Doom'}}}):
            self.assertEqual(catalog_tools.find_series(server,game)['series'],'Doom')
            claims['P1733'][0]['mainsnak']['datavalue']['value']='9999'
            self.assertEqual(catalog_tools.find_series(server,game),{})
