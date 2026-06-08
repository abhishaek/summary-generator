from jose import jwt
from summary_generator.config import SECRET_KEY, ALGORITHM
from summary_generator.services.auth import hash_password, verify_password, create_access_token


def test_hash_password_returns_hashed_string():
    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert hashed.startswith("$2b$")


def test_hash_password_produces_different_hash_each_time():
    hash1 = hash_password("mypassword")
    hash2 = hash_password("mypassword")
    assert hash1 != hash2


def test_verify_password_returns_true_for_correct_password():
    hashed = hash_password("correctpass")
    assert verify_password("correctpass", hashed) is True


def test_verify_password_returns_false_for_wrong_password():
    hashed = hash_password("correctpass")
    assert verify_password("wrongpass", hashed) is False


def test_create_access_token_returns_decodable_jwt():
    token = create_access_token(username="abhishek", user_id=1, role="user")
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "abhishek"
    assert payload["id"] == 1
    assert payload["role"] == "user"
    assert "exp" in payload


def test_create_access_token_includes_all_fields():
    token = create_access_token(username="admin", user_id=99, role="admin")
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "admin"
    assert payload["id"] == 99
    assert payload["role"] == "admin"
