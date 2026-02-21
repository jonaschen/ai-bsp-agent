# src/auth/login.py

def login(username, password):
    """
    Simulates a basic login for the Android BSP Consultant console.
    """
    if username == "admin" and password == "password123":
        return {"status": "success", "user": username}
    return {"status": "fail", "message": "Invalid credentials"}
