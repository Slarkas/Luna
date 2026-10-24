# Luna

Luna is a modular Windows desktop AI assistant built with PySide6. It combines a chat interface, an OpenAI-compatible AI backend, persistent local storage, sidebar navigation, and optional voice-to-text input.

## Features

- **Modular application structure** with a dedicated GUI (`app/ui`), agent service (`app/agent`), provider client, and SQLite storage (`app/storage`).
- **Local/cloud-compatible API configuration** through environment variables.
- **Chat messaging** through an OpenAI-compatible chat-completions endpoint.
- **Opt-in conversation history recording**, disabled by default.
- **Saved chats** with opening, multi-selection, and deletion.
- **Improved GUI** with sidebar navigation, background images, settings, and a main-window application icon.
- **Persistent username storage** in SQLite, with common username spellings kept in sync.
- **Voice-to-text input** using Whisper (`base` model) and `sounddevice`.
- **API connection status indicator** that reflects successful AI replies instead of pre-pinging the endpoint.
- **Automated tests** for core functionality and UI components.

## Starting Luna

From the project root:

```bash
python run_luna.py
```

You can also use:

```bash
python -m app.main
```

## Configuration

Luna talks to an OpenAI-compatible chat-completions endpoint. By default it uses
`http://localhost:1235/v1` with the model served there. Override via environment
variables:

- `LUNA_PROVIDER_ENDPOINT` — API base URL (default `http://localhost:1235/v1`).
- `LUNA_MODEL` — model name to request.
- `LUNA_API_KEY` — optional API key for authenticated endpoints.

## Requirements

- Python 3.10 or newer
- PySide6
- Optional, for voice input:
  - `numpy`
  - `sounddevice`
  - `openai-whisper`

SQLite is included with Python.

## Tests

Run the full test suite with:

```bash
python -m unittest discover -v
```

## Project Structure

- `run_luna.py` — Application entry point
- `app/` — Core application code
  - `config.py` — Configuration defaults and environment overrides
  - `main.py` — Startup logic and application bootstrap
  - `agent/` — Agent service and OpenAI-compatible provider client
  - `storage/` — SQLite database, conversation history, and settings
  - `ui/` — PySide6 GUI, chat views, sidebar, settings, and images
  - `voice_to_txt.py` — Whisper-based voice-to-text helper
- `tests/` — Unit and UI tests

## Data Storage

Luna stores its SQLite database at:

```text
app/storage/luna.db
```

This keeps conversation history and settings, including the persisted username, with the project's storage folder.

## Notes

- Conversation history recording is opt-in and starts disabled for each new session.
- Voice input requires the optional audio/Whisper dependencies to be installed.
- The API status indicator becomes ready after a successful AI reply, or on launch if the configured endpoint is already connected.