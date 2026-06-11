# Summary Generator

A FastAPI service that generates summaries for large documents using Google Gemini, with user authentication.

## Features

- User registration with email validation, username uniqueness check, and bcrypt password hashing
- JWT-based login with 24-hour token expiry
- Role stored per user (default: `user`); role is included in the JWT
- Summarize plain text sent via JSON payload
- Summarize uploaded files: `.txt`, `.html`, `.pdf` (max 5 MB)
- Two summary formats: `bullet` (5 bullet points, default) or `paragraph`
- HTML files are stripped of `<script>` and `<style>` tags before summarization
- PDF files are extracted page-by-page before summarization
- Large documents are automatically split into chunks and summarized using a map-reduce strategy when token count exceeds 100,000 tokens
- All summary endpoints require a valid JWT token
- Async PostgreSQL database via SQLAlchemy 2.0 and asyncpg
- Database migrations managed with Alembic
- Auto-generated API docs at `/docs`

## Project Structure

```
src/summary_generator/
├── main.py                        # FastAPI app, router registration, uvicorn entrypoint
├── config.py                      # All settings and environment variables
├── database.py                    # Async SQLAlchemy engine, session, Base class
├── dependencies.py                # JWT validation dependency: get_current_user, UserDependency
├── models/
│   ├── __init__.py                # Exports all models
│   └── user.py                    # User table: id, email, username, hashed_password, role, is_active, created_at
├── schemas/
│   ├── __init__.py
│   ├── auth.py                    # Pydantic models: CreateUserRequest, UserResponse, Token
│   └── summary.py                 # Pydantic models: SummaryRequest, SummaryResponse
├── routers/
│   ├── __init__.py                # Central router aggregator — registers all routers into api_router
│   ├── auth.py                    # Auth routes: POST /auth/register, POST /auth/login
│   └── summary.py                 # Summary routes: POST /summary/text, POST /summary/file
├── services/
│   ├── __init__.py
│   ├── auth.py                    # hash_password, verify_password, create_access_token, authenticate_user
│   ├── chunker.py                 # Token counting, text splitting for large documents
│   └── gemini_service.py          # Gemini API calls: single-pass and map-reduce summarization
├── parsers/
│   ├── __init__.py                # Factory: extract_text(file_bytes, mime_type) -> str
│   ├── text.py                    # Decode and normalize plain text bytes
│   ├── html.py                    # Strip HTML tags, extract visible text via BeautifulSoup
│   └── pdf.py                     # Extract text page-by-page via pypdf
└── shared/
    ├── __init__.py
    ├── gemini_client.py           # Single shared google-genai Client instance
    └── parserHelper.py            # _normalize(): whitespace normalization used by all parsers

alembic/                           # Database migration scripts
tests/
├── conftest.py                    # Test DB setup, table cleanup, async HTTP client fixture
├── test_main.py                   # Tests for GET /health
├── test_auth.py                   # Tests for /auth/register and /auth/login endpoints
└── test_services.py               # Unit tests for hash_password, verify_password, create_access_token
pyproject.toml                     # Project config and dependencies
.env                               # Environment variables (not committed)
start.sh                           # Start the server
stop.sh                            # Stop the server
```

## Requirements

- Python >= 3.11
- PostgreSQL

Key dependencies:

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn[standard]` | ASGI server |
| `sqlalchemy>=2.0` | Async ORM |
| `asyncpg` | Async PostgreSQL driver |
| `alembic` | Database migrations |
| `bcrypt` | Password hashing |
| `python-jose[cryptography]` | JWT token creation and verification |
| `python-dotenv` | Loads `.env` file |
| `python-multipart` | Form data support for login and file uploads |
| `email-validator` | Email format validation |
| `google-genai` | Google Gemini API client |
| `pypdf` | PDF text extraction |
| `beautifulsoup4` | HTML text extraction |

## Environment Variables

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/<dbname>
GOOGLE_GEMINI_API_KEY=your-gemini-api-key-here
SECRET_KEY=your-secret-key-here
GEMINI_MODEL=gemini-2.5-flash
```

- `SECRET_KEY` is optional — a default is used if not set, but always set it in production.
- `GEMINI_MODEL` is optional — defaults to `gemini-2.5-flash` if not set.
- `GOOGLE_GEMINI_API_KEY` is required for summarization. Get a free key at [aistudio.google.com](https://aistudio.google.com).

## Installation

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Create PostgreSQL database and user
psql postgres -c "CREATE DATABASE summary_db;"
psql postgres -c "CREATE USER summary_user WITH PASSWORD 'yourpassword';"
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE summary_db TO summary_user;"
psql postgres -c "ALTER DATABASE summary_db OWNER TO summary_user;"

# Run migrations
alembic upgrade head
```

## Running the App

```bash
./start.sh
```

Or directly:

```bash
uvicorn summary_generator.main:app --reload --port 8000
```

Stop the server:

```bash
./stop.sh
```

API docs: `http://localhost:8000/docs`

## API Endpoints

| Method | Path | Auth Required | Description |
|---|---|---|---|
| GET | `/health` | No | Returns service health status |
| POST | `/auth/register` | No | Create a new user account |
| POST | `/auth/login` | No | Login and receive a JWT token |
| POST | `/summary/text` | Yes | Summarize plain text from JSON payload |
| POST | `/summary/file` | Yes | Summarize an uploaded .txt, .html, or .pdf file |

### POST /auth/register

Request body:
```json
{
  "email": "user@example.com",
  "username": "string",
  "password": "string",
  "role": "user"
}
```

Response `201`:
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "string",
  "role": "user",
  "is_active": true
}
```

### POST /auth/login

Form data: `username`, `password`

Response `200`:
```json
{
  "access_token": "<jwt_token>",
  "token_type": "bearer"
}
```

### POST /summary/text

Header: `Authorization: Bearer <token>`

Request body:
```json
{
  "text": "long text to summarize...",
  "summary_format": "bullet"
}
```

`summary_format` is optional — defaults to `bullet`. Accepted values: `bullet`, `paragraph`.

Response `200`:
```json
{
  "summary": [
    "• First key point...",
    "• Second key point...",
    "• Third key point...",
    "• Fourth key point...",
    "• Fifth key point..."
  ],
  "source_type": "text"
}
```

### POST /summary/file

Header: `Authorization: Bearer <token>`

Multipart form data:
- `file`: the file to upload (`.txt`, `.html`, or `.pdf`, max 5 MB)
- `summary_format`: optional, `bullet` (default) or `paragraph`

Response `200`: same shape as `/summary/text` with `source_type: "file"`.

Error responses:
- `400` — empty text or no readable content found in file
- `413` — file exceeds 5 MB
- `415` — unsupported file type

## Running Tests

Tests run against a separate `summary_test_db` database. Create it first:

```bash
psql postgres -c "CREATE DATABASE summary_test_db;"
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE summary_test_db TO summary_user;"
psql postgres -c "ALTER DATABASE summary_test_db OWNER TO summary_user;"
```

Then run:

```bash
pytest -v
```

## Database Migrations

```bash
# After changing any file in models/
alembic revision --autogenerate -m "describe what changed"
alembic upgrade head
```
