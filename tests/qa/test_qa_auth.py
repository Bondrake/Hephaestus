import pytest
import os
# Set test DB before any other imports to ensure consistency
os.environ["HEPHAESTUS_TEST_DB"] = "test_qa.db"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import time

from src.mcp.server import app
print(f"[DEBUG TEST] App ID: {id(app)}")
from src.core.database import Base, get_db
from src.core.user_models import User, AuthToken, LoginAttempt
from src.auth.auth_utils import hash_password, verify_password

# Setup test database
if os.path.exists("test_qa.db"):
    os.remove("test_qa.db")
if os.path.exists("hephaestus.db"):
    os.remove("hephaestus.db")

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_qa.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# We can still use overrides for safety, but env var ensures fallback works
app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module")
def test_db():
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables
    Base.metadata.drop_all(bind=engine)

from unittest.mock import patch, AsyncMock

@pytest.fixture(scope="module")
def client(test_db):
    # Patch server_state.initialize to avoid starting unnecessary components (LLM, etc.)
    with patch("src.mcp.server.server_state.initialize", new_callable=AsyncMock) as mock_init:
        with TestClient(app) as c:
            yield c

class TestScenario1_Auth:
    """Scenario 1: Authentication & Session Management"""
    
    user_email = "qa_user@example.com"
    user_password = "secure_password_123"
    access_token = None
    refresh_token = None
    
    def test_1_1_registration_and_login(self, client):
        """
        Scenario 1.1: User Registration & Login
        - Register a new user (via direct DB insertion as API might not have public register)
        - Login with valid credentials
        - Verify tokens
        - Verify identity via /api/auth/me
        """
        # 1. Register (Simulate registration by creating user in DB)
        db = TestingSessionLocal()
        
        # Debug: Check if tables exist
        from sqlalchemy import text
        result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
        print(f"[DEBUG TEST] Tables in DB: {result.fetchall()}")

        # Debug: Try to select
        try:
            print("[DEBUG TEST] Selecting from login_attempts...")
            db.execute(text("SELECT * FROM login_attempts"))
            print("[DEBUG TEST] Select successful")
        except Exception as e:
            print(f"[DEBUG TEST] Select failed: {e}")

        # Clear previous data to avoid lockout
        try:
            db.execute(text('DELETE FROM "login_attempts"'))
            print("[DEBUG TEST] Delete login_attempts successful")
        except Exception as e:
            print(f"[DEBUG TEST] Delete login_attempts failed: {e}")
            
        try:
            db.execute(text("DELETE FROM users"))
            print("[DEBUG TEST] Delete users successful")
        except Exception as e:
            print(f"[DEBUG TEST] Delete users failed: {e}")
            
        db.commit()
        
        user = User(
            id="qa-user-id",
            email=self.user_email,
            username="qa_user",
            password_hash=hash_password(self.user_password),
            first_name="QA",
            last_name="Tester",
            status="active",
            email_verified=True
        )
        db.add(user)
        db.commit()
        
        # Debug: Verify password manually
        print(f"\n[DEBUG] Password: {self.user_password}")
        print(f"[DEBUG] Hash: {user.password_hash}")
        is_valid = verify_password(self.user_password, user.password_hash)
        print(f"[DEBUG] Manual verification: {is_valid}")
        assert is_valid, "Manual password verification failed!"
        
        db.close()
        
        # 2. Login
        response = client.post(
            "/api/auth/login",
            data={"username": self.user_email, "password": self.user_password}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # 3. Verify tokens
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        
        TestScenario1_Auth.access_token = data["access_token"]
        TestScenario1_Auth.refresh_token = data["refresh_token"]
        
        # 4. Critical Check: Verify identity
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {TestScenario1_Auth.access_token}"}
        )
        assert response.status_code == 200
        user_data = response.json()
        assert user_data["email"] == self.user_email
        assert user_data["id"] == "qa-user-id"
        print("\n[PASS] Scenario 1.1: Registration & Login verified")

    def test_1_2_token_refresh(self, client):
        """
        Scenario 1.2: Token Refresh
        - Use refresh token to get new access token
        - Verify new token works
        """
        assert TestScenario1_Auth.refresh_token is not None, "Skipping: No refresh token from previous step"
        
        # 1. Refresh Token
        time.sleep(2) # Ensure iat changes
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": TestScenario1_Auth.refresh_token}
        )
        assert response.status_code == 200, f"Refresh failed: {response.text}"
        data = response.json()
        
        assert "access_token" in data
        new_access_token = data["access_token"]
        assert new_access_token != TestScenario1_Auth.access_token
        
        # 2. Verify new token works
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {new_access_token}"}
        )
        assert response.status_code == 200
        
        # Update class var for next step
        TestScenario1_Auth.access_token = new_access_token
        if "refresh_token" in data:
            TestScenario1_Auth.refresh_token = data["refresh_token"]
            
        print("\n[PASS] Scenario 1.2: Token Refresh verified")

    def test_1_3_logout(self, client):
        """
        Scenario 1.3: Logout
        - Call logout endpoint with refresh token
        - Verify refresh token is revoked (by trying to use it again)
        """
        assert TestScenario1_Auth.refresh_token is not None
        
        # 1. Logout
        response = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {TestScenario1_Auth.access_token}"},
            json={"refresh_token": TestScenario1_Auth.refresh_token}
        )
        assert response.status_code == 200
        
        # 2. Verify Refresh Token is Revoked (Try to refresh again)
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": TestScenario1_Auth.refresh_token}
        )
        # Should fail with 401 or similar because it's revoked
        assert response.status_code in [401, 403], f"Revoked token still worked! Status: {response.status_code}"
        
        print("\n[PASS] Scenario 1.3: Logout & Revocation verified")
