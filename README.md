# Summary Generator

A FastAPI service that generates structured summaries for large documents.

## Features

- REST API built with FastAPI
- Health check endpoint
- Auto-reload during development
- Auto-generated API docs via Swagger UI

## Project Structure

```
Summary-generator/
├── src/
│   └── summary_generator/
│       ├── __init__.py
│       └── main.py          # FastAPI app and uvicorn entrypoint
├── tests/                   # Test suite
├── pyproject.toml           # Project config, dependencies, scripts
└── README.md
```

## Requirements

- Python >= 3.11
- fastapi >= 0.111
- uvicorn[standard] >= 0.30

## Installation

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Running the App

```bash
uvicorn summary_generator.main:app --reload --port 8000
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Returns service health status |
| GET | `/docs` | Swagger UI — interactive API documentation |

## Running Tests

```bash
pytest
```

## Stopping the Server

```bash
lsof -ti :8000 | xargs kill -9
```
