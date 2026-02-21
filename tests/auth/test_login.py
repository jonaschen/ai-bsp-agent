# tests/auth/test_login.py
from src.auth.login import login

def test_login_success():
    result = login("admin", "password123")
    assert result["status"] == "success"
    assert result["user"] == "admin"

def test_login_fail():
    result = login("wrong_user", "wrong_pass")
    assert result["status"] == "fail"
    assert "message" in result
