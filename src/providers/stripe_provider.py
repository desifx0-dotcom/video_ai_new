"""
Stripe payment provider.
"""
import os
import logging
from typing import Dict, Any, Optional, List
import stripe

from core.exceptions import ExternalServiceError
from core.domain.value_objects.tier import Tier

logger = logging.getLogger(__name__)

class StripeProvider:
    """Stripe payment provider."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('STRIPE_SECRET_KEY')
        
        if not self.api_key:
            raise ExternalServiceError("Stripe", "API key not configured")
        
        stripe.api_key = self.api_key
        
        # Webhook secret for verifying webhook signatures
        self.webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    def create_customer(
        self,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a Stripe customer.
        
        Args:
            email: Customer email
            name: Customer name
            metadata: Additional metadata
        
        Returns:
            Customer object
        """
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata=metadata or {}
            )
            
            return customer.to_dict()
            
        except Exception as e:
            logger.error(f"Stripe customer creation failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a checkout session for subscription.
        
        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
            metadata: Additional metadata
        
        Returns:
            Checkout session
        """
        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata or {}
            )
            
            return session.to_dict()
            
        except Exception as e:
            logger.error(f"Stripe checkout session creation failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def create_one_time_payment(
        self,
        amount: int,
        currency: str,
        customer_id: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a one-time payment.
        
        Args:
            amount: Amount in smallest currency unit (e.g., cents)
            currency: Currency code
            customer_id: Stripe customer ID
            description: Payment description
            metadata: Additional metadata
        
        Returns:
            Payment intent
        """
        try:
            payment_intent = stripe.PaymentIntent.create(
                amount=amount,
                currency=currency,
                customer=customer_id,
                description=description,
                metadata=metadata or {},
                automatic_payment_methods={
                    'enabled': True,
                }
            )
            
            return payment_intent.to_dict()
            
        except Exception as e:
            logger.error(f"Stripe payment intent creation failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        trial_days: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a subscription.
        
        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID
            trial_days: Optional trial period in days
            metadata: Additional metadata
        
        Returns:
            Subscription object
        """
        try:
            subscription_data = {
                'customer': customer_id,
                'items': [{'price': price_id}],
                'metadata': metadata or {}
            }
            
            if trial_days:
                subscription_data['trial_period_days'] = trial_days
            
            subscription = stripe.Subscription.create(**subscription_data)
            
            return subscription.to_dict()
            
        except Exception as e:
            logger.error(f"Stripe subscription creation failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def cancel_subscription(
        self,
        subscription_id: str,
        cancel_at_period_end: bool = True
    ) -> Dict[str, Any]:
        """
        Cancel a subscription.
        
        Args:
            subscription_id: Stripe subscription ID
            cancel_at_period_end: Whether to cancel at period end
        
        Returns:
            Updated subscription
        """
        try:
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=cancel_at_period_end
            )
            
            return subscription.to_dict()
            
        except Exception as e:
            logger.error(f"Stripe subscription cancellation failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def update_subscription(
        self,
        subscription_id: str,
        new_price_id: str,
        prorate: bool = True
    ) -> Dict[str, Any]:
        """
        Update subscription to new price.
        
        Args:
            subscription_id: Stripe subscription ID
            new_price_id: New price ID
            prorate: Whether to prorate the change
        
        Returns:
            Updated subscription
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            
            updated = stripe.Subscription.modify(
                subscription_id,
                items=[{
                    'id': subscription['items']['data'][0].id,
                    'price': new_price_id,
                }],
                proration_behavior='create_prorations' if prorate else 'none'
            )
            
            return updated.to_dict()
            
        except Exception as e:
            logger.error(f"Stripe subscription update failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """Get customer by ID."""
        try:
            customer = stripe.Customer.retrieve(customer_id)
            return customer.to_dict()
        except Exception as e:
            logger.error(f"Stripe customer retrieval failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get subscription by ID."""
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return subscription.to_dict()
        except Exception as e:
            logger.error(f"Stripe subscription retrieval failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Get invoice by ID."""
        try:
            invoice = stripe.Invoice.retrieve(invoice_id)
            return invoice.to_dict()
        except Exception as e:
            logger.error(f"Stripe invoice retrieval failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def get_price_for_tier(self, tier: Tier, yearly: bool = False) -> Optional[str]:
        """
        Get Stripe price ID for tier.
        
        Args:
            tier: Subscription tier
            yearly: Whether to get yearly price
        
        Returns:
            Stripe price ID
        """
        # Map tier to price IDs (configured in Stripe dashboard)
        price_map = {
            'starter': {
                'monthly': os.getenv('STRIPE_PRICE_STARTER_MONTHLY'),
                'yearly': os.getenv('STRIPE_PRICE_STARTER_YEARLY')
            },
            'pro': {
                'monthly': os.getenv('STRIPE_PRICE_PRO_MONTHLY'),
                'yearly': os.getenv('STRIPE_PRICE_PRO_YEARLY')
            },
            'plus': {
                'monthly': os.getenv('STRIPE_PRICE_PLUS_MONTHLY'),
                'yearly': os.getenv('STRIPE_PRICE_PLUS_YEARLY')
            },
            'enterprise': {
                'monthly': os.getenv('STRIPE_PRICE_ENTERPRISE_MONTHLY'),
                'yearly': os.getenv('STRIPE_PRICE_ENTERPRISE_YEARLY')
            }
        }
        
        tier_prices = price_map.get(tier.value)
        if not tier_prices:
            return None
        
        return tier_prices['yearly' if yearly else 'monthly']
    
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> Optional[Dict[str, Any]]:
        """
        Verify Stripe webhook signature.
        
        Args:
            payload: Raw request payload
            signature: Stripe signature header
        
        Returns:
            Event object if valid, None otherwise
        """
        if not self.webhook_secret:
            logger.error("Stripe webhook secret not configured")
            return None
        
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
            return event.to_dict()
        except Exception as e:
            logger.error(f"Stripe webhook signature verification failed: {str(e)}")
            return None
    
    def create_billing_portal_session(
        self,
        customer_id: str,
        return_url: str
    ) -> Dict[str, Any]:
        """
        Create billing portal session.
        
        Args:
            customer_id: Stripe customer ID
            return_url: URL to return after portal session
        
        Returns:
            Billing portal session
        """
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url
            )
            
            return session.to_dict()
            
        except Exception as e:
            logger.error(f"Stripe billing portal session creation failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def get_customer_payment_methods(self, customer_id: str) -> List[Dict[str, Any]]:
        """Get customer's payment methods."""
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type="card"
            )
            
            return [pm.to_dict() for pm in payment_methods.data]
            
        except Exception as e:
            logger.error(f"Stripe payment methods retrieval failed: {str(e)}")
            raise ExternalServiceError("Stripe", str(e))
    
    def test_connection(self) -> bool:
        """Test Stripe API connection."""
        try:
            # Try to list customers (limit 1)
            stripe.Customer.list(limit=1)
            return True
        except Exception as e:
            logger.error(f"Stripe connection test failed: {str(e)}")
            return False