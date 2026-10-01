"""Small OS adapter; library and window lifecycle stay platform independent."""
import sys


def webview_options(root, platform=None):
    platform = platform or sys.platform
    if platform == 'win32':
        return {'gui': 'edgechromium', 'icon': str(root / 'static' / 'app-icon.ico')}
    # pywebview selects an installed GTK/WebKit or Qt backend on Linux.
    return {'icon': str(root / 'static' / 'app-icon.png')}


def prepare_application():
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('BackloGame.Backlog')


def startup_help(platform=None):
    platform = platform or sys.platform
    if platform == 'win32':
        return ('BackloGame requires Microsoft Edge WebView2 Runtime. If it is missing, '
                'download Evergreen Runtime from https://developer.microsoft.com/microsoft-edge/webview2/ .')
    return 'Install a pywebview backend for your OS (GTK/WebKit or Qt on Linux).'


def show_error(text):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, 'BackloGame', 0x10)
    else:
        print(text, file=sys.stderr)
