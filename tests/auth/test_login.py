from src.auth.login import login

def test_login_success():
    assert login("admin", "password") is True

def test_login_failure():
    assert login("admin", "wrong") is False
