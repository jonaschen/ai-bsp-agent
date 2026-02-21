import pytest
from src.auth.login import login

def test_login_success():
    assert login("admin", "password123") is True

def test_login_failure():
    assert login("admin", "wrong_password") is False

def test_login_empty_credentials():
    assert login("", "") is False
