import base64
import json
import hashlib
import io

from PIL import Image
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import library_share
import server


class SharingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        self.patches = [patch.object(server, 'DATA', self.data), patch.object(server, 'DB', self.data/'library.sqlite3')]
        for item in self.patches:
            item.start()
        server.init_db()
        self.game = server.save_game({'title':'Portal <2>', 'series':'Portal', 'status':'Пройдено',
                                     'completed_at':'2019-01-02', 'platform':'PC', 'notes':'private-note',
                                     'description':'private-description', 'source_url':'https://example.com/private'})
        self.second = server.save_game({'title':'Other', 'platform':'PS3'})

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def export(self, **options):
        return library_share.export(server, dict(ids=[self.game['id']], title='My games', language='en', **options))

    def test_only_selected_public_fields_and_order_without_mutations(self):
        before = server.library()
        result = self.export()
        self.assertIn('Portal &lt;2&gt;', result['html'])
        self.assertIn('Completed', result['html'])
        self.assertIn('2019-01-02', result['html'])
        for private in ('private-note', 'private-description', 'example.com/private', 'Other', server.TOKEN):
            self.assertNotIn(private, result['html'])
        self.assertEqual(server.library(), before)
        self.assertEqual(server.backup_files(), [])
        result = library_share.export(server, dict(ids=[self.second['id'],self.game['id'],self.second['id']],title='Ordered'))
        self.assertEqual(result['count'], 2)
        self.assertLess(result['html'].index('<h2>Other'), result['html'].index('<h2>Portal'))

    def test_opt_in_notes_and_all_user_text_are_escaped(self):
        server.save_game({'title':'Portal <2>', 'notes':'<script>alert(1)</script>'}, self.game['id'])
        result = self.export(notes=True)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', result['html'])
        self.assertNotIn('<script>', result['html'])
        self.assertIn("default-src 'none'", result['html'])

    def test_embedded_local_cover_and_no_network_dependencies(self):
        cover = '/covers/' + 'a'*64 + '.png'
        path = self.data/cover.lstrip('/')
        path.parent.mkdir()
        output = io.BytesIO()
        Image.new('RGB',(600,900),'teal').save(output,format='PNG')
        raw = output.getvalue()
        path.write_bytes(raw)
        server.save_game({'title':'Portal <2>', 'image_local':cover}, self.game['id'])
        result = self.export()
        self.assertIn('data:image/webp;base64,', result['html'])
        self.assertEqual(path.read_bytes(),raw)
        self.assertEqual(result['missing_covers'], 0)
        self.assertNotIn('/covers/', result['html'])
        result = self.export(covers=False)
        self.assertNotIn('data:image/', result['html'])

    def test_cover_compression_size_transparency_and_metadata(self):
        image=Image.effect_noise((1200,1800),70).convert('RGBA')
        image.putpixel((0,0),(0,0,0,0))
        original=io.BytesIO();image.save(original,format='PNG')
        raw=original.getvalue();before=hashlib.sha256(raw).digest()
        encoded=library_share.compressed_cover(raw)
        compact=base64.b64decode(encoded.split(',',1)[1])
        with Image.open(io.BytesIO(compact)) as thumb:
            self.assertEqual(thumb.format,'WEBP')
            self.assertLessEqual(thumb.width,224)
            self.assertLessEqual(thumb.height,300)
            self.assertEqual(thumb.mode,'RGBA')
            self.assertFalse(thumb.getexif())
        self.assertLess(len(compact),len(raw)//20)
        self.assertEqual(hashlib.sha256(raw).digest(),before)

    def test_invalid_cover_uses_other_candidate_and_shared_cover_is_encoded_once(self):
        cover='/covers/'+'b'*64+'.png'
        fallback='/covers/'+'c'*64+'.png'
        (self.data/'covers').mkdir()
        (self.data/cover.lstrip('/')).write_bytes(b'broken image')
        output=io.BytesIO();Image.new('RGB',(100,50),'red').save(output,format='PNG')
        (self.data/fallback.lstrip('/')).write_bytes(output.getvalue())
        game={'image_local':fallback,'custom_covers':{'portrait':{'local':cover}}}
        cache={}
        with patch.object(library_share,'compressed_cover',wraps=library_share.compressed_cover) as compress:
            first=library_share.local_cover(server,game,cache)
            second=library_share.local_cover(server,game,cache)
            self.assertEqual(first,second)
            self.assertTrue(first.startswith('data:image/webp;base64,'))
            self.assertEqual(compress.call_count,2)

    def test_missing_cover_and_unsafe_paths_are_not_read(self):
        with server.connection() as db:
            row = dict(self.game, image_local='/../credentials.png')
            db.execute('UPDATE games SET payload=? WHERE id=?', (json.dumps(row), self.game['id']))
        result = self.export()
        self.assertEqual(result['missing_covers'], 1)
        self.assertIn('No cover', result['html'])

    def test_input_validation_and_deleted_selection(self):
        for patch_data in ({'ids':[]}, {'ids':[True]}, {'ids':['1']}, {'title':' '}, {'title':'x'*201},
                           {'notes':'yes'}, {'covers':1}, {'language':'de'}, {'language':[]}, {'ids':[99999]}):
            with self.subTest(patch_data=patch_data), self.assertRaises(ValueError):
                library_share.export(server, dict({'ids':[self.game['id']],'title':'Games'},**patch_data))

    def test_russian_labels_and_safe_filename(self):
        result = library_share.export(server, dict(ids=[self.game['id']],title='../Пройдено <img>',language='ru'))
        self.assertIn('lang="ru"', result['html'])
        self.assertIn('Пройдено: 2019-01-02', result['html'])
        self.assertIn('&lt;img&gt;', result['html'])
        self.assertNotIn('/', result['filename'])
        self.assertNotIn('<', result['filename'])


if __name__ == '__main__':
    unittest.main()
