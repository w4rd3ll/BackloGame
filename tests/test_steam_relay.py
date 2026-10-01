import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import library_sync
import server


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        Path(self.work.name,'steam_api_key').write_text('')
        spec=importlib.util.spec_from_file_location('relay_test',Path(__file__).parents[1]/'deploy/steam-relay/relay.py')
        self.relay=importlib.util.module_from_spec(spec)
        with patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':self.work.name}):spec.loader.exec_module(self.relay)
    def tearDown(self):self.work.cleanup()
    def test_unconfigured_does_not_call_steam(self):
        with patch.object(self.relay,'fetch_steam') as fetch:
            with self.assertRaises(ValueError):self.relay.library('w4rd3ll')
            fetch.assert_not_called()
    def test_cached_public_library_contains_no_key(self):
        self.relay.KEY='test-only-placeholder'
        result=[{'title':'Portal','source_id':'steam:400'}]
        with patch.object(self.relay,'fetch_steam',return_value=result) as fetch:
            self.assertEqual(self.relay.library('w4rd3ll'),result)
            self.assertEqual(self.relay.library('w4rd3ll'),result)
            self.assertEqual(fetch.call_count,1)
            self.assertNotIn(self.relay.KEY,str(result))
    def test_other_hosts_rejected(self):
        self.relay.KEY='test-only-placeholder'
        with patch.object(self.relay,'fetch_steam') as fetch:
            with self.assertRaises(ValueError):self.relay.library('https://example.com/profile')
            fetch.assert_not_called()
    def test_global_upstream_limit(self):
        self.relay.KEY='test-only-placeholder'
        self.relay.DAILY.update(day=int(self.relay.time.time()//86400),count=5000)
        with patch.object(self.relay,'fetch_steam') as fetch:
            with self.assertRaises(ValueError):self.relay.library('w4rd3ll')
            fetch.assert_not_called()
    def test_client_only_sends_profile_and_rebuilds_trusted_urls(self):
        response='{"games":[{"title":"Portal","source_id":"steam:400","image":"http://127.0.0.1/private","notes":"injected"}]}'
        with patch.object(library_sync,'request',return_value=response) as request:
            games=library_sync.fetch_steam_relay('w4rd3ll','https://example.com')
            request.assert_called_once_with('https://example.com/v1/steam/library?profile=w4rd3ll')
            self.assertTrue(games[0]['image'].startswith('https://cdn.akamai.steamstatic.com/'))
            self.assertNotIn('notes',games[0])
            self.assertEqual(games[0]['tags'],'Steam')
    def test_service_settings_reject_http_and_embedded_credentials(self):
        for value in ('http://example.com','https://user:pass@example.com','https://example.com?key=secret'):
            with self.assertRaises(ValueError):server.validate_settings({'steam_relay_url':value})
        self.assertEqual(server.validate_settings({'steam_relay_url':'https://example.com/'}),{'steam_relay_url':'https://example.com'})


if __name__=='__main__':unittest.main()
