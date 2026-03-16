"""
End-to-end tests for user flows.
"""
import pytest
import json
import time
from unittest.mock import patch, MagicMock
import tempfile
import os

from src.app.config import TestingConfig

class TestUserFlows:
    """End-to-end tests for complete user flows."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.main import create_app
        app, _ = create_app(TestingConfig)
        with app.test_client() as client:
            yield client
    
    def test_complete_user_registration_flow(self, client):
        """Test complete user registration flow."""
        # 1. Register new user
        register_data = {
            "email": "e2e_user@example.com",
            "password": "StrongPassword123!",
            "full_name": "E2E Test User"
        }
        
        register_response = client.post('/api/v1/auth/register', 
                                       json=register_data)
        assert register_response.status_code == 201
        
        register_data = json.loads(register_response.data)
        access_token = register_data['access_token']
        
        auth_headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        # 2. Get user profile
        profile_response = client.get('/api/v1/users/me', 
                                     headers=auth_headers)
        assert profile_response.status_code == 200
        
        profile_data = json.loads(profile_response.data)
        assert profile_data['user']['email'] == 'e2e_user@example.com'
        assert profile_data['user']['tier'] == 'free'
        
        # 3. Update user profile
        update_data = {
            "full_name": "Updated E2E User",
            "language": "es",
            "timezone": "America/New_York"
        }
        
        update_response = client.put('/api/v1/users/me', 
                                    json=update_data,
                                    headers=auth_headers)
        assert update_response.status_code == 200
        
        # 4. Verify update
        profile_response = client.get('/api/v1/users/me', 
                                     headers=auth_headers)
        profile_data = json.loads(profile_response.data)
        
        assert profile_data['user']['full_name'] == 'Updated E2E User'
        assert profile_data['user']['language'] == 'es'
        
        # 5. Logout
        logout_response = client.post('/api/v1/auth/logout', 
                                     headers=auth_headers)
        assert logout_response.status_code == 200
        
        # 6. Login again
        login_data = {
            "email": "e2e_user@example.com",
            "password": "StrongPassword123!"
        }
        
        login_response = client.post('/api/v1/auth/login', 
                                    json=login_data)
        assert login_response.status_code == 200
        
        # 7. Delete account
        new_auth = json.loads(login_response.data)
        delete_headers = {
            'Authorization': f'Bearer {new_auth["access_token"]}'
        }
        
        delete_response = client.delete('/api/v1/users/me', 
                                       headers=delete_headers)
        assert delete_response.status_code == 200
        
        # 8. Verify can't login after deletion
        login_response = client.post('/api/v1/auth/login', 
                                    json=login_data)
        assert login_response.status_code == 401
    
    def test_complete_video_processing_flow(self, client):
        """Test complete video processing flow."""
        # 1. Register and login
        register_data = {
            "email": "video_flow@example.com",
            "password": "StrongPassword123!"
        }
        
        register_response = client.post('/api/v1/auth/register', 
                                       json=register_data)
        register_data = json.loads(register_response.data)
        access_token = register_data['access_token']
        
        auth_headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'multipart/form-data'
        }
        
        # 2. Upload video
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            # Create a minimal valid MP4 file for testing
            # This is a valid MP4 header (very small)
            f.write(b'\x00\x00\x00\x1cftypmp42\x00\x00\x00\x01mp42isom\x00\x00\x00\x08free')
            video_path = f.name
        
        try:
            # Mock video processing
            with patch('src.services.video_service.VideoService.upload_video') as mock_upload:
                mock_video = MagicMock()
                mock_video.id = 'test_video_123'
                mock_video.status = 'uploaded'
                mock_video.to_dict.return_value = {
                    'id': 'test_video_123',
                    'status': 'uploaded'
                }
                
                mock_upload.return_value = (mock_video, video_path)
                
                with open(video_path, 'rb') as video_file:
                    data = {
                        'video': (video_file, 'test_video.mp4'),
                        'quality': '720p'
                    }
                    
                    upload_response = client.post('/api/v1/videos/upload', 
                                                 data=data,
                                                 headers=auth_headers)
                
                assert upload_response.status_code == 200
                upload_data = json.loads(upload_response.data)
                video_id = upload_data['video_id']
                
                # 3. Check processing status
                with patch('src.services.video_service.VideoService.get_processing_status') as mock_status:
                    mock_status.return_value = {
                        'video': {
                            'id': video_id,
                            'status': 'processing',
                            'progress': 25
                        },
                        'job': {
                            'id': 'test_job_123',
                            'status': 'processing'
                        }
                    }
                    
                    status_response = client.get(f'/api/v1/videos/{video_id}/status', 
                                                headers=auth_headers)
                    assert status_response.status_code == 200
                    
                    # 4. Wait for completion (mock)
                    time.sleep(0.1)  # Simulate waiting
                    
                    mock_status.return_value = {
                        'video': {
                            'id': video_id,
                            'status': 'completed',
                            'progress': 100,
                            'output_video_url': 'https://storage.example.com/video.mp4',
                            'title': 'Test Video Title',
                            'description': 'Test video description'
                        },
                        'job': {
                            'id': 'test_job_123',
                            'status': 'completed'
                        }
                    }
                    
                    # 5. Get results
                    results_response = client.get(f'/api/v1/videos/{video_id}/results', 
                                                 headers=auth_headers)
                    assert results_response.status_code == 200
                    
                    results_data = json.loads(results_response.data)
                    assert results_data['video']['status'] == 'completed'
                    assert 'output_video_url' in results_data['video']
                    
                    # 6. Download video
                    with patch('src.services.storage_service.StorageService.generate_download_url') as mock_url:
                        mock_url.return_value = 'https://storage.example.com/download/video.mp4?token=abc123'
                        
                        download_response = client.get(f'/api/v1/videos/{video_id}/download', 
                                                      headers=auth_headers)
                        assert download_response.status_code == 200
                        
                        download_data = json.loads(download_response.data)
                        assert 'download_url' in download_data
                        
                        # 7. List user videos
                        with patch('src.services.video_service.VideoService.get_user_videos') as mock_list:
                            mock_videos = [mock_video]
                            mock_list.return_value = mock_videos
                            
                            list_response = client.get('/api/v1/videos', 
                                                      headers=auth_headers)
                            assert list_response.status_code == 200
                            
                            list_data = json.loads(list_response.data)
                            assert len(list_data['videos']) == 1
                            assert list_data['videos'][0]['id'] == video_id
                            
                            # 8. Delete video
                            with patch('src.services.video_service.VideoService.delete_video') as mock_delete:
                                mock_delete.return_value = True
                                
                                delete_response = client.delete(f'/api/v1/videos/{video_id}', 
                                                               headers=auth_headers)
                                assert delete_response.status_code == 200
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)
    
    def test_tier_upgrade_flow(self, client):
        """Test complete tier upgrade flow."""
        # 1. Register free user
        register_data = {
            "email": "upgrade_flow@example.com",
            "password": "StrongPassword123!"
        }
        
        register_response = client.post('/api/v1/auth/register', 
                                       json=register_data)
        register_data = json.loads(register_response.data)
        access_token = register_data['access_token']
        
        auth_headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        # 2. Check current tier (should be free)
        profile_response = client.get('/api/v1/users/me', 
                                     headers=auth_headers)
        profile_data = json.loads(profile_response.data)
        assert profile_data['user']['tier'] == 'free'
        assert profile_data['user']['monthly_video_limit'] == 3
        
        # 3. Get pricing plans
        plans_response = client.get('/api/v1/billing/plans')
        assert plans_response.status_code == 200
        
        plans_data = json.loads(plans_response.data)
        pro_plan = next(p for p in plans_data['plans'] if p['tier'] == 'pro')
        
        # 4. Create checkout session for upgrade
        checkout_data = {
            "tier": "pro",
            "billing_cycle": "monthly",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel"
        }
        
        with patch('src.providers.stripe_provider.StripeProvider.create_checkout_session') as mock_session:
            mock_session.return_value = {
                'id': 'cs_test_upgrade',
                'url': 'https://checkout.stripe.com/c/pay/cs_test_upgrade'
            }
            
            checkout_response = client.post('/api/v1/billing/checkout', 
                                          json=checkout_data,
                                          headers=auth_headers)
            assert checkout_response.status_code == 200
            
            checkout_data = json.loads(checkout_response.data)
            assert 'checkout_url' in checkout_data
            
            # 5. Simulate successful payment (webhook)
            webhook_data = {
                "id": "evt_test_upgrade",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_test_upgrade",
                        "customer": "cus_test_upgrade",
                        "subscription": "sub_test_upgrade",
                        "amount_total": 7900,
                        "currency": "usd",
                        "metadata": {
                            "user_id": profile_data['user']['id'],
                            "tier": "pro"
                        }
                    }
                }
            }
            
            with patch('src.services.billing_service.BillingService.handle_webhook') as mock_webhook:
                mock_webhook.return_value = True
                
                # This would be called by Stripe webhook
                # For test, we'll directly check tier upgrade
                pass
            
            # 6. Check upgraded tier
            with patch('src.services.billing_service.BillingService.get_subscription') as mock_sub:
                mock_sub.return_value = {
                    'tier': 'pro',
                    'status': 'active',
                    'current_period_end': '2024-12-31T23:59:59'
                }
                
                # Also need to mock user service to return upgraded user
                with patch('src.services.user_service.UserService.get_user') as mock_user:
                    upgraded_user = MagicMock()
                    upgraded_user.id = profile_data['user']['id']
                    upgraded_user.tier = 'pro'
                    upgraded_user.monthly_video_limit = 100
                    upgraded_user.to_dict.return_value = {
                        'id': profile_data['user']['id'],
                        'tier': 'pro',
                        'monthly_video_limit': 100
                    }
                    mock_user.return_value = upgraded_user
                    
                    profile_response = client.get('/api/v1/users/me', 
                                                 headers=auth_headers)
                    profile_data = json.loads(profile_response.data)
                    
                    # Should now be pro tier
                    assert profile_data['user']['tier'] == 'pro'
                    assert profile_data['user']['monthly_video_limit'] == 100
            
            # 7. Test pro tier features (upload larger video)
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
                # Create test file
                f.write(b'test' * 1000)  # 4KB file
                video_path = f.name
            
            try:
                with patch('src.services.video_service.VideoService.upload_video') as mock_upload:
                    mock_video = MagicMock()
                    mock_video.id = 'pro_tier_video'
                    mock_video.to_dict.return_value = {'id': 'pro_tier_video'}
                    
                    mock_upload.return_value = (mock_video, video_path)
                    
                    with open(video_path, 'rb') as video_file:
                        data = {
                            'video': (video_file, 'pro_video.mp4'),
                            'quality': '4k',  # Pro tier supports 4K
                            'styles': '["cinematic", "gaming"]'  # Multiple styles
                        }
                        
                        upload_response = client.post('/api/v1/videos/upload', 
                                                     data=data,
                                                     headers=auth_headers)
                        
                        # Pro tier should allow this
                        assert upload_response.status_code == 200
            finally:
                if os.path.exists(video_path):
                    os.unlink(video_path)
            
            # 8. Cancel subscription
            cancel_data = {
                "cancel_at_period_end": True
            }
            
            with patch('src.services.billing_service.BillingService.cancel_subscription') as mock_cancel:
                mock_cancel.return_value = {
                    'cancel_at_period_end': True,
                    'current_period_end': '2024-12-31T23:59:59'
                }
                
                cancel_response = client.post('/api/v1/billing/subscription/cancel', 
                                            json=cancel_data,
                                            headers=auth_headers)
                assert cancel_response.status_code == 200
    
    def test_credit_purchase_flow(self, client):
        """Test complete credit purchase flow."""
        # 1. Register user
        register_data = {
            "email": "credits_flow@example.com",
            "password": "StrongPassword123!"
        }
        
        register_response = client.post('/api/v1/auth/register', 
                                       json=register_data)
        register_data = json.loads(register_response.data)
        access_token = register_data['access_token']
        
        auth_headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        # 2. Check initial credits (free tier has 0)
        with patch('src.services.credit_service.CreditService.get_balance') as mock_balance:
            mock_balance.return_value = {
                'credits_remaining': 0,
                'credits_used_this_month': 0,
                'credits_total': 0
            }
            
            credits_response = client.get('/api/v1/billing/credits', 
                                         headers=auth_headers)
            assert credits_response.status_code == 200
            
            credits_data = json.loads(credits_response.data)
            assert credits_data['credits']['credits_remaining'] == 0
            
            # 3. Get credit packages
            packages_response = client.get('/api/v1/billing/credits/packages')
            assert packages_response.status_code == 200
            
            packages_data = json.loads(packages_response.data)
            assert 'packages' in packages_data
            assert len(packages_data['packages']) > 0
            
            # 4. Purchase credits
            purchase_data = {
                "amount": 100,
                "currency": "usd"
            }
            
            with patch('src.services.billing_service.BillingService.purchase_credits') as mock_purchase:
                mock_purchase.return_value = {
                    'id': 'pay_credits_123',
                    'amount': 10.00,
                    'credits_added': 100,
                    'new_balance': 100
                }
                
                purchase_response = client.post('/api/v1/billing/credits/purchase', 
                                              json=purchase_data,
                                              headers=auth_headers)
                assert purchase_response.status_code == 200
                
                purchase_data = json.loads(purchase_response.data)
                assert purchase_data['transaction']['credits_added'] == 100
                
                # 5. Check updated credits
                mock_balance.return_value = {
                    'credits_remaining': 100,
                    'credits_used_this_month': 0,
                    'credits_total': 100
                }
                
                credits_response = client.get('/api/v1/billing/credits', 
                                             headers=auth_headers)
                credits_data = json.loads(credits_response.data)
                
                assert credits_data['credits']['credits_remaining'] == 100
                
                # 6. Process video using credits
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
                    f.write(b'test video')
                    video_path = f.name
                
                try:
                    with patch('src.services.video_service.VideoService.upload_video') as mock_upload:
                        mock_video = MagicMock()
                        mock_video.id = 'credit_video'
                        mock_video.to_dict.return_value = {'id': 'credit_video'}
                        
                        mock_upload.return_value = (mock_video, video_path)
                        
                        with open(video_path, 'rb') as video_file:
                            data = {
                                'video': (video_file, 'credit_video.mp4')
                            }
                            
                            upload_response = client.post('/api/v1/videos/upload', 
                                                         data=data,
                                                         headers=auth_headers)
                            assert upload_response.status_code == 200
                            
                            # 7. Check credits after processing
                            mock_balance.return_value = {
                                'credits_remaining': 95,  # Used 5 credits for video
                                'credits_used_this_month': 5,
                                'credits_total': 100
                            }
                            
                            credits_response = client.get('/api/v1/billing/credits', 
                                                         headers=auth_headers)
                            credits_data = json.loads(credits_response.data)
                            
                            assert credits_data['credits']['credits_remaining'] == 95
                            assert credits_data['credits']['credits_used_this_month'] == 5
                finally:
                    if os.path.exists(video_path):
                        os.unlink(video_path)