"""Never wait for WebView JavaScript inside the native closing event."""
import logging
import threading


class CloseController:
    def __init__(self, window):
        self.window = window
        self.allowed = threading.Event()
        self.ready = threading.Event()
        self.pending = threading.Lock()

    def approve(self):
        self.allowed.set()
        self.window.destroy()

    def on_closing(self):
        if self.allowed.is_set() or not self.ready.is_set():
            return True
        if self.pending.acquire(blocking=False):
            threading.Thread(target=self._check, daemon=True).start()
        return False

    def _check(self):
        try:
            self.window.run_js('desktopCloseRequest();')
        except Exception:
            logging.exception('Could not check unsaved changes before closing')
        finally:
            self.pending.release()
