"""
Integration tests for authentication API.
"""
import pytest
import json
from unittest.mock import patch
import jwt

from src.app.config import TestingConfig

class TestAuthAPI:
    """Test authentication API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.main import create_app
        app, _ = create_app(TestingConfig)
        with app.test_client() as client:
            yield client
    
    def test_register_success(self, client):
        """Test successful user registration."""
        data = {
            "email": "test@example.com",
            "password": "StrongPassword123!",
            "full_name": "Test User"
        }
        
        response = client.post('/api/v1/auth/register', 
                             json=data,
                             content_type='application/json')
        
        assert response.status_code == 201
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
        assert 'user_id' in response_data
        assert 'access_token' in response_data
        assert 'refresh_token' in response_data
    
    def test_register_invalid_email(self, client):
        """Test registration with invalid email."""
        data = {
            "email": "invalid-email",
            "password": "StrongPassword123!"
        }
        
        response = client.post('/api/v1/auth/register', json=data)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'VALIDATION_ERROR_EMAIL'
    
    def test_register_weak_password(self, client):
        """Test registration with weak password."""
        data = {
            "email": "test@example.com",
            "password": "weak"
        }
        
        response = client.post('/api/v1/auth/register', json=data)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'VALIDATION_ERROR_PASSWORD'
    
    def test_login_success(self, client):
        """Test successful login."""
        # First register a user
        register_data = {
            "email": "login@example.com",
            "password": "StrongPassword123!"
        }
        
        client.post('/api/v1/auth/register', json=register_data)
        
        # Then login
        login_data = {
            "email": "login@example.com",
            "password": "StrongPassword123!"
        }
        
        response = client.post('/api/v1/auth/login', json=login_data)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
        assert 'access_token' in response_data
        assert 'refresh_token' in response_data
    
    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        data = {
            "email": "nonexistent@example.com",
            "password": "WrongPassword123!"
        }
        
        response = client.post('/api/v1/auth/login', json=data)
        
        assert response.status_code == 401
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'UNAUTHORIZED'
    
    def test_refresh_token(self, client):
        """Test token refresh."""
        # First register and login
        register_data = {
            "email": "refresh@example.com",
            "password": "StrongPassword123!"
        }
        
        register_response = client.post('/api/v1/auth/register', json=register_data)
        register_data = json.loads(register_response.data)
        refresh_token = register_data['refresh_token']
        
        # Refresh token
        refresh_data = {
            "refresh_token": refresh_token
        }
        
        response = client.post('/api/v1/auth/refresh', json=refresh_data)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
        assert 'access_token' in response_data
        assert 'refresh_token' in response_data
    
    def test_refresh_invalid_token(self, client):
        """Test refresh with invalid token."""
        refresh_data = {
            "refresh_token": "invalid.token.here"
        }
        
        response = client.post('/api/v1/auth/refresh', json=refresh_data)
        
        assert response.status_code == 401
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'UNAUTHORIZED'
    
    def test_logout(self, client):
        """Test logout."""
        # First register and login
        register_data = {
            "email": "logout@example.com",
            "password": "StrongPassword123!"
        }
        
        register_response = client.post('/api/v1/auth/register', json=register_data)
        register_data = json.loads(register_response.data)
        access_token = register_data['access_token']
        
        # Logout
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        response = client.post('/api/v1/auth/logout', headers=headers)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
    
    def test_logout_without_token(self, client):
        """Test logout without token."""
        response = client.post('/api/v1/auth/logout')
        
        assert response.status_code == 401
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'UNAUTHORIZED'
    
    def test_forgot_password(self, client):
        """Test forgot password endpoint."""
        # First register a user
        register_data = {
            "email": "forgot@example.com",
            "password": "StrongPassword123!"
        }
        
        client.post('/api/v1/auth/register', json=register_data)
        
        # Request password reset
        reset_data = {
            "email": "forgot@example.com"
        }
        
        with patch('src.services.email_service.EmailService.send_password_reset') as mock_send:
            mock_send.return_value = True
            
            response = client.post('/api/v1/auth/forgot-password', json=reset_data)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['message'] == 'Password reset email sent'
            
            # Check email was sent
            mock_send.assert_called_once()
    
    def test_forgot_password_nonexistent_user(self, client):
        """Test forgot password for nonexistent user."""
        reset_data = {
            "email": "nonexistent@example.com"
        }
        
        response = client.post('/api/v1/auth/forgot-password', json=reset_data)
        
        # Should still return success to prevent email enumeration
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
    
    def test_reset_password(self, client):
        """Test password reset."""
        # First register a user
        register_data = {
            "email": "reset@example.com",
            "password": "OldPassword123!"
        }
        
        client.post('/api/v1/auth/register', json=register_data)
        
        # Generate reset token
        from src.core.security import SecurityUtils
        reset_token = SecurityUtils.generate_jwt_token(
            {"email": "reset@example.com", "type": "password_reset"},
            TestingConfig.SECRET_KEY
        )
        
        # Reset password
        reset_data = {
            "token": reset_token,
            "new_password": "NewPassword123!"
        }
        
        response = client.post('/api/v1/auth/reset-password', json=reset_data)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
        
        # Verify new password works
        login_data = {
            "email": "reset@example.com",
            "password": "NewPassword123!"
        }
        
        login_response = client.post('/api/v1/auth/login', json=login_data)
        assert login_response.status_code == 200
    
    def test_reset_password_invalid_token(self, client):
        """Test password reset with invalid token."""
        reset_data = {
            "token": "invalid.token.here",
            "new_password": "NewPassword123!"
        }
        
        response = client.post('/api/v1/auth/reset-password', json=reset_data)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'VALIDATION_ERROR_TOKEN'
    
    def test_verify_email(self, client):
        """Test email verification."""
        # First register a user
        register_data = {
            "email": "verify@example.com",
            "password": "StrongPassword123!"
        }
        
        client.post('/api/v1/auth/register', json=register_data)
        
        # Generate verification token
        from src.core.security import SecurityUtils
        verify_token = SecurityUtils.generate_jwt_token(
            {"email": "verify@example.com", "type": "email_verify"},
            TestingConfig.SECRET_KEY
        )
        
        # Verify email
        response = client.get(f'/api/v1/auth/verify-email?token={verify_token}')
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
        assert response_data['message'] == 'Email verified successfully'
    
    def test_protected_endpoint_with_token(self, client):
        """Test accessing protected endpoint with valid token."""
        # First register and login
        register_data = {
            "email": "protected@example.com",
            "password": "StrongPassword123!"
        }
        
        register_response = client.post('/api/v1/auth/register', json=register_data)
        register_data = json.loads(register_response.data)
        access_token = register_data['access_token']
        
        # Access protected endpoint
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        response = client.get('/api/v1/users/me', headers=headers)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
        assert response_data['user']['email'] == 'protected@example.com'
    
    def test_protected_endpoint_without_token(self, client):
        """Test accessing protected endpoint without token."""
        response = client.get('/api/v1/users/me')
        
        assert response.status_code == 401
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'UNAUTHORIZED'
    
    def test_protected_endpoint_expired_token(self, client):
        """Test accessing protected endpoint with expired token."""
        # Generate expired token
        import time
        expired_payload = {
            "sub": "test_user",
            "exp": time.time() - 3600  # Expired 1 hour ago
        }
        
        expired_token = jwt.encode(
            expired_payload,
            TestingConfig.SECRET_KEY,
            algorithm='HS256'
        )
        
        headers = {
            'Authorization': f'Bearer {expired_token}'
        }
        
        response = client.get('/api/v1/users/me', headers=headers)
        
        assert response.status_code == 401
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'UNAUTHORIZED'
    
    def test_rate_limiting(self, client):
        """Test rate limiting on auth endpoints."""
        # Try to register multiple times quickly
        data = {
            "email": "ratelimit@example.com",
            "password": "StrongPassword123!"
        }
        
        responses = []
        for i in range(15):  # More than free tier limit
            response = client.post('/api/v1/auth/register', 
                                 json=data,
                                 content_type='application/json')
            responses.append(response.status_code)
        
        # Some requests should be rate limited
        assert 429 in responses
    
    def test_cors_headers(self, client):
        """Test CORS headers are present."""
        response = client.options('/api/v1/auth/login')
        
        assert response.status_code == 200
        assert 'Access-Control-Allow-Origin' in response.headers
        assert 'Access-Control-Allow-Methods' in response.headers
        assert 'Access-Control-Allow-Headers' in response.headers
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get('/health')
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['status'] == 'healthy'
        assert response_data['service'] == 'video-ai-studio'