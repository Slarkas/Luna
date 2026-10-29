"""Chat queue orchestration extracted from LunaGUI."""

import threading

from PySide6.QtCore import QTimer


class ChatController:
    """Owns chat message queue state and processing orchestration."""

    def __init__(
        self,
        agent_service_factory,
        on_response,
        on_error=None,
        on_processing_finished=None,
    ):
        self.agent_service_factory = agent_service_factory
        self.on_response = on_response
        self.on_error = on_error
        self.on_processing_finished = on_processing_finished

        self._message_queue = []
        self._processing_message = False

    def enqueue(self, message):
        """Add a message to the FIFO queue and start processing if idle."""
        self._message_queue.append(message)
        self._ensure_processing()

    def _ensure_processing(self):
        """Start queue processing when no worker is active."""
        if self._processing_message:
            return
        if not self._message_queue:
            return
        self._processing_message = True
        self._process_next_queued()

    def _process_next_queued(self):
        """Process one queued message, then continue with the rest."""
        if not self._message_queue:
            self._processing_message = False
            if self.on_processing_finished is not None:
                self.on_processing_finished()
            return

        message = self._message_queue.pop(0)
        result = {"value": None, "error": None}

        def worker():
            try:
                service = self.agent_service_factory()
                result["value"] = service.process_message(message)
            except Exception as exc:  # noqa: BLE001
                result["error"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def poll():
            if thread.is_alive():
                from PySide6.QtCore import QTimer

                QTimer.singleShot(10, poll)
                return
            if result["error"] is not None:
                if self.on_error is not None:
                    self.on_error(result["error"])
            else:
                if self.on_response is not None:
                    self.on_response(result["value"])
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._process_next_queued)

        from PySide6.QtCore import QTimer

        QTimer.singleShot(10, poll)
