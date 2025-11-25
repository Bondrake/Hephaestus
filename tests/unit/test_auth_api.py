
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.auth.auth_api import router, get_db_manager
from src.core.user_models import User, AuthToken
from fastapi import FastAPI

# Setup app for testing
app = FastAPI()
app.include_router(router)

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_db_session():
    mock_session = MagicMock()
    return mock_session

@pytest.fixture
def mock_db_manager(mock_db_session):
    with patch("src.auth.auth_api.get_db_manager") as mock_get_manager:
        mock_manager = MagicMock()
        mock_manager.get_session.return_value.__enter__.return_value = mock_db_session
        mock_get_manager.return_value = mock_manager
        yield mock_manager

@pytest.fixture
def mock_verify_access_token():
    with patch("src.auth.verify_access_token") as mock:
        yield mock

@pytest.fixture
def mock_hash_token():
    with patch("src.auth.hash_token") as mock:
        mock.return_value = "hashed_token"
        yield mock

def test_get_current_user_success(client, mock_db_session, mock_db_manager, mock_verify_access_token):
    # Mock token verification
    user_id = "test-user-id"
    mock_verify_access_token.return_value = {"sub": user_id}
    
    # Mock database user
    mock_user = MagicMock(spec=User)
    mock_user.id = user_id
    mock_user.email = "test@example.com"
    mock_user.username = "testuser"
    mock_user.first_name = "Test"
    mock_user.last_name = "User"
    mock_user.created_at = datetime.utcnow()
    mock_user.email_verified = True
    mock_user.status = "active"
    
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user
    
    # Make request
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer valid-token"})
    
    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == "test@example.com"
    assert data["username"] == "testuser"

def test_get_current_user_invalid_token(client, mock_verify_access_token):
    # Mock invalid token
    mock_verify_access_token.return_value = None
    
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid-token"})
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication credentials"

def test_get_current_user_not_found(client, mock_db_session, mock_db_manager, mock_verify_access_token):
    # Mock valid token but user not in DB
    mock_verify_access_token.return_value = {"sub": "non-existent-id"}
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer valid-token"})
    
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"

def test_logout_success(client, mock_db_session, mock_db_manager, mock_hash_token, mock_verify_access_token):
    # Mock token verification for logging context
    mock_verify_access_token.return_value = {"sub": "user_id"}
    
    # Mock stored token
    mock_token = MagicMock(spec=AuthToken)
    mock_token.user_id = "user_id"
    mock_token.revoked_at = None
    
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_token
    
    # Make request
    response = client.post(
        "/api/auth/logout", 
        headers={"Authorization": "Bearer valid-token"},
        json={"refresh_token": "valid-refresh-token"}
    )
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"
    
    # Verify token was revoked
    assert mock_token.revoked_at is not None
    mock_db_session.commit.assert_called_once()

def test_logout_token_not_found(client, mock_db_session, mock_db_manager, mock_hash_token, mock_verify_access_token):
    # Mock token not found
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    
    # Make request
    response = client.post(
        "/api/auth/logout", 
        headers={"Authorization": "Bearer valid-token"},
        json={"refresh_token": "invalid-refresh-token"}
    )
    
    # Verify response (should still succeed to not leak info)
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"
    
    # Verify no commit happened (nothing to revoke)
    mock_db_session.commit.assert_not_called()
