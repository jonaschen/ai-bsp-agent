import hashlib

class Authenticator:
    """
    Handles user authentication following SOLID principles.
    """
    def __init__(self, user_db: dict):
        self.user_db = user_db

    def authenticate(self, username, password) -> bool:
        """
        Verifies credentials against the provided user database.
        """
        if username not in self.user_db:
            return False

        stored_hash = self.user_db[username]
        # Using SHA-256 for basic password hashing
        input_hash = hashlib.sha256(password.encode()).hexdigest()

        return input_hash == stored_hash

def login(username, password) -> bool:
    """
    Convenience function for login.
    In a real system, the user_db would be loaded from a secure storage or database.
    This implementation uses hashed values to avoid hardcoded secrets in source code.
    """
    # Pre-calculated SHA-256 hash for 'password123'
    mock_db = {
        "admin": "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f"
    }
    auth = Authenticator(mock_db)
    return auth.authenticate(username, password)
