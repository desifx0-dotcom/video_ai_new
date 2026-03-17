"""
Firebase database provider with PostgreSQL abstraction.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import Query

from core.exceptions import DatabaseError, ConfigurationError
from core.constants import DatabaseProvider

logger = logging.getLogger(__name__)


class FirebaseProvider:
    """Firebase database provider."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseProvider, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize Firebase connection."""
        try:
            # Check if Firebase app is already initialized
            if not firebase_admin._apps:
                # Initialize with credentials
                cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")

                if cred_path and os.path.exists(cred_path):
                    # Use service account credentials
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                else:
                    # Use application default credentials (for production environments like GCP)
                    firebase_admin.initialize_app()

            # Get Firestore client
            self._db = firestore.client()

            logger.info("Firebase Firestore initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}")
            raise ConfigurationError(f"Failed to initialize Firebase: {str(e)}")

    def save(self, collection: str, document_id: str, data: Dict[str, Any]) -> bool:
        """
        Save document to Firestore.

        Args:
            collection: Collection name
            document_id: Document ID
            data: Document data

        Returns:
            True if successful
        """
        try:
            doc_ref = self._db.collection(collection).document(document_id)
            doc_ref.set(data, merge=True)
            return True

        except Exception as e:
            logger.error(
                f"Failed to save document {collection}/{document_id}: {str(e)}"
            )
            raise DatabaseError(f"Failed to save document: {str(e)}")

    def get(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get document from Firestore.

        Args:
            collection: Collection name
            document_id: Document ID

        Returns:
            Document data or None if not found
        """
        try:
            doc_ref = self._db.collection(collection).document(document_id)
            doc = doc_ref.get()

            if doc.exists:
                data = doc.to_dict()
                data["id"] = doc.id

                # 🔥 FIX: Convert Firestore timestamps to datetime objects
                for key, value in data.items():
                    if hasattr(
                        value, "timestamp"
                    ):  # Check if it's a Firestore timestamp
                        # Convert to Python datetime
                        data[key] = datetime.fromtimestamp(value.timestamp())

                return data
            else:
                return None

        except Exception as e:
            logger.error(f"Failed to get document {collection}/{document_id}: {str(e)}")
            raise DatabaseError(f"Failed to get document: {str(e)}")

    def query(
        self,
        collection: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        descending: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query documents from Firestore.

        Args:
            collection: Collection name
            filters: Dictionary of field filters
            order_by: Field to order by
            descending: Order descending
            limit: Maximum number of documents
            offset: Number of documents to skip

        Returns:
            List of documents
        """
        try:
            if not self._db:
                logger.error("Firestore client not initialized")
                return []

            query = self._db.collection(collection)

            # Apply filters
            if filters:
                for field, value in filters.items():
                    try:
                        if isinstance(value, dict) and "$" in str(value):
                            # Handle operators
                            for op, op_value in value.items():
                                if op == "$in" and isinstance(op_value, list):
                                    query = query.where(field, "in", op_value)
                                elif op == "$ne":
                                    query = query.where(field, "!=", op_value)
                        else:
                            # Simple equality
                            query = query.where(field, "==", value)
                    except Exception as e:
                        logger.error(f"Error applying filter {field}={value}: {e}")

            # Apply ordering
            if order_by:
                try:
                    if descending:
                        query = query.order_by(
                            order_by, direction=firestore.Query.DESCENDING
                        )
                    else:
                        query = query.order_by(
                            order_by, direction=firestore.Query.ASCENDING
                        )
                except Exception as e:
                    logger.error(f"Error applying order_by {order_by}: {e}")

            # Apply limit
            if limit:
                query = query.limit(limit)

            # Execute query
            docs = query.stream()

            results = []
            for doc in docs:
                try:
                    data = doc.to_dict()
                    if data:
                        data["id"] = doc.id

                        # 🔥 FIX: Convert Firestore timestamps to datetime objects
                        for key, value in data.items():
                            if hasattr(
                                value, "timestamp"
                            ):  # Check if it's a Firestore timestamp
                                # Convert to Python datetime
                                data[key] = datetime.fromtimestamp(value.timestamp())

                        results.append(data)
                except Exception as e:
                    logger.error(f"Error processing document {doc.id}: {e}")

            return results

        except Exception as e:
            logger.error(f"Failed to query collection {collection}: {str(e)}")
            return []  # Return empty list instead of raising exception

    def delete(self, collection: str, document_id: str) -> bool:
        """
        Delete document from Firestore.

        Args:
            collection: Collection name
            document_id: Document ID

        Returns:
            True if successful
        """
        try:
            doc_ref = self._db.collection(collection).document(document_id)
            doc_ref.delete()
            return True

        except Exception as e:
            logger.error(
                f"Failed to delete document {collection}/{document_id}: {str(e)}"
            )
            raise DatabaseError(f"Failed to delete document: {str(e)}")

    def get_all(
        self,
        collection: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all documents from collection.

        Args:
            collection: Collection name
            limit: Maximum number of documents
            offset: Number of documents to skip

        Returns:
            List of all documents
        """
        return self.query(collection=collection, limit=limit, offset=offset)

    def count(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count documents in collection.

        Args:
            collection: Collection name
            filters: Optional filters

        Returns:
            Number of documents
        """
        try:
            query = self._db.collection(collection)

            # Apply filters
            if filters:
                for field, value in filters.items():
                    query = query.where(field, "==", value)

            # Get count (Firestore doesn't have count, so we get all and count)
            docs = query.stream()
            count = 0
            for _ in docs:
                count += 1

            return count

        except Exception as e:
            logger.error(f"Failed to count documents in {collection}: {str(e)}")
            raise DatabaseError(f"Failed to count documents: {str(e)}")

    def batch_save(self, collection: str, documents: List[Dict[str, Any]]) -> bool:
        """
        Save multiple documents in batch.

        Args:
            collection: Collection name
            documents: List of documents with 'id' field

        Returns:
            True if successful
        """
        try:
            batch = self._db.batch()

            for doc_data in documents:
                doc_id = doc_data.get("id")
                if not doc_id:
                    continue

                # Remove id from data (Firestore uses document reference for id)
                doc_data_copy = doc_data.copy()
                doc_data_copy.pop("id", None)

                doc_ref = self._db.collection(collection).document(doc_id)
                batch.set(doc_ref, doc_data_copy, merge=True)

            batch.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to batch save to {collection}: {str(e)}")
            raise DatabaseError(f"Failed to batch save documents: {str(e)}")

    def batch_delete(self, collection: str, document_ids: List[str]) -> bool:
        """
        Delete multiple documents in batch.

        Args:
            collection: Collection name
            document_ids: List of document IDs

        Returns:
            True if successful
        """
        try:
            batch = self._db.batch()

            for doc_id in document_ids:
                doc_ref = self._db.collection(collection).document(doc_id)
                batch.delete(doc_ref)

            batch.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to batch delete from {collection}: {str(e)}")
            raise DatabaseError(f"Failed to batch delete documents: {str(e)}")

    def create_subcollection(
        self,
        collection: str,
        document_id: str,
        subcollection: str,
        subdocument_id: str,
        data: Dict[str, Any],
    ) -> bool:
        """
        Create document in subcollection.

        Args:
            collection: Parent collection name
            document_id: Parent document ID
            subcollection: Subcollection name
            subdocument_id: Subdocument ID
            data: Subdocument data

        Returns:
            True if successful
        """
        try:
            doc_ref = self._db.collection(collection).document(document_id)
            subdoc_ref = doc_ref.collection(subcollection).document(subdocument_id)
            subdoc_ref.set(data, merge=True)
            return True

        except Exception as e:
            logger.error(
                f"Failed to create subdocument {collection}/{document_id}/{subcollection}/{subdocument_id}: {str(e)}"
            )
            raise DatabaseError(f"Failed to create subdocument: {str(e)}")

    def get_subcollection(
        self, collection: str, document_id: str, subcollection: str
    ) -> List[Dict[str, Any]]:
        """
        Get all documents from subcollection.

        Args:
            collection: Parent collection name
            document_id: Parent document ID
            subcollection: Subcollection name

        Returns:
            List of subdocuments
        """
        try:
            doc_ref = self._db.collection(collection).document(document_id)
            subdocs = doc_ref.collection(subcollection).stream()

            results = []
            for doc in subdocs:
                data = doc.to_dict()
                data["id"] = doc.id
                results.append(data)

            return results

        except Exception as e:
            logger.error(
                f"Failed to get subcollection {collection}/{document_id}/{subcollection}: {str(e)}"
            )
            raise DatabaseError(f"Failed to get subcollection: {str(e)}")

    def increment_field(
        self, collection: str, document_id: str, field: str, amount: int = 1
    ) -> bool:
        """
        Increment a numeric field atomically.

        Args:
            collection: Collection name
            document_id: Document ID
            field: Field name to increment
            amount: Amount to increment

        Returns:
            True if successful
        """
        try:
            doc_ref = self._db.collection(collection).document(document_id)
            doc_ref.update({field: firestore.Increment(amount)})
            return True

        except Exception as e:
            logger.error(
                f"Failed to increment field {field} in {collection}/{document_id}: {str(e)}"
            )
            raise DatabaseError(f"Failed to increment field: {str(e)}")

    def run_transaction(self, transaction_func) -> Any:
        """
        Run a Firestore transaction.

        Args:
            transaction_func: Function that takes a transaction object

        Returns:
            Result of transaction function
        """
        try:
            return self._db.transaction(transaction_func)
        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            raise DatabaseError(f"Transaction failed: {str(e)}")

    def create_index(self, collection: str, fields: List[str]) -> bool:
        """
        Create composite index (note: Firestore indexes are created in Firebase console).
        This is a placeholder for compatibility.

        Args:
            collection: Collection name
            fields: List of fields to index

        Returns:
            True (Firestore creates indexes automatically or via console)
        """
        logger.info(
            f"Note: Firestore indexes for {collection} on fields {fields} should be created in Firebase console"
        )
        return True

    def test_connection(self) -> bool:
        """Test Firebase connection."""
        try:
            # Try to list collections
            collections = self._db.collections()
            next(collections, None)  # Get first collection if exists
            return True
        except Exception as e:
            logger.error(f"Firebase connection test failed: {str(e)}")
            return False

    def get_database_info(self) -> Dict[str, Any]:
        """Get database information."""
        try:
            # Note: Firestore doesn't have a direct way to get database info
            # This returns basic configuration info
            return {
                "provider": "firebase",
                "type": "firestore",
                "initialized": True,
                "project_id": self._db.project,
                "collections": [],  # Would need to list collections
            }
        except Exception as e:
            return {
                "provider": "firebase",
                "type": "firestore",
                "initialized": False,
                "error": str(e),
            }


# PostgreSQL Provider (for future migration)
class PostgreSQLProvider:
    """PostgreSQL database provider."""

    def __init__(self):
        import psycopg2
        from psycopg2.extras import RealDictCursor

        self.connection_string = os.getenv("POSTGRES_URL")

        if not self.connection_string:
            raise ConfigurationError("PostgreSQL connection string not configured")

        try:
            self.conn = psycopg2.connect(self.connection_string)
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)

            # Create tables if they don't exist
            self._create_tables()

            logger.info("PostgreSQL initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {str(e)}")
            raise ConfigurationError(f"Failed to initialize PostgreSQL: {str(e)}")

    def _create_tables(self):
        """Create database tables."""
        tables = {
            "users": """
                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR(255) PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    tier VARCHAR(50) DEFAULT 'free',
                    status VARCHAR(50) DEFAULT 'active',
                    full_name VARCHAR(255),
                    avatar_url TEXT,
                    language VARCHAR(10) DEFAULT 'en',
                    timezone VARCHAR(50) DEFAULT 'UTC',
                    credits_remaining INTEGER DEFAULT 0,
                    videos_processed_this_month INTEGER DEFAULT 0,
                    monthly_video_limit INTEGER DEFAULT 3,
                    total_videos_processed INTEGER DEFAULT 0,
                    total_processing_time FLOAT DEFAULT 0.0,
                    stripe_customer_id VARCHAR(255),
                    stripe_subscription_id VARCHAR(255),
                    subscription_start_date TIMESTAMP,
                    subscription_end_date TIMESTAMP,
                    subscription_cancel_at_period_end BOOLEAN DEFAULT FALSE,
                    settings JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    email_verified_at TIMESTAMP,
                    is_admin BOOLEAN DEFAULT FALSE,
                    permissions TEXT[] DEFAULT '{}'
                )
            """,
            "videos": """
                CREATE TABLE IF NOT EXISTS videos (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255) REFERENCES users(id),
                    original_filename VARCHAR(255) NOT NULL,
                    file_size BIGINT NOT NULL,
                    duration FLOAT NOT NULL,
                    mime_type VARCHAR(100) NOT NULL,
                    status VARCHAR(50) DEFAULT 'uploaded',
                    video_type VARCHAR(50) DEFAULT 'unknown',
                    priority INTEGER DEFAULT 0,
                    original_path TEXT,
                    processing_path TEXT,
                    output_path TEXT,
                    transcription TEXT,
                    transcription_language VARCHAR(10),
                    title TEXT,
                    description TEXT,
                    tags TEXT[] DEFAULT '{}',
                    ai_thumbnails TEXT[] DEFAULT '{}',
                    extracted_thumbnails TEXT[] DEFAULT '{}',
                    selected_thumbnail TEXT,
                    output_quality VARCHAR(20) DEFAULT '720p',
                    output_format VARCHAR(10) DEFAULT 'mp4',
                    applied_styles TEXT[] DEFAULT '{}',
                    output_video_url TEXT,
                    output_video_size BIGINT,
                    translated_transcription TEXT,
                    translation_language VARCHAR(10),
                    translated_title TEXT,
                    translated_description TEXT,
                    processing_started TIMESTAMP,
                    processing_completed TIMESTAMP,
                    processing_time FLOAT,
                    ai_costs JSONB DEFAULT '{}',
                    total_cost FLOAT DEFAULT 0.0,
                    processed_tier VARCHAR(50) DEFAULT 'free',
                    scheduled_for_deletion TIMESTAMP,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            "processing_jobs": """
                CREATE TABLE IF NOT EXISTS processing_jobs (
                    id VARCHAR(255) PRIMARY KEY,
                    video_id VARCHAR(255) REFERENCES videos(id),
                    user_id VARCHAR(255) REFERENCES users(id),
                    task_id VARCHAR(255),
                    status VARCHAR(50) DEFAULT 'pending',
                    current_step VARCHAR(100),
                    progress FLOAT DEFAULT 0.0,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """,
            "credit_transactions": """
                CREATE TABLE IF NOT EXISTS credit_transactions (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255) REFERENCES users(id),
                    amount INTEGER NOT NULL,
                    description TEXT,
                    video_id VARCHAR(255),
                    source VARCHAR(50),
                    balance_after INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            "subscriptions": """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255) REFERENCES users(id),
                    tier VARCHAR(50) NOT NULL,
                    status VARCHAR(50) DEFAULT 'active',
                    stripe_subscription_id VARCHAR(255) UNIQUE NOT NULL,
                    stripe_customer_id VARCHAR(255) NOT NULL,
                    stripe_price_id VARCHAR(255) NOT NULL,
                    current_period_start TIMESTAMP NOT NULL,
                    current_period_end TIMESTAMP NOT NULL,
                    cancel_at_period_end BOOLEAN DEFAULT FALSE,
                    amount FLOAT NOT NULL,
                    currency VARCHAR(3) DEFAULT 'USD',
                    billing_cycle VARCHAR(20) DEFAULT 'monthly',
                    features JSONB DEFAULT '{}',
                    last_payment_date TIMESTAMP,
                    next_payment_date TIMESTAMP,
                    trial_start TIMESTAMP,
                    trial_end TIMESTAMP,
                    is_in_trial BOOLEAN DEFAULT FALSE,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    cancelled_at TIMESTAMP
                )
            """,
        }

        for table_name, create_sql in tables.items():
            try:
                self.cursor.execute(create_sql)
                self.conn.commit()
            except Exception as e:
                logger.error(f"Failed to create table {table_name}: {str(e)}")
                self.conn.rollback()

    # Implement similar methods as FirebaseProvider for PostgreSQL...

    def save(self, collection: str, document_id: str, data: Dict[str, Any]) -> bool:
        """Save document to PostgreSQL."""
        # Implementation similar to Firebase but for PostgreSQL
        pass

    def get(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document from PostgreSQL."""
        pass
