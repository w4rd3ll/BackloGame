import json
import io
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from pathlib import Path
from http.server import ThreadingHTTPServer
import server


class LibraryTests(unittest.TestCase):
    def test_share_endpoint_exports_only_selected_cards(self):
        game=self.request('/api/save', {'game':{'title':'Shared game','notes':'personal note'}})[1]
        other=self.request('/api/save', {'game':{'title':'Not shared'}})[1]
        status,result=self.request('/api/share', {'ids':[game['id']], 'title':'For a friend','language':'en','covers':False})
        self.assertEqual(status,200)
        self.assertIn('Shared game',result['html'])
        self.assertNotIn('personal note',result['html'])
        self.assertNotIn('Not shared',result['html'])
        self.assertEqual(result['count'],1)
        self.assertEqual(self.request('/api/share', {'ids':[], 'title':'Empty'})[0],400)
        with urllib.request.urlopen(self.url+'/sharing.js') as response:
            self.assertEqual(response.status,200)

    def test_language_preferences_preserve_library(self):
        self.assertEqual(self.request('/api/library')[1]['settings']['language'], 'en')
        self.request('/api/save', {'game':{'title':'Название без перевода','notes':'Моя заметка','platform':'Моя консоль'}})
        original=self.request('/api/library')[1]['games']
        for language in ('ru','en'):
            self.assertEqual(self.request('/api/settings',{'language':language})[1]['language'],language)
            data=self.request('/api/library')[1]
            self.assertEqual(data['settings']['language'],language)
            self.assertEqual(data['games'],original)
        self.assertEqual(self.request('/api/settings',{'language':'de'})[0],400)
        with urllib.request.urlopen(self.url+'/i18n.js') as response:
            self.assertEqual(response.status,200)
            self.assertIn(b"let uiLanguage='en'",response.read())

    def test_games_only_rollback(self):
        self.assertEqual(self.request('/api/save',{'game':{'title':'Game','media_type':'game','series':'Half-Life; Portal'}})[0],200)
        for kind in ('book','movie','tv','animation','comic'):
            self.assertEqual(self.request('/api/save',{'game':{'title':'Other','media_type':kind}})[0],400)
        self.assertEqual(self.request('/api/sources')[0],404)
        self.assertEqual(self.request('/api/discover',{'query':'World'})[0],404)
        self.assertEqual(self.request('/api/series',{'game':{'title':'Portal'}})[0],404)
        self.assertEqual(self.request('/api/sources',{'kinopoisk':'fixture-key'})[0],404)
        self.assertEqual(self.request('/api/artwork',{'game':{}})[0],404)
        self.assertEqual(self.request('/instructions.html')[0],404)
        self.assertEqual(self.request('/media.js')[0],404)
        self.assertNotIn('interface_style',self.request('/api/settings',{'interface_style':'modern'})[1])
        with patch.object(server,'remote',side_effect=AssertionError('No network allowed')):
            with self.assertRaises(ValueError):server.search_games('Title','kinopoisk')
            with self.assertRaises(ValueError):server.details('kinopoisk:1')

    def test_metacritic_import_and_search(self):
        url = 'https://www.metacritic.com/game/jackal-assault/details/?x=1'
        self.assertEqual(server.metacritic_slug(url), 'jackal-assault')
        for bad in ('https://metacritic.com.evil.test/game/test/', 'https://example.com/game/test/', 'https://www.metacritic.com/movie/test/', 'https://www.metacritic.com/game/../test/'):
            self.assertIsNone(server.metacritic_slug(bad))
        metadata = {'@type':'VideoGame','name':'Jackal Assault','description':'English description', 'image':'https://example.com/a.jpg', 'datePublished':'2016-11-04', 'gamePlatform':['PlayStation 4'], 'genre':'Action'}
        page = '<script type="application/ld+json">' + json.dumps(metadata) + '</script>'
        with patch.object(server,'remote_html',return_value=page) as fetch:
            item=server.search_games(url, 'steam')[0]
            self.assertEqual(item['source_id'],'metacritic:jackal-assault')
            self.assertEqual(item['release_date'],'2016-11-04')
            self.assertEqual(item['description_language'],'original')
            self.assertEqual(server.details(item['source_id'])['available_platforms'],'PlayStation 4')
            saved=self.request('/api/save',{'game':item})[1]
            self.assertEqual(saved['source_url'],'https://www.metacritic.com/game/jackal-assault/')
            self.assertEqual(saved['description'],'English description')
        search = '<a href="/game/menu-game/">Navigation</a><a class="c-search-item search-item__content" href="/game/jackal-assault/"><img src="https://example.com/a.jpg?a=1&amp;b=2"><p class="c-search-item__title">Jackal Assault</p></a>'
        with patch.object(server,'remote_html',return_value=search):
            results=server.search_games('Jackal Assault', 'metacritic')
            self.assertEqual(len(results),1)
            self.assertEqual(results[0]['title'],'Jackal Assault')
            self.assertEqual(results[0]['image'],'https://example.com/a.jpg?a=1&b=2')
        search += '<a class="c-search-item" href="/game/other/"><p class="c-search-item__title">Call of Duty: Infinite Warfare</p></a><a class="c-search-item" href="/game/vr/"><p class="c-search-item__title">Call of Duty: Infinite Warfare Jackal Assault VR Experience</p></a>'
        with patch.object(server,'remote_html',return_value=search):
            self.assertEqual([x['source_id'] for x in server.search_games('Call of Duty Infinite Warfare Jackal Assault VR','metacritic')],['metacritic:vr'])
        with patch.object(server,'remote_html',return_value='<html>No game</html>'):
            with self.assertRaises(ValueError):server.details('metacritic:missing')
        with patch.object(server,'remote_html') as fetch:
            with self.assertRaises(ValueError):server.details('metacritic:../../secret')
            fetch.assert_not_called()

    def test_wikipedia_excludes_list_articles(self):
        titles=['List of PlayStation VR games','Lists of video games','Список игр Activision','Portal','Call of Duty: Infinite Warfare']
        payload={'query':{'pages':{str(i):{'pageid':i,'title':title,'index':i} for i,title in enumerate(titles)}}}
        with patch.object(server,'remote',return_value=payload):
            self.assertEqual([x['title'] for x in server.search_games('Jackal','wikipedia')],titles[3:])

    def test_bulk_atomic_and_delete_undo(self):
        a=self.request('/api/save',{'game':{'title':'One'}})[1]
        b=self.request('/api/save',{'game':{'title':'Two'}})[1]
        self.assertEqual(self.request('/api/bulk',{'ids':[a['id'],b['id']],'patch':{'platform':'My platform','favorite':True,'status':'Играю'}})[0],200)
        self.assertTrue(all(g['favorite'] and g['platform']=='My platform' for g in server.library()))
        self.assertEqual(self.request('/api/bulk',{'ids':[a['id'],9999],'patch':{'favorite':False}})[0],400)
        self.assertTrue(server.library()[0]['favorite'])
        before=server.library()
        deleted=self.request('/api/delete',{'id':a['id']})[1]
        self.assertEqual(self.request('/api/undo-delete',{'undo':deleted['undo']})[0],200)
        self.assertEqual(server.library(),before)
        self.assertEqual(self.request('/api/undo-delete',{'undo':deleted['undo']})[0],400)

    def test_backup_retention_and_complete_restore(self):
        self.request('/api/save',{'game':{'title':'Original','notes':'Keep'}})
        cover=b'\x89PNG\r\n\x1a\nfixture'
        import hashlib,zipfile
        name=hashlib.sha256(cover).hexdigest()+'.png'
        (server.DATA/'covers').mkdir(exist_ok=True)
        (server.DATA/'covers'/name).write_bytes(cover)
        with server.connection() as db:
            game=server.library()[0]
            game.update(image='https://example.com/cover.png',image_local='/covers/'+name)
            db.execute('UPDATE games SET payload=?',(json.dumps(game),))
        before=server.library()
        backup=server.create_backup()
        raw=server.backup_path(backup).read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:self.assertEqual(archive.read('covers/'+name),cover)
        for _ in range(12):server.create_backup()
        self.assertEqual(len(server.backup_files()),10)
        self.assertIsNone(server.create_backup(automatic=True))
        self.request('/api/save',{'id':before[0]['id'],'game':{'title':'Changed','notes':'Other'}})
        server.restore_backup(raw)
        self.assertEqual(server.library(),before)
        self.assertEqual(len(server.backup_files()),10)
        invalid=io.BytesIO()
        with zipfile.ZipFile(invalid,'w') as archive:
            archive.writestr('../evil','bad')
            archive.writestr('library.sqlite3','bad')
        with self.assertRaises(ValueError):server.restore_backup(invalid.getvalue())
        self.assertEqual(server.library(),before)
        self.assertEqual(self.request('/api/backup-restore',{'name':'../library.sqlite3'})[0],400)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = server.DATA, server.DB
        server.DATA = Path(self.tmp.name)
        server.DB = server.DATA / 'test.sqlite3'
        server.init_db()
        self.cover_mock = patch.object(server, 'archive_cover', return_value='')
        self.cover_mock.start()
        self.http = server.LocalServer(('127.0.0.1', 0), server.Handler)
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.url = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.cover_mock.stop()
        self.http.shutdown()
        self.http.server_close()
        self.worker.join()
        server.DATA, server.DB = self.original
        self.tmp.cleanup()

    def request(self, path, data=None, authorized=True):
        request = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers={'Content-Type':'application/json', 'X-Library-Token':server.TOKEN if authorized else ''})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.load(exc)

    def test_local_covers_and_safe_caching(self):
        self.cover_mock.stop()
        png=b'\x89PNG\r\n\x1a\nfixture'
        image='https://example.com/cover.png'
        with patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(png)):
            game=server.save_game({'title':'Cover','source_id':'steam:380','image':image,'notes':'Keep','favorite':True})
        self.assertTrue(game['image_local'].startswith('/covers/'))
        self.assertEqual((server.DATA/game['image_local'].lstrip('/')).read_bytes(),png)
        with urllib.request.urlopen(self.url+game['image_local']) as response:
            self.assertEqual(response.read(),png)
            self.assertEqual(response.headers['Content-Type'],'image/png')
        crop={'x':0,'y':0,'width':1,'height':.3,'image':image}
        self.request('/api/save',{'id':game['id'],'game':{'title':'Cover','thumbnail_crop':crop}})
        with patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(png+b'new')):
            changed=server.update_cover(game['id'])
        self.assertNotEqual(changed['image_local'],game['image_local'])
        self.assertIsNone(changed['thumbnail_crop'])
        self.assertEqual(changed['notes'],'Keep')
        self.assertTrue(changed['favorite'])
        with patch.object(server.urllib.request,'urlopen',side_effect=OSError('offline')):
            with self.assertRaises(OSError):server.update_cover(game['id'])
        self.assertEqual(server.library()[0]['image_local'],changed['image_local'])
        self.assertTrue((server.DATA/game['image_local'].lstrip('/')).is_file())
        clone=dict(changed, source_id='')
        with patch.object(server,'archive_cover',side_effect=AssertionError('Import must reuse local archive')):
            self.assertEqual(self.request('/api/import',{'version':1,'games':[clone]})[0],200)
        self.assertEqual(server.library()[-1]['image_local'],changed['image_local'])
        with patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(b'<html>error</html>')):
            with self.assertRaises(ValueError):server.archive_cover(image)

    def test_thumbnail_crop_persistence_and_validation(self):
        image='https://example.com/cover.jpg'
        crop={'x':0,'y':0.25,'width':1,'height':0.3,'image':image}
        game=self.request('/api/save',{'game':{'title':'Cover','image':image,'notes':'Keep','favorite':True}})[1]
        status,saved=self.request('/api/save',{'id':game['id'],'game':{'title':'Cover','thumbnail_crop':crop}})
        self.assertEqual(status,200)
        self.assertEqual(saved['thumbnail_crop'],crop)
        self.assertEqual(saved['notes'],'Keep')
        self.assertTrue(saved['favorite'])
        server.init_db()
        exported=self.request('/api/export')[1]
        self.assertEqual(exported['games'][0]['thumbnail_crop'],crop)
        self.assertEqual(self.request('/api/import',exported)[0],200)
        self.assertEqual(server.library()[-1]['thumbnail_crop'],crop)
        for bad in [dict(crop,width=0),dict(crop,y=.9),dict(crop,x=True),dict(crop,x=float('nan')),dict(crop,image=42),'bad']:
            self.assertEqual(self.request('/api/save',{'id':game['id'],'game':{'title':'Cover','thumbnail_crop':bad}})[0],400)
        self.assertEqual(server.library()[0]['thumbnail_crop'],crop)
        changed=self.request('/api/save',{'id':game['id'],'game':{'title':'Cover','image':'https://example.com/new.jpg'}})[1]
        self.assertIsNone(changed['thumbnail_crop'])
        reset=self.request('/api/save',{'id':game['id'],'game':{'title':'Cover','thumbnail_crop':None}})[1]
        self.assertIsNone(reset['thumbnail_crop'])

    def test_save_edit_export_delete(self):
        status, a = self.request('/api/save', {'game':{'title':'Ведьмак', 'notes':'Русская заметка', 'platform':'Моя консоль', 'release_date':'2015'}})
        self.assertEqual(status, 200)
        self.assertEqual(a['status'], 'Хочу пройти')
        status, b = self.request('/api/save', {'id':a['id'], 'game':{'title':'Ведьмак', 'notes':'Изменено', 'added_at':'2000-01-01'}})
        self.assertEqual(b['added_at'], a['added_at'])
        self.assertEqual(b['platform'], 'Моя консоль')
        self.assertEqual(self.request('/api/library')[1]['games'][0]['notes'], 'Изменено')
        self.assertEqual(self.request('/api/export')[1]['games'][0]['title'], 'Ведьмак')
        self.assertEqual(self.request('/api/delete', {'id':a['id']})[0], 200)
        self.assertEqual(server.library(), [])

    def test_duplicate_and_validation(self):
        record = {'title':'Game', 'source_id':'steam:1'}
        self.assertEqual(self.request('/api/save', {'game':record})[0], 200)
        self.assertEqual(self.request('/api/save', {'game':record})[0], 409)
        for fields in ({'release_date':'2026-99-50'}, {'image':'javascript:alert(1)'}, {'status':'random'}, {'added_at':'garbage'}):
            self.assertEqual(self.request('/api/save', {'game':dict(title='Bad', **fields)})[0], 400)
        self.assertEqual(self.request('/api/save', {'game':{'title':'No auth'}}, False)[0], 403)
        self.assertEqual(len(server.library()), 1)

    def test_atomic_import_and_round_trip(self):
        result = self.request('/api/import', {'version':1,'games':[{'title':'A'}, {'title':''}]})
        self.assertEqual(result[0], 400)
        self.assertEqual(server.library(), [])
        data = {'version':1, 'games':[{'title':'A','source_id':'steam:1'}, {'title':'B','source_id':'steam:2'}]}
        self.assertEqual(self.request('/api/import', data)[1]['added'], 2)
        exported = self.request('/api/export')[1]
        result = self.request('/api/import', exported)[1]
        self.assertEqual(result, {'added':0, 'skipped':2})
        self.assertEqual(len(server.library()), 2)

    def test_single_instance_port(self):
        with self.assertRaises(OSError):
            second = server.LocalServer(('127.0.0.1', self.http.server_port), server.Handler)
            second.server_close()

    def test_favorites_and_platform_registry(self):
        _, game = self.request('/api/save', {'game':{'title':'First','platform':'Steam','notes':'Keep me'}})
        _, favorite = self.request('/api/save', {'id':game['id'],'game':{'title':'First','favorite':True}})
        self.assertIs(favorite['favorite'], True)
        self.assertEqual(favorite['notes'], 'Keep me')
        self.assertIn('Steam', self.request('/api/library')[1]['platforms'])
        exported = self.request('/api/export')[1]
        self.assertIs(exported['games'][0]['favorite'], True)
        self.assertIn('Steam', exported['platforms'])
        self.request('/api/save', {'id':game['id'],'game':{'title':'First','favorite':False,'platform':'GOG'}})
        self.assertIs(server.library()[0]['favorite'], False)
        self.request('/api/delete', {'id':game['id']})
        server.init_db()
        self.assertIn('Steam', server.platform_names())
        self.assertIn('GOG', server.platform_names())
        self.request('/api/import', exported)
        self.assertIs(server.library()[0]['favorite'], True)

    def test_existing_platform_migration(self):
        # Simulate a library written by the previous version without a registry.
        with server.connection() as db:
            db.execute('INSERT INTO games(payload) VALUES (?)', (json.dumps({'title':'Old','platform':'Steam'}),))
        server.init_db()
        self.assertIn('Steam', self.request('/api/library')[1]['platforms'])

    def test_russian_descriptions(self):
        self.assertEqual(server.clean('<p>Первый абзац.</p><p>Второй абзац.</p>'), 'Первый абзац.\n\nВторой абзац.')
        text = 'Введение об игре.\n\n== Игровой процесс ==\nСражения и исследование.\n\n== Сюжет ==\nСпойлер.'
        description = server.wiki_description(text)
        self.assertIn('Сражения', description)
        self.assertNotIn('Спойлер', description)
        english = {'title':'Game','pageid':1,'langlinks':[{'lang':'ru','*':'Игра'}]}
        russian = {'title':'Игра','pageid':2,'extract':text}
        with patch.object(server, 'wiki_page', side_effect=[english,russian]):
            lang,page = server.localized_wiki_page('en',pageids='1')
        self.assertEqual(lang,'ru')
        self.assertEqual(page['title'],'Игра')

    def test_steam_search_filters_real_types_and_keeps_editions(self):
        payload={'items':[{'type':'app','id':2,'name':'Game - Map Pack'},{'type':'app','id':1,'name':'Game - Gold Edition'},{'type':'app','id':3,'name':'Game - Soundtrack'},{'type':'app','id':4,'name':'Game - Demo'}]}
        def result(appid):
            kind={'1':'game','2':'dlc','3':'music','4':'demo'}[appid]
            return {'source_id':'steam:'+appid,'title':next(x['name'] for x in payload['items'] if str(x['id'])==appid),'steam_type':kind,'provider':'Steam'}
        with patch.object(server,'remote',return_value=payload),patch.object(server,'steam_result',side_effect=result),patch.object(server,'steam_title_fallback',side_effect=lambda query,items:items):
            self.assertEqual([g['source_id'] for g in server.search_games('Game')],['steam:1'])
            all_items=server.search_games('Game',include_extras=True)
            self.assertEqual(all_items[0]['source_id'],'steam:1')
            self.assertEqual(len(all_items),4)
        with patch.object(server,'remote',return_value=payload),patch.object(server,'steam_result',side_effect=OSError('offline')),patch.object(server,'steam_title_fallback',side_effect=lambda query,items:items):
            unchecked=server.search_games('Game')
            self.assertEqual(len(unchecked),4)
            self.assertTrue(all(g['steam_type']=='unknown' for g in unchecked))

    def test_steam_link_and_unlisted_title(self):
        url = 'https://store.steampowered.com/app/380/HalfLife_2_Episode_One/?l=russian'
        self.assertEqual(server.steam_app_id(url), '380')
        self.assertEqual(server.steam_app_id('380'), '380')
        self.assertEqual(server.steam_app_id('steam:380'), '380')
        for bad in ('https://store.steampowered.com.evil.test/app/380/', 'https://example.com/app/380/', 'https://store.steampowered.com/app/not-a-number/'):
            self.assertIsNone(server.steam_app_id(bad))
        with patch.object(server, 'steam_result', return_value={'source_id':'steam:380','title':'Half-Life 2: Episode One'}) as direct:
            self.assertEqual(server.search_games(url)[0]['source_id'], 'steam:380')
            direct.assert_called_once_with('380')
        search = {'search':[{'id':'Q18951','label':'Half-Life 2: Episode One'}]}
        data = {'claims':{'P1733':[{'mainsnak':{'datavalue':{'value':'380'}}}]}}
        existing = [{'source_id':'steam:323150','title':'Half-Life 2: Episode One Soundtrack'}]
        with patch.object(server,'remote',return_value=search), patch.object(server,'entity',return_value=data), patch.object(server,'steam_result',return_value={'source_id':'steam:380','title':'Half-Life 2: Episode One'}):
            result = server.steam_title_fallback('Half-Life 2 Episode One',existing)
        self.assertEqual(result[0]['source_id'],'steam:380')
        self.assertEqual(result[0]['qid'],'Q18951')

    def test_manual_order_survives_edits_and_new_games(self):
        games=[self.request('/api/save',{'game':{'title':x}})[1] for x in ['A','B','C','D']]
        a,b,c,d=[x['id'] for x in games]
        self.assertEqual(self.request('/api/reorder',{'id':d,'target':b})[0],200)
        self.assertEqual([x['id'] for x in server.library()],[a,d,b,c])
        self.request('/api/save',{'id':d,'game':{'title':'D edited','manual_order':999}})
        self.assertEqual([x['id'] for x in server.library()],[a,d,b,c])
        self.request('/api/reorder',{'id':a,'target':c,'after':True})
        self.assertEqual([x['id'] for x in server.library()],[d,b,c,a])
        self.assertEqual(self.request('/api/reorder',{'id':999,'target':a})[0],400)
        self.request('/api/save',{'game':{'title':'New'}})
        server.init_db()
        self.assertEqual([x['title'] for x in server.library()],['D edited','B','C','A','New'])

    def test_category_management_and_preferences(self):
        self.assertEqual(self.request('/api/categories',{'action':'add','name':'С друзьями'})[0],200)
        self.request('/api/settings',{'default_category':'С друзьями','hidden_categories':['Брошено'],'show_card_notes':False})
        game=self.request('/api/save',{'game':{'title':'Game','notes':'Keep'}})[1]
        self.assertEqual(game['status'],'С друзьями')
        self.request('/api/categories',{'action':'rename','name':'С друзьями','replacement':'Кооператив'})
        self.assertEqual(server.library()[0]['status'],'Кооператив')
        self.assertEqual(server.settings()['default_category'],'Кооператив')
        exported=self.request('/api/export')[1]
        self.assertIn('Кооператив',exported['categories'])
        self.request('/api/categories',{'action':'delete','name':'Кооператив','replacement':'Хочу пройти'})
        self.assertEqual(server.library()[0]['notes'],'Keep')
        self.assertEqual(server.library()[0]['status'],'Хочу пройти')
        self.assertEqual(server.settings()['default_category'],'Хочу пройти')
        server.init_db()
        self.assertNotIn('Кооператив',server.category_names())
        self.assertEqual(server.settings()['show_card_notes'],False)
        self.assertEqual(self.request('/api/import',exported)[0],200)
        self.assertIn('Кооператив',server.category_names())
        self.assertEqual(server.settings()['default_category'],'Кооператив')

    def test_platform_rename_delete_does_not_recreate_defaults(self):
        game=self.request('/api/save',{'game':{'title':'Game','platform':'PC','favorite':True}})[1]
        self.assertEqual(self.request('/api/platforms',{'action':'rename','name':'PC','replacement':'Компьютер'})[0],200)
        self.assertEqual(server.library()[0]['platform'],'Компьютер')
        self.request('/api/platforms',{'action':'delete','name':'Компьютер','replacement':'Пока неизвестно'})
        server.init_db()
        self.assertNotIn('PC',server.platform_names())
        self.assertNotIn('Компьютер',server.platform_names())
        self.assertTrue(server.library()[0]['favorite'])
        self.assertEqual(server.library()[0]['platform'],'Пока неизвестно')
        self.assertEqual(self.request('/api/platforms',{'action':'delete','name':'Пока неизвестно','replacement':'Steam Deck'})[0],400)


if __name__ == '__main__':
    unittest.main()
