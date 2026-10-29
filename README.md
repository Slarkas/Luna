# Luna

Luna is a modular Windows desktop AI assistant built with PySide6. It combines a chat interface, local or cloud OpenAI-compatible LLM endpoints, persistent local storage, sidebar navigation, optional speech-to-text, text-to-speech, and AI tool calling.

## Features

- **PySide6 desktop chat interface** with a main window, chat view, sidebar, settings page, and status bar.
- **Local and cloud OpenAI-compatible LLM endpoints** configured through environment variables.
- **Whisper-based speech-to-text (STT)** using the Whisper `base` model and `sounddevice`.
- **Chatterbox Turbo text-to-speech (TTS)** with lazy model loading.
- **Speaker toggle and voice playback** for enabling or disabling spoken replies.
- **AI function/tool calling** through OpenAI-compatible tool calls.
- **Live weather information** using the Open-Meteo API.
- **Extensible tool registry** for registering additional AI tools.
- **ChatController** for background queue processing of chat messages.
- **TTSController** for voice synthesis and playback.
- **SettingsController** for settings and username management.
- **SQLite conversation history and username persistence**.
- **Saved chats** with opening, multi-selection, and deletion.
- **Opt-in history recording**, disabled by default for each session.
- **GUI settings, sidebar navigation, and API connection status**.

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
`http://localhost:1235/v1`. Override via environment variables:

- `LUNA_PROVIDER_ENDPOINT` — API base URL (default `http://localhost:1235/v1`).
- `LUNA_MODEL` — model name to request.
- `LUNA_API_KEY` — optional API key for authenticated endpoints.

Both local and remote OpenAI-compatible providers are supported. Luna does not configure or pay for any cloud service automatically; provide the endpoint, model, and key yourself when using a hosted provider.

## Requirements

- Python 3.10 or newer
- PySide6 (includes Qt Multimedia for audio playback)

Optional voice dependencies:

- Speech-to-text:
  - `numpy`
  - `sounddevice`
  - `openai-whisper`
- Text-to-speech:
  - `chatterbox-tts` (and its `torch`/`torchaudio` dependencies)

SQLite is included with Python.

## Tests

Run the test suite with:

```bash
python -m pytest tests -q
```

## Project Structure

- `run_luna.py` — Application entry point
- `app/` — Core application code
  - `config.py` — Configuration defaults and environment overrides
  - `main.py` — Startup logic and application bootstrap
  - `agent/` — Agent service and OpenAI-compatible provider client
  - `tools/` — Extensible tool registry and weather tool
  - `storage/` — SQLite database, conversation history, and settings
  - `ui/` — PySide6 GUI, chat views, sidebar, settings, and controllers
    - `chat_controller.py` — Background chat queue processing
    - `tts_controller.py` — Voice synthesis and playback
    - `settings_controller.py` — Settings management
  - `tts_service.py` — Chatterbox Turbo TTS service
  - `voice_to_txt.py` — Whisper-based speech-to-text helper
- `tests/` — Unit and UI tests

## Data Storage

Luna stores its SQLite database at:

```text
app/storage/luna.db
```

This keeps conversation history and settings, including the persisted username, in the project's storage folder.

## Additional AI Tools

The tool registry currently provides live weather lookup. Additional AI tools are planned and can be added by registering new tools with the registry in `app/tools/`.

## Notes

- Conversation history recording is opt-in and starts disabled for each new session.
- Voice input and output require their optional dependencies to be installed.
- The API status indicator reflects successful AI replies rather than pre-pinging the endpoint.