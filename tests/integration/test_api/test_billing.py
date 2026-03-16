"""
Integration tests for billing API.
"""
import pytest
import json
from unittest.mock import patch, MagicMock

from src.app.config import TestingConfig

class TestBillingAPI:
    """Test billing API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.main import create_app
        app, _ = create_app(TestingConfig)
        with app.test_client() as client:
            yield client
    
    @pytest.fixture
    def auth_headers(self, client):
        """Create authenticated user and return headers."""
        # Register and login
        register_data = {
            "email": "billing@example.com",
            "password": "StrongPassword123!"
        }
        
        response = client.post('/api/v1/auth/register', json=register_data)
        response_data = json.loads(response.data)
        access_token = response_data['access_token']
        
        return {
            'Authorization': f'Bearer {access_token}'
        }
    
    def test_get_pricing_plans(self, client):
        """Test getting pricing plans."""
        response = client.get('/api/v1/billing/plans')
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
        assert 'plans' in response_data
        
        # Check all tiers are present
        tiers = ['free', 'starter', 'pro', 'plus', 'enterprise']
        for tier in tiers:
            tier_plans = [p for p in response_data['plans'] if p['tier'] == tier]
            assert len(tier_plans) > 0
    
    def test_get_pricing_plans_with_currency(self, client):
        """Test getting pricing plans with specific currency."""
        response = client.get('/api/v1/billing/plans?currency=EUR')
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
        
        # Check currency is used
        for plan in response_data['plans']:
            if plan['price_monthly'] > 0:
                assert plan['currency'] == 'EUR'
    
    def test_create_checkout_session(self, client, auth_headers):
        """Test creating checkout session."""
        checkout_data = {
            "tier": "pro",
            "billing_cycle": "monthly",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel"
        }
        
        # Mock Stripe provider
        with patch('src.providers.stripe_provider.StripeProvider.create_checkout_session') as mock_session:
            mock_session.return_value = {
                'id': 'cs_test_123',
                'url': 'https://checkout.stripe.com/c/pay/cs_test_123'
            }
            
            response = client.post('/api/v1/billing/checkout', 
                                 json=checkout_data,
                                 headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['session_id'] == 'cs_test_123'
            assert response_data['checkout_url'] == 'https://checkout.stripe.com/c/pay/cs_test_123'
    
    def test_create_checkout_session_invalid_tier(self, client, auth_headers):
        """Test creating checkout session with invalid tier."""
        checkout_data = {
            "tier": "invalid_tier",
            "billing_cycle": "monthly"
        }
        
        response = client.post('/api/v1/billing/checkout', 
                             json=checkout_data,
                             headers=auth_headers)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'VALIDATION_ERROR_TIER'
    
    def test_create_checkout_session_invalid_billing_cycle(self, client, auth_headers):
        """Test creating checkout session with invalid billing cycle."""
        checkout_data = {
            "tier": "pro",
            "billing_cycle": "invalid_cycle"
        }
        
        response = client.post('/api/v1/billing/checkout', 
                             json=checkout_data,
                             headers=auth_headers)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'VALIDATION_ERROR_BILLING_CYCLE'
    
    def test_get_subscription_status(self, client, auth_headers):
        """Test getting subscription status."""
        # Mock billing service
        with patch('src.services.billing_service.BillingService.get_subscription') as mock_sub:
            mock_sub.return_value = {
                'id': 'sub_123',
                'tier': 'pro',
                'status': 'active',
                'current_period_end': '2024-12-31T23:59:59',
                'cancel_at_period_end': False
            }
            
            response = client.get('/api/v1/billing/subscription', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['subscription']['tier'] == 'pro'
            assert response_data['subscription']['status'] == 'active'
    
    def test_get_subscription_status_no_subscription(self, client, auth_headers):
        """Test getting subscription status when no subscription exists."""
        # Mock billing service returning None
        with patch('src.services.billing_service.BillingService.get_subscription') as mock_sub:
            mock_sub.return_value = None
            
            response = client.get('/api/v1/billing/subscription', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['subscription'] is None
    
    def test_cancel_subscription(self, client, auth_headers):
        """Test canceling subscription."""
        cancel_data = {
            "cancel_at_period_end": True
        }
        
        # Mock billing service
        with patch('src.services.billing_service.BillingService.cancel_subscription') as mock_cancel:
            mock_cancel.return_value = {
                'id': 'sub_123',
                'cancel_at_period_end': True,
                'current_period_end': '2024-12-31T23:59:59'
            }
            
            response = client.post('/api/v1/billing/subscription/cancel', 
                                 json=cancel_data,
                                 headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['subscription']['cancel_at_period_end'] == True
    
    def test_cancel_subscription_no_active_subscription(self, client, auth_headers):
        """Test canceling subscription when no active subscription exists."""
        cancel_data = {
            "cancel_at_period_end": True
        }
        
        # Mock billing service raising error
        from src.core.exceptions import ValidationError
        
        with patch('src.services.billing_service.BillingService.cancel_subscription') as mock_cancel:
            mock_cancel.side_effect = ValidationError("No active subscription found")
            
            response = client.post('/api/v1/billing/subscription/cancel', 
                                 json=cancel_data,
                                 headers=auth_headers)
            
            assert response.status_code == 400
            response_data = json.loads(response.data)
            
            assert response_data['error']['code'] == 'VALIDATION_ERROR'
    
    def test_reactivate_subscription(self, client, auth_headers):
        """Test reactivating subscription."""
        # Mock billing service
        with patch('src.services.billing_service.BillingService.reactivate_subscription') as mock_reactivate:
            mock_reactivate.return_value = {
                'id': 'sub_123',
                'cancel_at_period_end': False,
                'status': 'active'
            }
            
            response = client.post('/api/v1/billing/subscription/reactivate', 
                                 headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['subscription']['cancel_at_period_end'] == False
    
    def test_get_payment_methods(self, client, auth_headers):
        """Test getting payment methods."""
        # Mock billing service
        with patch('src.services.billing_service.BillingService.get_payment_methods') as mock_methods:
            mock_methods.return_value = [
                {
                    'id': 'pm_123',
                    'type': 'card',
                    'card': {
                        'brand': 'visa',
                        'last4': '4242',
                        'exp_month': 12,
                        'exp_year': 2025
                    },
                    'is_default': True
                }
            ]
            
            response = client.get('/api/v1/billing/payment-methods', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert 'payment_methods' in response_data
            assert len(response_data['payment_methods']) == 1
            assert response_data['payment_methods'][0]['type'] == 'card'
    
    def test_add_payment_method(self, client, auth_headers):
        """Test adding payment method."""
        payment_data = {
            "payment_method_id": "pm_test_123"
        }
        
        # Mock billing service
        with patch('src.services.billing_service.BillingService.add_payment_method') as mock_add:
            mock_add.return_value = {
                'id': 'pm_123',
                'type': 'card',
                'is_default': True
            }
            
            response = client.post('/api/v1/billing/payment-methods', 
                                 json=payment_data,
                                 headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['payment_method']['id'] == 'pm_123'
            assert response_data['payment_method']['is_default'] == True
    
    def test_set_default_payment_method(self, client, auth_headers):
        """Test setting default payment method."""
        payment_data = {
            "payment_method_id": "pm_123"
        }
        
        # Mock billing service
        with patch('src.services.billing_service.BillingService.set_default_payment_method') as mock_set:
            mock_set.return_value = True
            
            response = client.put('/api/v1/billing/payment-methods/default', 
                                json=payment_data,
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['message'] == 'Payment method set as default'
    
    def test_remove_payment_method(self, client, auth_headers):
        """Test removing payment method."""
        payment_method_id = "pm_123"
        
        # Mock billing service
        with patch('src.services.billing_service.BillingService.remove_payment_method') as mock_remove:
            mock_remove.return_value = True
            
            response = client.delete(f'/api/v1/billing/payment-methods/{payment_method_id}', 
                                   headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['message'] == 'Payment method removed'
    
    def test_get_invoices(self, client, auth_headers):
        """Test getting invoices."""
        # Mock billing service
        with patch('src.services.billing_service.BillingService.get_invoices') as mock_invoices:
            mock_invoices.return_value = [
                {
                    'id': 'in_123',
                    'number': 'INV-2024-001',
                    'amount': 79.00,
                    'currency': 'usd',
                    'status': 'paid',
                    'created': '2024-01-01T00:00:00',
                    'invoice_pdf': 'https://invoice.stripe.com/invoice_123.pdf'
                }
            ]
            
            response = client.get('/api/v1/billing/invoices', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert 'invoices' in response_data
            assert len(response_data['invoices']) == 1
            assert response_data['invoices'][0]['number'] == 'INV-2024-001'
    
    def test_get_invoice_pdf(self, client, auth_headers):
        """Test getting invoice PDF URL."""
        invoice_id = "in_123"
        
        # Mock billing service
        with patch('src.services.billing_service.BillingService.get_invoice_pdf_url') as mock_url:
            mock_url.return_value = 'https://invoice.stripe.com/invoice_123.pdf'
            
            response = client.get(f'/api/v1/billing/invoices/{invoice_id}/pdf', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['pdf_url'] == 'https://invoice.stripe.com/invoice_123.pdf'
    
    def test_get_credits_balance(self, client, auth_headers):
        """Test getting credits balance."""
        # Mock credit service
        with patch('src.services.credit_service.CreditService.get_balance') as mock_balance:
            mock_balance.return_value = {
                'credits_remaining': 150,
                'credits_used_this_month': 50,
                'credits_total': 200
            }
            
            response = client.get('/api/v1/billing/credits', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['credits']['credits_remaining'] == 150
            assert response_data['credits']['credits_used_this_month'] == 50
    
    def test_purchase_credits(self, client, auth_headers):
        """Test purchasing credits."""
        purchase_data = {
            "amount": 100,
            "currency": "usd"
        }
        
        # Mock billing service
        with patch('src.services.billing_service.BillingService.purchase_credits') as mock_purchase:
            mock_purchase.return_value = {
                'id': 'pay_123',
                'amount': 10.00,
                'credits_added': 100,
                'new_balance': 200
            }
            
            response = client.post('/api/v1/billing/credits/purchase', 
                                 json=purchase_data,
                                 headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert response_data['transaction']['credits_added'] == 100
            assert response_data['transaction']['new_balance'] == 200
    
    def test_purchase_credits_invalid_amount(self, client, auth_headers):
        """Test purchasing credits with invalid amount."""
        purchase_data = {
            "amount": 0,
            "currency": "usd"
        }
        
        response = client.post('/api/v1/billing/credits/purchase', 
                             json=purchase_data,
                             headers=auth_headers)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        
        assert response_data['error']['code'] == 'VALIDATION_ERROR_AMOUNT'
    
    def test_get_credit_packages(self, client):
        """Test getting available credit packages."""
        response = client.get('/api/v1/billing/credits/packages')
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        
        assert response_data['success'] == True
        assert 'packages' in response_data
        
        # Check packages have required fields
        for package in response_data['packages']:
            assert 'id' in package
            assert 'credits' in package
            assert 'price' in package
            assert 'currency' in package
    
    def test_stripe_webhook(self, client):
        """Test Stripe webhook endpoint."""
        webhook_data = {
            "id": "evt_test_123",
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "id": "in_test_123",
                    "customer": "cus_test_123",
                    "amount_paid": 7900,
                    "currency": "usd"
                }
            }
        }
        
        webhook_secret = "whsec_test"
        
        # Mock Stripe signature verification
        with patch('src.api.v1.routers.billing.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = webhook_data
            
            # Mock billing service
            with patch('src.services.billing_service.BillingService.handle_webhook') as mock_handle:
                mock_handle.return_value = True
                
                headers = {
                    'Stripe-Signature': 't=1234567890,v1=signature'
                }
                
                response = client.post('/api/v1/billing/webhook/stripe', 
                                     json=webhook_data,
                                     headers=headers)
                
                assert response.status_code == 200
                assert response.data == b'Webhook processed successfully'
    
    def test_stripe_webhook_invalid_signature(self, client):
        """Test Stripe webhook with invalid signature."""
        webhook_data = {
            "id": "evt_test_123",
            "type": "invoice.payment_succeeded"
        }
        
        # Mock signature verification failure
        with patch('src.api.v1.routers.billing.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.side_effect = Exception("Invalid signature")
            
            headers = {
                'Stripe-Signature': 't=1234567890,v1=invalid'
            }
            
            response = client.post('/api/v1/billing/webhook/stripe', 
                                 json=webhook_data,
                                 headers=headers)
            
            assert response.status_code == 400
            response_data = json.loads(response.data)
            
            assert response_data['error']['code'] == 'VALIDATION_ERROR_SIGNATURE'
    
    def test_get_usage_analytics(self, client, auth_headers):
        """Test getting usage analytics."""
        # Mock analytics service
        with patch('src.services.billing_service.BillingService.get_usage_analytics') as mock_analytics:
            mock_analytics.return_value = {
                'current_month': {
                    'videos_processed': 5,
                    'processing_time_minutes': 25,
                    'credits_used': 25,
                    'cost': 0.75
                },
                'previous_month': {
                    'videos_processed': 3,
                    'processing_time_minutes': 15,
                    'credits_used': 15,
                    'cost': 0.45
                },
                'trends': {
                    'videos_processed_change': '+66.7%',
                    'cost_change': '+66.7%'
                }
            }
            
            response = client.get('/api/v1/billing/analytics/usage', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert 'analytics' in response_data
            assert 'current_month' in response_data['analytics']
            assert 'trends' in response_data['analytics']
    
    def test_get_cost_breakdown(self, client, auth_headers):
        """Test getting cost breakdown."""
        # Mock billing service
        with patch('src.services.billing_service.BillingService.get_cost_breakdown') as mock_breakdown:
            mock_breakdown.return_value = {
                'total_cost': 1.25,
                'breakdown': {
                    'transcription': 0.50,
                    'thumbnail_generation': 0.30,
                    'style_application': 0.25,
                    'translation': 0.10,
                    'video_processing': 0.10
                },
                'savings_from_silent_videos': 0.75
            }
            
            response = client.get('/api/v1/billing/analytics/costs', 
                                headers=auth_headers)
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            
            assert response_data['success'] == True
            assert 'cost_breakdown' in response_data
            assert response_data['cost_breakdown']['total_cost'] == 1.25