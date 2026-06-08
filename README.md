# Summary Generator

A FastAPI service that generates summaries for large documents, with user authentication and authorization.

## Features

- User registration with email validation, username uniqueness check, and bcrypt password hashing
- JWT-based login with 24-hour token expiry
- Role-based access control (default role: `user`)
- Async PostgreSQL database via SQLAlchemy 2.0 and asyncpg
- Database migrations managed with Alembic
- Auto-generated API documentation via Swagger UI at `/docs`

## Project Structure

```
src/summary_generator/
├── main.py                  # FastAPI app, router registration, uvicorn entrypoint
├── config.py                # All settings and environment variables
├── database.py              # Async SQLAlchemy engine, session, Base class
├── dependencies.py          # Shared FastAPI dependencies: DbDependency, UserDependency, get_current_user
├── models/
│   ├── __init__.py          # Exports all models
│   └── user.py              # User table definition
├── schemas/
│   ├── __init__.py
│   └── auth.py              # Pydantic models: CreateUserRequest, UserResponse, Token
├── services/
│   ├── __init__.py
│   └── auth.py              # Business logic: hash_password, verify_password, create_access_token, authenticate_user
└── routers/
    ├── __init__.py
    └── auth.py              # Auth HTTP routes: /register, /login

alembic/                     # Database migration scripts
tests/
├── conftest.py              # Shared fixtures: test DB setup, table cleanup, HTTP client
├── test_main.py             # Tests for core app endpoints
└── test_auth.py             # Tests for auth endpoints
pyproject.toml               # Project config and dependencies
.env                         # Environment variables (not committed)
start.sh                     # Start the server
stop.sh                      # Stop the server
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
| `python-multipart` | Form data support for login |
| `email-validator` | Email format validation |

## Environment Variables

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/<dbname>
SECRET_KEY=your-secret-key-here
```

`SECRET_KEY` is optional — a default is used if not set, but always set it in production.

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
