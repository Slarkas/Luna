# Luna

A modular Windows desktop AI assistant — minimal foundation.

## Purpose

Luna is designed as a structured, extensible base for building intelligent agents on Windows. The project separates configuration from startup logic and provides testable defaults out of the box.

## Starting Luna

```bash
python run_luna.py
```

## Running Tests

```bash
python -m unittest discover -v
```

## Project Structure

- `run_luna.py` — Application entry point
- `app/` — Core application code
  - `config.py` — Configuration defaults
  - `main.py` — Startup logic and main function
- `tests/` — Unit tests