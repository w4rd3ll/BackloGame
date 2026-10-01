import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import desktop_platform


class PlatformTests(unittest.TestCase):
    def test_windows_uses_system_webview(self):
        options = desktop_platform.webview_options(Path('/app'), 'win32')
        self.assertEqual(options['gui'], 'edgechromium')
        self.assertTrue(options['icon'].endswith('.ico'))

    def test_linux_does_not_force_windows_backend(self):
        options = desktop_platform.webview_options(Path('/app'), 'linux')
        self.assertNotIn('gui', options)
        self.assertTrue(options['icon'].endswith('.png'))
        self.assertNotIn('WebView2', desktop_platform.startup_help('linux'))
        with patch.object(sys, 'platform', 'linux'):
            desktop_platform.prepare_application()


if __name__ == '__main__':
    unittest.main()
