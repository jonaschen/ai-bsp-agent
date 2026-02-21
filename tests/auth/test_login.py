import hashlib
from auth.login import login, Authenticator

def test_login_success():
    assert login("admin", "password123") is True

def test_login_failure():
    assert login("admin", "wrong_password") is False
    assert login("wrong_user", "password123") is False

def test_authenticator_class():
    # Test with a custom database
    custom_db = {
        "user1": hashlib.sha256(b"pass1").hexdigest()
    }
    auth = Authenticator(custom_db)
    assert auth.authenticate("user1", "pass1") is True
    assert auth.authenticate("user1", "wrong") is False
    assert auth.authenticate("unknown", "pass1") is False
