"""Regression tests for LunaGUI chat queue behavior."""

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from app.ui import luna as luna_module
from app.ui.chat_controller import ChatController
from app.ui.luna import LunaGUI


class ImmediateThread:
    def __init__(self, target, daemon=True):
        self.target = target

    def start(self):
        self.target()

    def is_alive(self):
        return False


class ImmediateTimer:
    @staticmethod
    def singleShot(delay, callback):
        callback()


class DeferredTimer:
    callbacks = []

    @classmethod
    def singleShot(cls, delay, callback):
        cls.callbacks.append(callback)


from threading import Thread as RealThread

class BlockingThread:
    instances = []

    def __init__(self, target, daemon=True):
        self.target = target
        self._thread = None
        self._alive = False
        self.instances.append(self)

    def start(self):
        self._alive = True

        def run():
            try:
                self.target()
            finally:
                self._alive = False

        self._thread = RealThread(target=run, daemon=True)
        self._thread.start()

    def is_alive(self):
        return self._alive and self._thread is not None and self._thread.is_alive()

    def join(self):
        if self._thread is not None:
            self._thread.join()


def make_gui():
    gui = SimpleNamespace()
    gui.user_name = "User"
    gui.input_edit = SimpleNamespace(text=Mock(return_value="hello"), clear=Mock())
    gui.msg_layout = SimpleNamespace()
    gui.chat_view = SimpleNamespace(
        voice_output_enabled=False,
        set_api_connected=Mock(),
    )
    gui._set_current_view = Mock()
    gui._speak = Mock()
    gui.settings_controller = None
    gui.chat_controller = None
    return gui


def bind(gui):
    for name in (
        "_on_send_clicked",
        "_on_message_submitted",
        "_handle_chat_response",
        "_handle_chat_error",
    ):
        setattr(gui, name, LunaGUI.__dict__[name].__get__(gui, type(gui)))


class TestLunaGUIChatQueue(unittest.TestCase):
    def setUp(self):
        self.gui = make_gui()
        bind(self.gui)
        BlockingThread.instances.clear()
        DeferredTimer.callbacks.clear()
        self.mock_agent = Mock()
        self.mock_agent.process_message.return_value = "agent reply"
        self.display_user = patch("app.ui.luna._display_user_message").start()
        self.display_agent = patch("app.ui.luna._display_agent_message").start()
        self.gui.chat_controller = ChatController(
            agent_service_factory=lambda: self.mock_agent,
            on_response=self.gui._handle_chat_response,
            on_error=self.gui._handle_chat_error,
        )
        self.addCleanup(patch.stopall)

    def test_submitted_message_enqueues_through_chat_controller(self):
        self.gui.chat_controller.enqueue = Mock()
        LunaGUI._on_message_submitted(self.gui, "hello")
        self.gui.chat_controller.enqueue.assert_called_once_with("hello")
        self.display_user.assert_called_once_with(
            "hello", self.gui.msg_layout, username="User"
        )

    def test_empty_submission_does_not_enqueue(self):
        self.gui.chat_controller.enqueue = Mock()
        self.gui.input_edit.text.return_value = ""
        LunaGUI._on_message_submitted(self.gui, "")
        self.gui.chat_controller.enqueue.assert_not_called()
        self.display_user.assert_not_called()

    def test_send_clicked_submits_current_input(self):
        self.gui.chat_controller.enqueue = Mock()
        self.gui.input_edit.text.return_value = "typed"
        LunaGUI._on_send_clicked(self.gui)
        self.gui.chat_controller.enqueue.assert_called_once_with("typed")

    def test_messages_processed_in_fifo_order(self):
        self.mock_agent.process_message.side_effect = lambda message: f"reply:{message}"
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            LunaGUI._on_message_submitted(self.gui, "first")
            LunaGUI._on_message_submitted(self.gui, "second")
        self.assertEqual(
            self.display_agent.call_args_list,
            [call("reply:first", self.gui.msg_layout), call("reply:second", self.gui.msg_layout)],
        )

    def test_agent_exception_does_not_block_queue(self):
        self.mock_agent.process_message.side_effect = [
            RuntimeError("boom"),
            "second reply",
        ]
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            LunaGUI._on_message_submitted(self.gui, "first")
            LunaGUI._on_message_submitted(self.gui, "second")
        self.assertEqual(
            self.display_agent.call_args_list,
            [
                call("An internal error occurred while processing your message.", self.gui.msg_layout),
                call("second reply", self.gui.msg_layout),
            ],
        )

    def test_responses_reach_display_callback(self):
        self.mock_agent.process_message.return_value = "displayed response"
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            LunaGUI._on_message_submitted(self.gui, "hello")
        self.display_agent.assert_called_once_with("displayed response", self.gui.msg_layout)

    def test_tts_invoked_when_voice_output_enabled(self):
        self.gui.chat_view.voice_output_enabled = True
        self.mock_agent.process_message.return_value = "spoken response"
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            LunaGUI._on_message_submitted(self.gui, "hello")
        self.gui._speak.assert_called_once_with("spoken response")

    def test_tts_not_invoked_when_voice_output_disabled(self):
        self.gui.chat_view.voice_output_enabled = False
        self.mock_agent.process_message.return_value = "silent response"
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            LunaGUI._on_message_submitted(self.gui, "hello")
        self.gui._speak.assert_not_called()

if __name__ == "__main__":
    unittest.main()


from app.ui.chat_controller import ChatController


class TestChatController(unittest.TestCase):
    def setUp(self):
        self.mock_agent = Mock()
        self.mock_agent.process_message.return_value = "agent reply"
        self.on_response = Mock()
        self.on_error = Mock()
        self.on_finished = Mock()
        self.controller = ChatController(
            agent_service_factory=lambda: self.mock_agent,
            on_response=self.on_response,
            on_error=self.on_error,
            on_processing_finished=self.on_finished,
        )
        BlockingThread.instances.clear()
        DeferredTimer.callbacks.clear()

    def test_enqueue_adds_messages_in_fifo_order(self):
        self.controller._processing_message = True
        self.controller.enqueue("first")
        self.controller.enqueue("second")
        self.assertEqual(self.controller._message_queue, ["first", "second"])
        self.assertTrue(self.controller._processing_message)

    def test_responses_reach_on_response_in_order(self):
        self.mock_agent.process_message.side_effect = lambda message: f"reply:{message}"
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            self.controller.enqueue("first")
            self.controller.enqueue("second")
        self.assertEqual(
            self.on_response.call_args_list,
            [call("reply:first"), call("reply:second")],
        )

    def test_processing_continues_after_each_response(self):
        self.mock_agent.process_message.side_effect = lambda message: f"reply:{message}"
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            self.controller.enqueue("first")
            self.controller.enqueue("second")
        self.assertEqual(self.mock_agent.process_message.call_count, 2)
        self.assertFalse(self.controller._processing_message)

    def test_only_one_worker_active_at_a_time(self):
        active = 0
        max_active = 0

        def process_message(message):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            active -= 1
            return f"reply:{message}"

        self.mock_agent.process_message.side_effect = process_message
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            self.controller.enqueue("first")
            self.controller.enqueue("second")
    def test_exceptions_reach_on_error(self):
        self.mock_agent.process_message.side_effect = RuntimeError("boom")
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            self.controller.enqueue("hello")
        self.on_error.assert_called_once()
        self.assertIsInstance(self.on_error.call_args[0][0], RuntimeError)
        self.on_response.assert_not_called()

    def test_queue_continues_after_exception(self):
        self.mock_agent.process_message.side_effect = [
            RuntimeError("boom"),
            "second reply",
        ]
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            self.controller.enqueue("first")
            self.controller.enqueue("second")
        self.assertEqual(self.on_response.call_args_list, [call("second reply")])
        self.assertFalse(self.controller._processing_message)

    def test_processing_flag_resets_when_queue_empty(self):
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            self.controller.enqueue("hello")
        self.assertFalse(self.controller._processing_message)
        self.assertEqual(self.controller._message_queue, [])

    def test_on_processing_finished_invoked(self):
        with (
            patch("threading.Thread", ImmediateThread),
            patch("PySide6.QtCore.QTimer", ImmediateTimer),
        ):
            self.controller.enqueue("hello")
        self.on_finished.assert_called_once()

    def test_callback_delivery_is_scheduled_not_direct(self):
        release = threading.Event()
        callback_thread = {}

        def process_message(message):
            release.wait()
            return "reply"

        on_response = Mock(side_effect=lambda response: callback_thread.__setitem__("thread", threading.current_thread()))

        controller = ChatController(
            agent_service_factory=lambda: self.mock_agent,
            on_response=on_response,
            on_error=self.on_error,
            on_processing_finished=self.on_finished,
        )
        self.mock_agent.process_message.side_effect = process_message

        with (
            patch("threading.Thread", BlockingThread),
            patch("PySide6.QtCore.QTimer", DeferredTimer),
        ):
            controller.enqueue("hello")
            self.assertEqual(on_response.call_count, 0)
            release.set()
            BlockingThread.instances[-1].join()
            self.assertEqual(on_response.call_count, 0)
            DeferredTimer.callbacks.pop(0)()
            self.assertEqual(on_response.call_count, 1)
            self.assertIs(callback_thread["thread"], threading.main_thread())
            DeferredTimer.callbacks.pop(0)()

        self.assertFalse(controller._processing_message)
    def test_fifo_order_with_active_worker(self):
        DeferredTimer.callbacks.clear()
        BlockingThread.instances.clear()
        release = threading.Event()

        def process_message(message):
            if message == "first":
                release.wait()
            return f"reply:{message}"

        self.mock_agent.process_message.side_effect = process_message
        self.on_response.reset_mock()

        with (
            patch("threading.Thread", BlockingThread),
            patch("PySide6.QtCore.QTimer", DeferredTimer),
        ):
            self.controller.enqueue("first")
            self.controller.enqueue("second")
            self.assertEqual(self.controller._message_queue, ["second"])
            release.set()
            BlockingThread.instances[-1].join()
            DeferredTimer.callbacks.pop(0)()
            BlockingThread.instances[-1].join()
            DeferredTimer.callbacks.pop(0)()
            DeferredTimer.callbacks.pop(0)()
            if DeferredTimer.callbacks:
                DeferredTimer.callbacks.pop(0)()

        self.assertEqual(
            self.on_response.call_args_list,
            [call("reply:first"), call("reply:second")],
        )
        self.assertFalse(self.controller._processing_message)




class TestChatControllerQtEventLoop(unittest.TestCase):
    def _application(self):
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QCoreApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    def test_success_callbacks_run_on_qt_main_thread(self):
        from PySide6.QtCore import QEventLoop, QTimer

        app = self._application()
        worker_thread = {}
        response_thread = {}

        mock_agent = Mock()

        def process_message(message):
            worker_thread["thread"] = threading.current_thread()
            return "reply"

        mock_agent.process_message.side_effect = process_message

        finished = {"value": False}

        def on_response(response):
            response_thread["thread"] = threading.current_thread()
            self.assertEqual(response, "reply")

        loop = QEventLoop()

        def on_finished():
            finished["value"] = True
            loop.quit()

        controller = ChatController(
            agent_service_factory=lambda: mock_agent,
            on_response=on_response,
            on_error=Mock(),
            on_processing_finished=on_finished,
        )

        controller.enqueue("hello")
        QTimer.singleShot(1000, loop.quit)
        loop.exec()

        self.assertTrue(finished["value"])
        self.assertIsNotNone(worker_thread.get("thread"))
        self.assertIsNot(worker_thread["thread"], threading.main_thread())
        self.assertIs(response_thread["thread"], threading.main_thread())
        self.assertFalse(controller._processing_message)

    def test_error_callback_runs_on_qt_main_thread(self):
        from PySide6.QtCore import QEventLoop, QTimer

        app = self._application()
        worker_thread = {}
        error_thread = {}

        mock_agent = Mock()

        def process_message(message):
            worker_thread["thread"] = threading.current_thread()
            raise RuntimeError("boom")

        mock_agent.process_message.side_effect = process_message

        finished = {"value": False}

        def on_error(exc):
            error_thread["thread"] = threading.current_thread()
            self.assertIsInstance(exc, RuntimeError)

        loop = QEventLoop()

        def on_finished():
            finished["value"] = True
            loop.quit()

        controller = ChatController(
            agent_service_factory=lambda: mock_agent,
            on_response=Mock(),
            on_error=on_error,
            on_processing_finished=on_finished,
        )

        controller.enqueue("hello")
        QTimer.singleShot(1000, loop.quit)
        loop.exec()

        self.assertTrue(finished["value"])
        self.assertIsNot(worker_thread["thread"], threading.main_thread())
        self.assertIs(error_thread["thread"], threading.main_thread())
        self.assertFalse(controller._processing_message)


if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()

