# Luna

A modular Windows desktop AI assistant — minimal foundation.

## Purpose

Luna is designed as a structured, extensible base for building intelligent agents on Windows. The project separates configuration from startup logic and provides testable defaults out of the box.

## Starting Luna

```bash
python run_luna.py
```

## Configuration

Luna talks to an OpenAI-compatible chat-completions endpoint. By default it uses
`http://localhost:1235/v1` with the model served there. Override via environment
variables:

- `LUNA_PROVIDER_ENDPOINT` — API base URL (default `http://localhost:1235/v1`).
- `LUNA_MODEL` — model name to request.
- `LUNA_API_KEY` — optional API key for authenticated endpoints.


```bash
python -m unittest discover -v
```

## Project Structure

- `run_luna.py` — Application entry point
- `app/` — Core application code
  - `config.py` — Configuration defaults
  - `main.py` — Startup logic and main function
- `tests/` — Unit tests