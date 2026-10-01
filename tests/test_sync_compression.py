import gzip
import io
import unittest
from unittest.mock import patch

import library_sync


class CompressionTests(unittest.TestCase):
    def response(self, raw):
        response = io.BytesIO(gzip.compress(raw))
        response.headers = {'Content-Encoding': 'gzip'}
        return response

    def test_gzip_library_is_decoded(self):
        body = b'{"games":[{"title":"Portal","source_id":"steam:400"}]}'
        with patch.object(library_sync.urllib.request, 'urlopen', return_value=self.response(body)) as open_url:
            games = library_sync.fetch_steam_relay('test', 'https://example.com')
            self.assertEqual(games[0]['source_id'], 'steam:400')
            self.assertEqual(open_url.call_args.args[0].get_header('Accept-encoding'), 'gzip')

    def test_decompressed_size_is_bounded(self):
        with patch.object(library_sync.urllib.request, 'urlopen', return_value=self.response(b'x' * 8_000_001)):
            with self.assertRaisesRegex(ValueError, 'Список слишком большой'):
                library_sync.request('https://example.com')
