from pathlib import Path
import json
import tempfile
import time
import unittest
import zipfile
import urllib.error
from unittest.mock import patch
import server
import steamgriddb
import game_merge


class ArtworkTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.root=Path(self.work.name)
        self.patches=[patch.object(server,'DATA',self.root),patch.object(server,'DB',self.root/'library.sqlite3'),patch.object(server,'TRASH',{}),patch.object(game_merge,'UNDO',{}),patch.object(steamgriddb,'GALLERIES',{})]
        for p in self.patches:p.start()
        server.init_db()
        self.game=server.save_game({'title':'Portal','source_id':'hltb:1','platform':'PS3','status':'Пройдено','completed_at':'2019-01-01','notes':'personal'})
        (self.root/'covers').mkdir()
        self.a=self.cover('a');self.b=self.cover('b');self.c=self.cover('c')

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.work.cleanup()

    def cover(self,char):
        name='/covers/'+char*64+'.png'
        (self.root/name.lstrip('/')).write_bytes(b'fixture')
        return name

    def gallery(self,orientation,asset=1):
        rows=[{'id':asset,'url':'https://cdn2.steamgriddb.com/grid/test.png','thumb':'https://cdn2.steamgriddb.com/thumb/test.png','width':600 if orientation=='portrait' else 920,'height':900 if orientation=='portrait' else 430,'author':{'name':'Artist'},'mime':'image/png'}]
        with patch.object(steamgriddb,'request',return_value=rows):return steamgriddb.grids(server,{'game':9022,'orientation':orientation})

    def test_independent_covers_reset_preserves_progress_and_source(self):
        for orientation,local in [('portrait',self.a),('landscape',self.b)]:
            gallery=self.gallery(orientation)
            with patch.object(server,'archive_cover',return_value=local):steamgriddb.apply(server,{'id':self.game['id'],'gallery':gallery['gallery'],'asset':1})
        card=server.library()[0]
        self.assertEqual(set(card['custom_covers']),{'portrait','landscape'})
        self.assertEqual(card['notes'],self.game['notes'])
        self.assertEqual(card['source_id'],self.game['source_id'])
        self.assertEqual(card['playthroughs'],self.game['playthroughs'])
        card=steamgriddb.reset(server,{'id':card['id'],'orientation':'portrait'})['game']
        self.assertEqual(list(card['custom_covers']),['landscape'])

    def test_gallery_must_be_current_and_belong_to_database(self):
        token=self.gallery('portrait')['gallery']
        entry=steamgriddb.GALLERIES[token]
        steamgriddb.GALLERIES[token]=(entry[0],'other.sqlite3',*entry[2:])
        with self.assertRaises(ValueError):steamgriddb.apply(server,{'id':self.game['id'],'gallery':token,'asset':1})
        steamgriddb.GALLERIES[token]=(time.monotonic()-1,*entry[1:])
        with self.assertRaises(ValueError):steamgriddb.apply(server,{'id':self.game['id'],'gallery':token,'asset':1})

    def test_failed_download_keeps_previous_cover(self):
        before=server.library()
        gallery=self.gallery('portrait')
        with patch.object(server,'archive_cover',side_effect=OSError('offline')):
            with self.assertRaises(OSError):steamgriddb.apply(server,{'id':self.game['id'],'gallery':gallery['gallery'],'asset':1})
        self.assertEqual(server.library(),before)

    def test_backup_has_both_images_but_never_key(self):
        steamgriddb.set_key(server,{'key':'private-fixture-key-12345'})
        covers={o:{'url':'https://cdn2.steamgriddb.com/grid/test.png','local':local} for o,local in [('portrait',self.a),('landscape',self.b)]}
        server.save_game({'title':'Portal','custom_covers':covers},self.game['id'])
        name=server.create_backup()
        with zipfile.ZipFile(server.backup_path(name)) as archive:
            self.assertIn(self.a.lstrip('/'),archive.namelist());self.assertIn(self.b.lstrip('/'),archive.namelist())
            self.assertNotIn('.steamgriddb-key',archive.namelist())
        self.assertNotIn('private-fixture-key',json.dumps(server.library()))

    def test_cleanup_retains_shared_covers_and_pending_undo(self):
        server.save_game({'title':'Portal','image_local':self.a},self.game['id'])
        other=server.save_game({'title':'Other','image_local':self.a})
        undo=server.delete_game(self.game['id'])['undo']
        server.cleanup_unused_covers()
        self.assertTrue((self.root/self.a.lstrip('/')).exists())
        server.undo_delete(undo)
        self.assertEqual(len(server.library()),2)
        server.delete_game(other['id']);server.delete_game(self.game['id'])
        with patch.object(server.time,'monotonic',return_value=time.monotonic()+601):server.cleanup_unused_covers()
        self.assertFalse((self.root/self.a.lstrip('/')).exists())

    def test_cleanup_retains_archived_metadata_and_undo_merge(self):
        server.save_game({'title':'Portal','merge_archive':[{'title':'Old','image_local':self.a,'custom_covers':{'portrait':{'url':'https://cdn2.steamgriddb.com/grid/test.png','local':self.b}}}]},self.game['id'])
        server.cleanup_unused_covers()
        self.assertTrue((self.root/self.a.lstrip('/')).exists())
        self.assertTrue((self.root/self.b.lstrip('/')).exists())
        self.assertFalse((self.root/self.c.lstrip('/')).exists())

    def test_cleanup_after_restart_with_no_pending_undo(self):
        server.save_game({'title':'Portal','image_local':self.a},self.game['id'])
        server.delete_game(self.game['id']);server.TRASH.clear()
        server.cleanup_unused_covers()
        self.assertFalse((self.root/self.a.lstrip('/')).exists())

    def test_merge_undo_keeps_original_images_even_after_edit(self):
        server.save_game({'title':'Portal','image_local':self.a},self.game['id'])
        other=server.save_game({'title':'Portal','image_local':self.b})
        data={'ids':[self.game['id'],other['id']]}
        data['signature']=game_merge.preview(server,data)['signature']
        merged=game_merge.apply(server,data)
        # Undo snapshots also hold files independently of current card metadata.
        with server.connection() as db:
            row=json.loads(db.execute('SELECT payload FROM games WHERE id=?',(merged['id'],)).fetchone()[0]);row.pop('merge_archive');row.pop('image_local')
            db.execute('UPDATE games SET payload=? WHERE id=?',(json.dumps(row),merged['id']))
        server.cleanup_unused_covers()
        self.assertTrue((self.root/self.a.lstrip('/')).exists())
        self.assertTrue((self.root/self.b.lstrip('/')).exists())

    def test_cleanup_leaves_backups_and_unrelated_files(self):
        (self.root/'covers'/'notes.txt').write_text('keep')
        server.save_game({'title':'Portal','image_local':self.a},self.game['id'])
        name=server.create_backup()
        server.delete_game(self.game['id']);server.TRASH.clear();server.cleanup_unused_covers()
        self.assertTrue(server.backup_path(name).is_file())
        self.assertTrue((self.root/'covers'/'notes.txt').is_file())

    def test_invalid_external_artwork_is_not_selectable(self):
        rows=[{'id':1,'url':'https://other.example/grid.png','width':600,'height':900}, {'id':2,'url':'https://cdn2.steamgriddb.com/grid/a.png','width':920,'height':430}]
        with patch.object(steamgriddb,'request',return_value=rows):
            self.assertEqual(steamgriddb.grids(server,{'game':1,'orientation':'portrait'})['items'],[])

    def test_authentication_failure_never_exposes_key(self):
        steamgriddb.set_key(server,{'key':'private-fixture-key-12345'})
        with patch('urllib.request.OpenerDirector.open',side_effect=urllib.error.HTTPError('https://www.steamgriddb.com',401,'private-fixture-key-12345',None,None)):
            with self.assertRaises(ValueError) as error:steamgriddb.search(server,{'query':'Portal'})
        self.assertNotIn('private-fixture',str(error.exception))

    def test_crop_of_custom_cover_is_saved_and_invalidated_when_source_changes(self):
        url='https://cdn2.steamgriddb.com/grid/portrait.png'
        server.save_game({'title':'Portal','custom_covers':{'portrait':{'url':url,'local':self.a}}},self.game['id'])
        crop={'image':url,'x':0,'y':.2,'width':1,'height':.3}
        card=server.save_game({'title':'Portal','thumbnail_crop':crop},self.game['id'])
        self.assertEqual(card['thumbnail_crop'],crop)
        card=server.save_game({'title':'Portal','notes':'edited'},self.game['id'])
        self.assertEqual(card['thumbnail_crop'],crop)
        card=server.save_game({'title':'Portal','custom_covers':{'portrait':{'url':url+'?new','local':self.b}}},self.game['id'])
        self.assertIsNone(card['thumbnail_crop'])

    def test_explicit_landscape_selection_replaces_manual_crop(self):
        url='https://cdn2.steamgriddb.com/grid/portrait.png'
        server.save_game({'title':'Portal','custom_covers':{'portrait':{'url':url,'local':self.a}},'thumbnail_crop':{'image':url,'x':0,'y':.2,'width':1,'height':.3}},self.game['id'])
        gallery=self.gallery('landscape')
        with patch.object(server,'archive_cover',return_value=self.b):
            card=steamgriddb.apply(server,{'id':self.game['id'],'gallery':gallery['gallery'],'asset':1})['game']
        self.assertIsNone(card['thumbnail_crop'])
        self.assertEqual(card['custom_covers']['portrait']['url'],url)
