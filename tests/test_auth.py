async def test_register_returns_201_on_valid_input(client):
    response = await client.post("/auth/v1/register", json={
        "email": "testuser@example.com",
        "username": "testuser",
        "password": "securepass123",
        "role": "user"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert data["username"] == "testuser"
    assert "hashed_password" not in data


async def test_register_returns_400_on_duplicate_email(client):
    payload = {
        "email": "duplicate@example.com",
        "username": "uniqueuser",
        "password": "pass123"
    }
    await client.post("/auth/v1/register", json=payload)
    response = await client.post("/auth/v1/register", json={**payload, "username": "anotheruser"})
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


async def test_register_returns_400_on_duplicate_username(client):
    payload = {
        "email": "unique@example.com",
        "username": "dupeuser",
        "password": "pass123"
    }
    await client.post("/auth/v1/register", json=payload)
    response = await client.post("/auth/v1/register", json={**payload, "email": "another@example.com"})
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


async def test_register_returns_422_on_invalid_email(client):
    response = await client.post("/auth/v1/register", json={
        "email": "notanemail",
        "username": "someuser",
        "password": "pass123"
    })
    assert response.status_code == 422


async def test_register_returns_422_when_fields_missing(client):
    response = await client.post("/auth/v1/register", json={"email": "test@example.com"})
    assert response.status_code == 422


async def test_login_returns_200_and_token_on_valid_credentials(client):
    await client.post("/auth/v1/register", json={
        "email": "loginuser@example.com",
        "username": "loginuser",
        "password": "mypassword"
    })
    response = await client.post("/auth/v1/login", data={
        "username": "loginuser",
        "password": "mypassword"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_returns_401_on_wrong_password(client):
    await client.post("/auth/v1/register", json={
        "email": "wrongpass@example.com",
        "username": "wrongpassuser",
        "password": "correctpass"
    })
    response = await client.post("/auth/v1/login", data={
        "username": "wrongpassuser",
        "password": "wrongpass"
    })
    assert response.status_code == 401


async def test_login_returns_401_on_nonexistent_user(client):
    response = await client.post("/auth/v1/login", data={
        "username": "doesnotexist",
        "password": "anypassword"
    })
    assert response.status_code == 401
