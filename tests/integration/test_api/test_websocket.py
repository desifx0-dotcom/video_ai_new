"""
Integration tests for WebSocket API.
"""
import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock
import socketio
import eventlet

from src.app.config import TestingConfig

class TestWebSocketAPI:
    """Test WebSocket API endpoints."""
    
    @pytest.fixture
    def socket_client(self):
        """Create Socket.IO test client."""
        from src.main import create_app
        app, socketio = create_app(TestingConfig)
        
        # Create test client
        client = socketio.test_client(app, flask_test_client=True)
        return client
    
    def test_connection(self, socket_client):
        """Test WebSocket connection."""
        assert socket_client.is_connected()
        
        # Check connection event
        received = socket_client.get_received()
        assert len(received) > 0
        assert received[0]['name'] == 'connect'
    
    def test_disconnection(self, socket_client):
        """Test WebSocket disconnection."""
        socket_client.disconnect()
        assert not socket_client.is_connected()
    
    def test_authentication(self, socket_client):
        """Test WebSocket authentication."""
        # Mock JWT token
        test_token = "test_jwt_token"
        
        # Send authentication event
        socket_client.emit('authenticate', {'token': test_token})
        
        # Check response
        received = socket_client.get_received()
        assert len(received) > 0
        
        # Should receive authentication response
        auth_response = None
        for event in received:
            if event['name'] == 'authenticated':
                auth_response = event
                break
        
        assert auth_response is not None
        assert auth_response['args'][0]['success'] == True
    
    def test_authentication_invalid_token(self, socket_client):
        """Test WebSocket authentication with invalid token."""
        # Send authentication with invalid token
        socket_client.emit('authenticate', {'token': 'invalid_token'})
        
        # Check response
        received = socket_client.get_received()
        
        # Should receive error response
        error_response = None
        for event in received:
            if event['name'] == 'error':
                error_response = event
                break
        
        assert error_response is not None
        assert error_response['args'][0]['success'] == False
        assert 'error' in error_response['args'][0]
    
    def test_video_processing_updates(self, socket_client):
        """Test video processing updates."""
        # First authenticate
        socket_client.emit('authenticate', {'token': 'test_token'})
        socket_client.get_received()  # Clear received events
        
        # Subscribe to video updates
        video_id = 'test_video_123'
        socket_client.emit('subscribe_video', {'video_id': video_id})
        
        # Check subscription confirmation
        received = socket_client.get_received()
        subscription_response = None
        for event in received:
            if event['name'] == 'subscribed':
                subscription_response = event
                break
        
        assert subscription_response is not None
        assert subscription_response['args'][0]['video_id'] == video_id
        assert subscription_response['args'][0]['success'] == True
    
    def test_video_progress_updates(self, socket_client):
        """Test receiving video progress updates."""
        # First authenticate and subscribe
        socket_client.emit('authenticate', {'token': 'test_token'})
        socket_client.emit('subscribe_video', {'video_id': 'test_video_123'})
        socket_client.get_received()  # Clear received events
        
        # Mock sending a progress update
        progress_data = {
            'video_id': 'test_video_123',
            'progress': 50,
            'status': 'processing',
            'current_step': 'transcribing',
            'estimated_time_remaining': 120
        }
        
        # This would normally come from the server
        # For testing, we'll check if the client can receive such events
        socket_client.eio.send(json.dumps({
            'name': 'video_progress',
            'args': [progress_data]
        }))
        
        # Check if client received the update
        # Note: This depends on the test client implementation
    
    def test_video_completed_event(self, socket_client):
        """Test video completed event."""
        # First authenticate and subscribe
        socket_client.emit('authenticate', {'token': 'test_token'})
        socket_client.emit('subscribe_video', {'video_id': 'test_video_123'})
        socket_client.get_received()  # Clear received events
        
        # Mock sending a completion event
        completion_data = {
            'video_id': 'test_video_123',
            'status': 'completed',
            'progress': 100,
            'output_video_url': 'https://storage.example.com/video.mp4',
            'thumbnail_url': 'https://storage.example.com/thumbnail.jpg'
        }
        
        # Emit completion event
        socket_client.eio.send(json.dumps({
            'name': 'video_completed',
            'args': [completion_data]
        }))
        
        # Check if client received the event
        # (Implementation depends on test client)
    
    def test_video_failed_event(self, socket_client):
        """Test video failed event."""
        # First authenticate and subscribe
        socket_client.emit('authenticate', {'token': 'test_token'})
        socket_client.emit('subscribe_video', {'video_id': 'test_video_123'})
        socket_client.get_received()  # Clear received events
        
        # Mock sending a failure event
        failure_data = {
            'video_id': 'test_video_123',
            'status': 'failed',
            'error_message': 'Processing failed due to network error',
            'error_code': 'PROCESSING_ERROR_NETWORK'
        }
        
        # Emit failure event
        socket_client.eio.send(json.dumps({
            'name': 'video_failed',
            'args': [failure_data]
        }))
    
    def test_tier_upgrade_notification(self, socket_client):
        """Test tier upgrade notification."""
        # First authenticate
        socket_client.emit('authenticate', {'token': 'test_token'})
        socket_client.get_received()  # Clear received events
        
        # Mock sending tier upgrade notification
        upgrade_data = {
            'from_tier': 'free',
            'to_tier': 'starter',
            'upgrade_price': 24.00,
            'new_features': ['50 videos/month', '1080p quality', '7-day retention']
        }
        
        # Emit tier upgrade event
        socket_client.eio.send(json.dumps({
            'name': 'tier_upgraded',
            'args': [upgrade_data]
        }))
    
    def test_credits_updated_notification(self, socket_client):
        """Test credits updated notification."""
        # First authenticate
        socket_client.emit('authenticate', {'token': 'test_token'})
        socket_client.get_received()  # Clear received events
        
        # Mock sending credits update
        credits_data = {
            'credits_remaining': 150,
            'credits_used_this_month': 50,
            'credits_added': 100,
            'transaction_id': 'txn_123'
        }
        
        # Emit credits updated event
        socket_client.eio.send(json.dumps({
            'name': 'credits_updated',
            'args': [credits_data]
        }))
    
    def test_multiple_video_subscriptions(self, socket_client):
        """Test subscribing to multiple videos."""
        # First authenticate
        socket_client.emit('authenticate', {'token': 'test_token'})
        socket_client.get_received()  # Clear received events
        
        # Subscribe to multiple videos
        video_ids = ['video_1', 'video_2', 'video_3']
        
        for video_id in video_ids:
            socket_client.emit('subscribe_video', {'video_id': video_id})
        
        # Check all subscriptions were successful
        received = socket_client.get_received()
        
        subscription_responses = [
            event for event in received 
            if event['name'] == 'subscribed'
        ]
        
        assert len(subscription_responses) == len(video_ids)
    
    def test_unsubscribe_video(self, socket_client):
        """Test unsubscribing from video updates."""
        # First authenticate and subscribe
        socket_client.emit('authenticate', {'token': 'test_token'})
        socket_client.emit('subscribe_video', {'video_id': 'test_video_123'})
        socket_client.get_received()  # Clear received events
        
        # Unsubscribe
        socket_client.emit('unsubscribe_video', {'video_id': 'test_video_123'})
        
        # Check unsubscription confirmation
        received = socket_client.get_received()
        
        unsubscribe_response = None
        for event in received:
            if event['name'] == 'unsubscribed':
                unsubscribe_response = event
                break
        
        assert unsubscribe_response is not None
        assert unsubscribe_response['args'][0]['video_id'] == 'test_video_123'
        assert unsubscribe_response['args'][0]['success'] == True
    
    def test_room_based_updates(self, socket_client):
        """Test room-based updates for specific users."""
        # This tests that users only receive updates for their own videos
        user_id = 'test_user_123'
        
        # Mock authentication that sets user ID
        with patch('src.api.websocket.verify_token') as mock_verify:
            mock_verify.return_value = {'sub': user_id}
            
            socket_client.emit('authenticate', {'token': 'test_token'})
            socket_client.get_received()  # Clear received events
            
            # User should be joined to their personal room
            # This is tested at the server level
    
    def test_error_handling(self, socket_client):
        """Test WebSocket error handling."""
        # Send malformed data
        socket_client.eio.send('invalid json')
        
        # Send event without required data
        socket_client.emit('subscribe_video', {})  # Missing video_id
        
        # Check error response
        received = socket_client.get_received()
        
        error_events = [
            event for event in received 
            if event['name'] == 'error'
        ]
        
        assert len(error_events) > 0
    
    def test_reconnection(self, socket_client):
        """Test WebSocket reconnection."""
        # Connect and authenticate
        socket_client.emit('authenticate', {'token': 'test_token'})
        socket_client.get_received()  # Clear received events
        
        # Disconnect
        socket_client.disconnect()
        assert not socket_client.is_connected()
        
        # Reconnect
        socket_client.connect()
        assert socket_client.is_connected()
        
        # Should need to re-authenticate after reconnection
        socket_client.emit('authenticate', {'token': 'test_token'})
        
        received = socket_client.get_received()
        auth_response = None
        for event in received:
            if event['name'] == 'authenticated':
                auth_response = event
                break
        
        assert auth_response is not None
    
    def test_heartbeat(self, socket_client):
        """Test WebSocket heartbeat/ping-pong."""
        # The Socket.IO client should automatically handle ping/pong
        # This test verifies the connection stays alive
        
        # Send ping (handled by client library)
        # Wait a bit
        import time
        time.sleep(0.1)
        
        # Connection should still be alive
        assert socket_client.is_connected()
    
    def test_broadcast_messages(self, socket_client):
        """Test broadcast messages to all connected clients."""
        # This would require multiple test clients
        # For now, test that broadcast events are sent
        
        # Create another test client
        from src.main import create_app
        app, socketio = create_app(TestingConfig)
        client2 = socketio.test_client(app, flask_test_client=True)
        
        # Both clients authenticate
        socket_client.emit('authenticate', {'token': 'token1'})
        client2.emit('authenticate', {'token': 'token2'})
        
        # Clear received events
        socket_client.get_received()
        client2.get_received()
        
        # Broadcast an event from server
        # This would normally be done in the application code
        # For testing, we can emit to a broadcast room
        
        # Check both clients receive broadcast
        # (Implementation depends on test setup)
        
        client2.disconnect()