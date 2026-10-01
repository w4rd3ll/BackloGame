import threading
import unittest
from desktop_close import CloseController


class CloseTests(unittest.TestCase):
    def test_event_returns_while_javascript_waits_and_ignores_duplicate_clicks(self):
        entered, release = threading.Event(), threading.Event()
        class Window:
            calls = 0
            def run_js(self, script):
                self.calls += 1
                entered.set()
                release.wait(2)
        window = Window()
        controller = CloseController(window)
        controller.ready.set()
        try:
            self.assertFalse(controller.on_closing())
            self.assertTrue(entered.wait(1))
            self.assertFalse(controller.on_closing())
            self.assertEqual(window.calls, 1)
        finally:
            release.set()

    def test_approved_close_and_close_before_load_do_not_call_javascript(self):
        class Window:
            def destroy(self):
                self.result = controller.on_closing()
        window = Window()
        controller = CloseController(window)
        self.assertTrue(controller.on_closing())
        controller.ready.set()
        controller.approve()
        self.assertTrue(window.result)


if __name__ == '__main__':
    unittest.main()
