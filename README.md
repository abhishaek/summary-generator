# Summary Generator

A FastAPI service that generates summaries for large documents, with user authentication and authorization.

## Features

- User registration with email, username, and hashed password
- JWT-based authentication with 24-hour token expiry
- Role-based access control (user/admin)
- Async PostgreSQL database via SQLAlchemy and asyncpg
- Database migrations managed with Alembic
- Auto-generated API documentation via Swagger UI

## Project Structure

```
Summary-generator/
├── src/
│   └── summary_generator/
│       ├── __init__.py
│       ├── main.py           # FastAPI app, router registration, uvicorn entrypoint
│       ├── database.py       # Async SQLAlchemy engine and session, Base class
│       ├── models.py         # User table definition
│       └── routers/
│           ├── __init__.py
│           └── auth.py       # Register, login, JWT token logic, get_current_user
├── alembic/                  # Migration scripts
├── tests/                    # Test suite
├── pyproject.toml            # Project config and dependencies
├── .env                      # Environment variables (not committed)
├── start.sh                  # Start the server
└── stop.sh                   # Stop the server
```

## Requirements

- Python >= 3.11
- PostgreSQL

Key dependencies:
- `fastapi>=0.111`
- `uvicorn[standard]>=0.30`
- `sqlalchemy>=2.0`
- `asyncpg>=0.29`
- `alembic>=1.13`
- `python-jose[cryptography]>=3.3`
- `bcrypt>=4.0`
- `python-dotenv>=1.0`
- `python-multipart>=0.0.9`

## Installation

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Run database migrations
alembic upgrade head
```

## Environment Variables

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/<dbname>
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

API docs available at `http://localhost:8000/docs`

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

```bash
pytest
```

## Database Migrations

```bash
# After changing models.py
alembic revision --autogenerate -m "describe what changed"
alembic upgrade head
```
