"""
Integration tests for Firebase provider.
"""
import pytest
import json
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime

from src.providers.firebase_provider import FirebaseProvider
from src.core.exceptions import DatabaseError

class TestFirebaseProvider:
    """Test Firebase provider."""
    
    @pytest.fixture
    def firebase_provider(self):
        """Create Firebase provider instance."""
        provider = FirebaseProvider()
        
        # Mock Firebase initialization
        provider.app = MagicMock()
        provider.db = MagicMock()
        
        return provider
    
    def test_initialization(self, firebase_provider):
        """Test Firebase provider initialization."""
        # Should initialize with mocked Firebase app
        assert firebase_provider.app is not None
        assert firebase_provider.db is not None
    
    def test_save_document(self, firebase_provider):
        """Test saving a document."""
        # Mock Firebase collection and document
        mock_collection = MagicMock()
        mock_document = MagicMock()
        
        firebase_provider.db.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_document
        
        # Test data
        collection_name = 'users'
        document_id = 'user_123'
        data = {
            'email': 'test@example.com',
            'name': 'Test User',
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Save document
        result = firebase_provider.save(collection_name, document_id, data)
        
        assert result == True
        
        # Verify Firebase was called correctly
        firebase_provider.db.collection.assert_called_with(collection_name)
        mock_collection.document.assert_called_with(document_id)
        mock_document.set.assert_called_with(data)
    
    def test_save_document_error(self, firebase_provider):
        """Test saving document with error."""
        # Mock Firebase error
        mock_collection = MagicMock()
        mock_document = MagicMock()
        mock_document.set.side_effect = Exception("Firebase error")
        
        firebase_provider.db.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_document
        
        with pytest.raises(DatabaseError):
            firebase_provider.save('users', 'user_123', {})
    
    def test_get_document(self, firebase_provider):
        """Test getting a document."""
        # Mock Firebase document with data
        mock_document = MagicMock()
        mock_document.exists = True
        
        expected_data = {
            'id': 'user_123',
            'email': 'test@example.com',
            'name': 'Test User'
        }
        mock_document.to_dict.return_value = expected_data
        
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_document
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Get document
        result = firebase_provider.get('users', 'user_123')
        
        assert result == expected_data
        
        # Verify Firebase was called correctly
        firebase_provider.db.collection.assert_called_with('users')
        mock_collection.document.assert_called_with('user_123')
    
    def test_get_nonexistent_document(self, firebase_provider):
        """Test getting a non-existent document."""
        # Mock non-existent document
        mock_document = MagicMock()
        mock_document.exists = False
        
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_document
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Get non-existent document
        result = firebase_provider.get('users', 'nonexistent')
        
        assert result is None
    
    def test_update_document(self, firebase_provider):
        """Test updating a document."""
        # Mock Firebase document
        mock_document = MagicMock()
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_document
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Update data
        update_data = {
            'name': 'Updated Name',
            'updated_at': datetime.utcnow().isoformat()
        }
        
        result = firebase_provider.update('users', 'user_123', update_data)
        
        assert result == True
        
        # Verify update was called
        mock_document.update.assert_called_with(update_data)
    
    def test_update_nonexistent_document(self, firebase_provider):
        """Test updating a non-existent document."""
        # Mock Firebase document that doesn't exist
        mock_document = MagicMock()
        mock_document.update.side_effect = Exception("Document doesn't exist")
        
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_document
        
        firebase_provider.db.collection.return_value = mock_collection
        
        with pytest.raises(DatabaseError):
            firebase_provider.update('users', 'nonexistent', {})
    
    def test_delete_document(self, firebase_provider):
        """Test deleting a document."""
        # Mock Firebase document
        mock_document = MagicMock()
        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_document
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Delete document
        result = firebase_provider.delete('users', 'user_123')
        
        assert result == True
        
        # Verify delete was called
        mock_document.delete.assert_called_once()
    
    def test_query_documents(self, firebase_provider):
        """Test querying documents."""
        # Mock Firebase query results
        mock_document1 = MagicMock()
        mock_document1.to_dict.return_value = {
            'id': 'user_1',
            'email': 'user1@example.com',
            'tier': 'free'
        }
        
        mock_document2 = MagicMock()
        mock_document2.to_dict.return_value = {
            'id': 'user_2',
            'email': 'user2@example.com',
            'tier': 'pro'
        }
        
        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_document1, mock_document2]
        
        mock_collection = MagicMock()
        mock_collection.where.return_value = mock_query
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Query documents
        results = firebase_provider.query(
            collection='users',
            filters={'tier': 'free'},
            order_by='created_at',
            descending=True,
            limit=10,
            offset=0
        )
        
        assert len(results) == 2
        assert results[0]['tier'] == 'free'
        assert results[1]['tier'] == 'pro'
        
        # Verify query was built correctly
        mock_collection.where.assert_called_with('tier', '==', 'free')
    
    def test_query_with_multiple_filters(self, firebase_provider):
        """Test querying with multiple filters."""
        mock_query = MagicMock()
        mock_query.where.return_value = mock_query  # Chainable
        mock_query.stream.return_value = []
        
        mock_collection = MagicMock()
        mock_collection.where.return_value = mock_query
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Query with multiple filters
        filters = {
            'tier': 'pro',
            'is_active': True,
            'videos_processed_this_month': {'<': 100}
        }
        
        results = firebase_provider.query('users', filters=filters)
        
        # Verify multiple where clauses were added
        assert mock_query.where.call_count >= 2
    
    def test_count_documents(self, firebase_provider):
        """Test counting documents."""
        # Mock Firebase count
        mock_query = MagicMock()
        mock_query.count.return_value = [MagicMock(return_value=42)]
        
        mock_collection = MagicMock()
        mock_collection.where.return_value = mock_query
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Count documents
        count = firebase_provider.count('users', {'tier': 'free'})
        
        assert count == 42
        
        # Verify count was called
        mock_query.count.assert_called_once()
    
    def test_batch_operations(self, firebase_provider):
        """Test batch operations."""
        # Mock Firebase batch
        mock_batch = MagicMock()
        firebase_provider.db.batch.return_value = mock_batch
        
        # Mock collections and documents
        users_collection = MagicMock()
        videos_collection = MagicMock()
        
        def get_collection(name):
            if name == 'users':
                return users_collection
            elif name == 'videos':
                return videos_collection
            return MagicMock()
        
        firebase_provider.db.collection.side_effect = get_collection
        
        # Perform batch operations
        operations = [
            {
                'type': 'save',
                'collection': 'users',
                'id': 'user_123',
                'data': {'name': 'Test User'}
            },
            {
                'type': 'update',
                'collection': 'videos',
                'id': 'video_123',
                'data': {'status': 'completed'}
            },
            {
                'type': 'delete',
                'collection': 'temp',
                'id': 'temp_123'
            }
        ]
        
        result = firebase_provider.batch(operations)
        
        assert result == True
        
        # Verify batch was committed
        mock_batch.commit.assert_called_once()
    
    def test_transaction(self, firebase_provider):
        """Test transaction."""
        # Mock Firebase transaction
        mock_transaction = MagicMock()
        
        def transaction_callback(transaction):
            # Callback should be called with transaction object
            assert transaction is not None
            return "transaction_result"
        
        firebase_provider.db.transaction.return_value = transaction_callback
        
        # Execute transaction
        result = firebase_provider.transaction(transaction_callback)
        
        assert result == "transaction_result"
        
        # Verify transaction was called
        firebase_provider.db.transaction.assert_called_once()
    
    def test_create_id(self, firebase_provider):
        """Test creating document ID."""
        # Mock Firebase ID generation
        mock_collection = MagicMock()
        mock_document = MagicMock()
        mock_document.id = 'auto_generated_id'
        
        mock_collection.document.return_value = mock_document
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Create document with auto ID
        doc_id = firebase_provider.create_id('users')
        
        assert doc_id == 'auto_generated_id'
        
        # Verify document was created
        mock_collection.document.assert_called_once()
        # Should be called without ID for auto-generation
        call_args = mock_collection.document.call_args
        assert call_args[0] == ()  # No arguments means auto-ID
    
    def test_list_collections(self, firebase_provider):
        """Test listing collections."""
        # Mock Firebase collections
        mock_collection1 = MagicMock()
        mock_collection1.id = 'users'
        
        mock_collection2 = MagicMock()
        mock_collection2.id = 'videos'
        
        mock_collection3 = MagicMock()
        mock_collection3.id = 'processing_jobs'
        
        firebase_provider.db.collections.return_value = [
            mock_collection1, mock_collection2, mock_collection3
        ]
        
        # List collections
        collections = firebase_provider.list_collections()
        
        assert len(collections) == 3
        assert 'users' in collections
        assert 'videos' in collections
        assert 'processing_jobs' in collections
    
    def test_pagination(self, firebase_provider):
        """Test pagination in queries."""
        # Mock Firebase pagination
        mock_documents = []
        for i in range(20):
            mock_doc = MagicMock()
            mock_doc.to_dict.return_value = {
                'id': f'user_{i}',
                'email': f'user{i}@example.com'
            }
            mock_documents.append(mock_doc)
        
        mock_query = MagicMock()
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.stream.return_value = mock_documents[10:20]  # Second page
        
        mock_collection = MagicMock()
        mock_collection.where.return_value = mock_query
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Query with pagination
        results = firebase_provider.query(
            collection='users',
            limit=10,
            offset=10
        )
        
        assert len(results) == 10
        
        # Verify pagination methods were called
        mock_query.limit.assert_called_with(10)
        mock_query.offset.assert_called_with(10)
    
    def test_real_time_listener(self, firebase_provider):
        """Test real-time listener."""
        # Mock Firebase real-time listener
        callback_called = False
        
        def test_callback(change_type, document_id, data):
            nonlocal callback_called
            callback_called = True
            assert change_type in ['added', 'modified', 'removed']
            assert document_id == 'user_123'
            assert data is not None
        
        mock_listener = MagicMock()
        mock_query = MagicMock()
        mock_query.on_snapshot.return_value = mock_listener
        
        mock_collection = MagicMock()
        mock_collection.where.return_value = mock_query
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Setup listener
        unsubscribe = firebase_provider.add_listener(
            collection='users',
            callback=test_callback,
            filters={'is_active': True}
        )
        
        # Simulate document change
        mock_callback = mock_query.on_snapshot.call_args[0][0]
        
        # Create mock document change
        mock_document = MagicMock()
        mock_document.id = 'user_123'
        mock_document.to_dict.return_value = {'name': 'Test User'}
        
        mock_change = MagicMock()
        mock_change.type.name = 'ADDED'
        mock_change.document = mock_document
        
        # Trigger callback
        mock_callback([mock_change], None, None)
        
        assert callback_called
        
        # Test unsubscribe
        unsubscribe()
        mock_listener.unsubscribe.assert_called_once()
    
    def test_connection_health_check(self, firebase_provider):
        """Test database connection health check."""
        # Mock successful health check
        mock_collection = MagicMock()
        mock_query = MagicMock()
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []
        
        mock_collection.where.return_value = mock_query
        
        firebase_provider.db.collection.return_value = mock_collection
        
        # Check health
        is_healthy = firebase_provider.check_health()
        
        assert is_healthy == True
        
        # Test health check failure
        mock_collection.where.side_effect = Exception("Connection failed")
        
        is_healthy = firebase_provider.check_health()
        
        assert is_healthy == False