import jwt

from app import auth


def test_access_token_has_bound_security_claims(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", "s" * 48)
    password_version = "a" * 64
    token = auth.create_access_token({"sub": "admin", "pwd": password_version})

    payload = jwt.decode(
        token,
        auth.SECRET_KEY,
        algorithms=[auth.ALGORITHM],
        audience=auth.TOKEN_AUDIENCE,
        issuer=auth.TOKEN_ISSUER,
    )

    assert payload["sub"] == "admin"
    assert payload["pwd"] == password_version
    assert payload["iat"] < payload["exp"]
    assert payload["jti"]


def test_new_password_hashes_use_strengthened_pbkdf2_rounds():
    password_hash = auth.get_password_hash("correct horse battery staple")

    assert "$pbkdf2-sha256$600000$" in password_hash
    assert auth.verify_password("correct horse battery staple", password_hash)
