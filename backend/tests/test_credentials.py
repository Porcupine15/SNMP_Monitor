from cryptography.fernet import Fernet

from app.credentials import decrypt, encrypt


def test_credentials_are_encrypted_when_key_is_configured(monkeypatch):
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    encrypted = encrypt("private-community")
    assert encrypted.startswith("enc:")
    assert decrypt(encrypted) == "private-community"
