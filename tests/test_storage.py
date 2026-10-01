import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import server
import storage


class PortableStorageTests(unittest.TestCase):
    def test_frozen_storage_is_beside_executable(self):
        with patch.dict(storage.os.environ, {}, clear=True), patch.object(storage.sys,'frozen',True,create=True), patch.object(storage.sys,'executable',str(Path(tempfile.gettempdir())/'BackloGame'/'BackloGame.exe')):
            self.assertEqual(storage.user_data_directory(),Path(tempfile.gettempdir())/'BackloGame'/'data')

    def test_explicit_relative_path_becomes_absolute_without_migration(self):
        original=server.DATA,server.DB
        try:
            with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
                server.configure_data(Path(directory).relative_to(Path.cwd()))
                self.assertTrue(server.DATA.is_absolute())
                self.assertFalse(server.DB.exists())
                server.init_db()
                self.assertEqual(server.library(),[])
        finally:
            server.DATA,server.DB=original
