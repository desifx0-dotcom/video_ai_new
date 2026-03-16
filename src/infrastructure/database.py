"""
Database abstraction layer.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Union
import json
from datetime import datetime
import uuid

class Database(ABC):
    """Abstract database interface."""
    
    @abstractmethod
    def get(self, 
            collection: str, 
            document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID."""
        pass
    
    @abstractmethod
    def save(self, 
             collection: str, 
             document_id: str, 
             data: Dict[str, Any]) -> bool:
        """Save a document."""
        pass
    
    @abstractmethod
    def delete(self, 
               collection: str, 
               document_id: str) -> bool:
        """Delete a document."""
        pass
    
    @abstractmethod
    def query(self, 
              collection: str,
              filters: Optional[Dict[str, Any]] = None,
              order_by: Optional[str] = None,
              descending: bool = False,
              limit: int = 100,
              offset: int = 0) -> List[Dict[str, Any]]:
        """Query documents."""
        pass
    
    @abstractmethod
    def count(self, 
              collection: str,
              filters: Optional[Dict[str, Any]] = None) -> int:
        """Count documents."""
        pass
    
    @abstractmethod
    def exists(self, 
               collection: str, 
               document_id: str) -> bool:
        """Check if document exists."""
        pass
    
    @abstractmethod
    def batch_get(self, 
                  collection: str, 
                  document_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get multiple documents."""
        pass
    
    @abstractmethod
    def batch_save(self, 
                   collection: str, 
                   documents: Dict[str, Dict[str, Any]]) -> bool:
        """Save multiple documents."""
        pass
    
    @abstractmethod
    def batch_delete(self, 
                     collection: str, 
                     document_ids: List[str]) -> bool:
        """Delete multiple documents."""
        pass
    
    def generate_id(self) -> str:
        """Generate a unique document ID."""
        return str(uuid.uuid4())
    
    def save_with_generated_id(self, 
                              collection: str, 
                              data: Dict[str, Any]) -> str:
        """Save document with auto-generated ID."""
        document_id = self.generate_id()
        data['id'] = document_id
        data['created_at'] = datetime.utcnow().isoformat()
        data['updated_at'] = data['created_at']
        
        if self.save(collection, document_id, data):
            return document_id
        raise Exception("Failed to save document")
    
    def update(self, 
               collection: str, 
               document_id: str, 
               updates: Dict[str, Any]) -> bool:
        """Update a document."""
        # Get existing document
        existing = self.get(collection, document_id)
        if not existing:
            return False
        
        # Apply updates
        existing.update(updates)
        existing['updated_at'] = datetime.utcnow().isoformat()
        
        return self.save(collection, document_id, existing)
    
    def increment(self, 
                  collection: str, 
                  document_id: str, 
                  field: str, 
                  amount: int = 1) -> bool:
        """Increment a numeric field."""
        existing = self.get(collection, document_id)
        if not existing:
            return False
        
        current_value = existing.get(field, 0)
        if not isinstance(current_value, (int, float)):
            return False
        
        updates = {field: current_value + amount}
        return self.update(collection, document_id, updates)
    
    def paginate(self, 
                 collection: str,
                 filters: Optional[Dict[str, Any]] = None,
                 order_by: Optional[str] = None,
                 descending: bool = False,
                 page: int = 1,
                 per_page: int = 20) -> Dict[str, Any]:
        """Paginate query results."""
        offset = (page - 1) * per_page
        
        # Get total count
        total = self.count(collection, filters)
        
        # Get page results
        results = self.query(
            collection=collection,
            filters=filters,
            order_by=order_by,
            descending=descending,
            limit=per_page,
            offset=offset
        )
        
        # Calculate pagination metadata
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        has_next = page < total_pages
        has_prev = page > 1
        
        return {
            'items': results,
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': has_next,
            'has_prev': has_prev
        }

class FirebaseDatabase(Database):
    """Firebase Firestore database implementation."""
    
    def __init__(self, config: Dict[str, Any] = None):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError:
            raise ImportError("firebase-admin is required for FirebaseDatabase")
        
        config = config or {}
        
        # Initialize Firebase app
        try:
            # Check if already initialized
            firebase_admin.get_app()
        except ValueError:
            # Initialize with credentials
            creds_path = config.get('credentials_path')
            if creds_path:
                cred = credentials.Certificate(creds_path)
            else:
                # Try to use environment variable or default
                cred = credentials.ApplicationDefault()
            
            firebase_admin.initialize_app(cred)
        
        # Get Firestore client
        self.db = firestore.client()
        
        # Batch operation settings
        self.batch_size = config.get('batch_size', 500)  # Firestore limit
    
    def get(self, 
            collection: str, 
            document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document from Firestore."""
        try:
            doc_ref = self.db.collection(collection).document(document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return self._convert_firestore_types(data)
            return None
            
        except Exception as e:
            import logging
            logging.error(f"Firestore get error: {e}")
            return None
    
    def save(self, 
             collection: str, 
             document_id: str, 
             data: Dict[str, Any]) -> bool:
        """Save a document to Firestore."""
        try:
            # Remove ID from data (it's in the document path)
            data_to_save = data.copy()
            if 'id' in data_to_save:
                del data_to_save['id']
            
            # Add timestamps if not present
            if 'created_at' not in data_to_save:
                data_to_save['created_at'] = firestore.SERVER_TIMESTAMP
            
            data_to_save['updated_at'] = firestore.SERVER_TIMESTAMP
            
            # Convert Python types to Firestore types
            data_to_save = self._convert_to_firestore_types(data_to_save)
            
            # Save document
            doc_ref = self.db.collection(collection).document(document_id)
            doc_ref.set(data_to_save)
            
            return True
            
        except Exception as e:
            import logging
            logging.error(f"Firestore save error: {e}")
            return False
    
    def delete(self, 
               collection: str, 
               document_id: str) -> bool:
        """Delete a document from Firestore."""
        try:
            doc_ref = self.db.collection(collection).document(document_id)
            doc_ref.delete()
            return True
            
        except Exception as e:
            import logging
            logging.error(f"Firestore delete error: {e}")
            return False
    
    def query(self, 
              collection: str,
              filters: Optional[Dict[str, Any]] = None,
              order_by: Optional[str] = None,
              descending: bool = False,
              limit: int = 100,
              offset: int = 0) -> List[Dict[str, Any]]:
        """Query documents in Firestore."""
        try:
            query = self.db.collection(collection)
            
            # Apply filters
            if filters:
                for field, condition in filters.items():
                    if isinstance(condition, dict):
                        # Complex condition (==, !=, >, <, etc.)
                        for op, value in condition.items():
                            if op == '==':
                                query = query.where(field, '==', value)
                            elif op == '!=':
                                query = query.where(field, '!=', value)
                            elif op == '>':
                                query = query.where(field, '>', value)
                            elif op == '>=':
                                query = query.where(field, '>=', value)
                            elif op == '<':
                                query = query.where(field, '<', value)
                            elif op == '<=':
                                query = query.where(field, '<=', value)
                            elif op == 'in':
                                query = query.where(field, 'in', value)
                            elif op == 'array_contains':
                                query = query.where(field, 'array_contains', value)
                    else:
                        # Simple equality
                        query = query.where(field, '==', condition)
            
            # Apply ordering
            if order_by:
                if descending:
                    query = query.order_by(order_by, direction=firestore.Query.DESCENDING)
                else:
                    query = query.order_by(order_by)
            
            # Apply limit and offset
            if offset > 0:
                # Note: Firestore doesn't support offset directly
                # We need to use cursor-based pagination
                # For simplicity, we'll fetch all and slice (not efficient for large offsets)
                docs = query.limit(limit + offset).stream()
                docs = list(docs)[offset:offset+limit]
            else:
                docs = query.limit(limit).stream()
            
            # Convert to list of dictionaries
            results = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                results.append(self._convert_firestore_types(data))
            
            return results
            
        except Exception as e:
            import logging
            logging.error(f"Firestore query error: {e}")
            return []
    
    def count(self, 
              collection: str,
              filters: Optional[Dict[str, Any]] = None) -> int:
        """Count documents in Firestore."""
        try:
            # Firestore doesn't have a direct count method
            # We need to use aggregation query (requires Firestore BLaze plan)
            # For simplicity, we'll fetch and count (not efficient for large collections)
            
            query = self.db.collection(collection)
            
            # Apply filters
            if filters:
                for field, condition in filters.items():
                    if isinstance(condition, dict):
                        for op, value in condition.items():
                            if op == '==':
                                query = query.where(field, '==', value)
                    else:
                        query = query.where(field, '==', condition)
            
            # Get all documents (with limit for safety)
            docs = query.limit(10000).stream()
            return sum(1 for _ in docs)
            
        except Exception as e:
            import logging
            logging.error(f"Firestore count error: {e}")
            return 0
    
    def exists(self, 
               collection: str, 
               document_id: str) -> bool:
        """Check if document exists in Firestore."""
        try:
            doc_ref = self.db.collection(collection).document(document_id)
            doc = doc_ref.get()
            return doc.exists
            
        except Exception as e:
            import logging
            logging.error(f"Firestore exists error: {e}")
            return False
    
    def batch_get(self, 
                  collection: str, 
                  document_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get multiple documents from Firestore."""
        try:
            if not document_ids:
                return {}
            
            # Firestore batch get limit is 10
            batch_size = 10
            results = {}
            
            for i in range(0, len(document_ids), batch_size):
                batch_ids = document_ids[i:i+batch_size]
                
                # Create document references
                doc_refs = [
                    self.db.collection(collection).document(doc_id)
                    for doc_id in batch_ids
                ]
                
                # Batch get
                docs = self.db.get_all(doc_refs)
                
                # Process results
                for doc in docs:
                    if doc.exists:
                        data = doc.to_dict()
                        data['id'] = doc.id
                        results[doc.id] = self._convert_firestore_types(data)
            
            return results
            
        except Exception as e:
            import logging
            logging.error(f"Firestore batch_get error: {e}")
            return {}
    
    def batch_save(self, 
                   collection: str, 
                   documents: Dict[str, Dict[str, Any]]) -> bool:
        """Save multiple documents to Firestore."""
        try:
            if not documents:
                return True
            
            # Process in batches due to Firestore limits
            for i in range(0, len(documents), self.batch_size):
                batch = self.db.batch()
                batch_items = list(documents.items())[i:i+self.batch_size]
                
                for doc_id, data in batch_items:
                    # Remove ID from data
                    data_to_save = data.copy()
                    if 'id' in data_to_save:
                        del data_to_save['id']
                    
                    # Add timestamps
                    if 'created_at' not in data_to_save:
                        data_to_save['created_at'] = firestore.SERVER_TIMESTAMP
                    
                    data_to_save['updated_at'] = firestore.SERVER_TIMESTAMP
                    
                    # Convert types
                    data_to_save = self._convert_to_firestore_types(data_to_save)
                    
                    # Add to batch
                    doc_ref = self.db.collection(collection).document(doc_id)
                    batch.set(doc_ref, data_to_save)
                
                # Commit batch
                batch.commit()
            
            return True
            
        except Exception as e:
            import logging
            logging.error(f"Firestore batch_save error: {e}")
            return False
    
    def batch_delete(self, 
                     collection: str, 
                     document_ids: List[str]) -> bool:
        """Delete multiple documents from Firestore."""
        try:
            if not document_ids:
                return True
            
            # Process in batches
            for i in range(0, len(document_ids), self.batch_size):
                batch = self.db.batch()
                batch_ids = document_ids[i:i+self.batch_size]
                
                for doc_id in batch_ids:
                    doc_ref = self.db.collection(collection).document(doc_id)
                    batch.delete(doc_ref)
                
                # Commit batch
                batch.commit()
            
            return True
            
        except Exception as e:
            import logging
            logging.error(f"Firestore batch_delete error: {e}")
            return False
    
    def _convert_firestore_types(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Firestore types to Python types."""
        from google.cloud import firestore
        
        converted = {}
        
        for key, value in data.items():
            if isinstance(value, firestore.DocumentReference):
                converted[key] = str(value.path)
            elif isinstance(value, firestore.GeoPoint):
                converted[key] = {
                    'latitude': value.latitude,
                    'longitude': value.longitude
                }
            elif isinstance(value, firestore.ArrayUnion):
                converted[key] = list(value.values)
            elif isinstance(value, firestore.ArrayRemove):
                converted[key] = list(value.values)
            elif isinstance(value, datetime):
                converted[key] = value.isoformat()
            elif isinstance(value, dict):
                converted[key] = self._convert_firestore_types(value)
            elif isinstance(value, list):
                converted[key] = [
                    self._convert_firestore_types(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                converted[key] = value
        
        return converted
    
    def _convert_to_firestore_types(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Python types to Firestore types."""
        from google.cloud import firestore
        
        converted = {}
        
        for key, value in data.items():
            if isinstance(value, dict):
                # Check if it's a GeoPoint
                if 'latitude' in value and 'longitude' in value:
                    converted[key] = firestore.GeoPoint(
                        value['latitude'],
                        value['longitude']
                    )
                else:
                    converted[key] = self._convert_to_firestore_types(value)
            elif isinstance(value, list):
                converted[key] = value  # Firestore handles lists
            elif isinstance(value, str):
                # Try to parse as datetime
                try:
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    converted[key] = dt
                except (ValueError, AttributeError):
                    converted[key] = value
            else:
                converted[key] = value
        
        return converted

class PostgreSQLDatabase(Database):
    """PostgreSQL database implementation."""
    
    def __init__(self, config: Dict[str, Any] = None):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError:
            raise ImportError("psycopg2 is required for PostgreSQLDatabase")
        
        config = config or {}
        
        # Connection parameters
        self.connection_params = {
            'host': config.get('host', 'localhost'),
            'port': config.get('port', 5432),
            'database': config.get('database', 'video_ai'),
            'user': config.get('user', 'postgres'),
            'password': config.get('password'),
            'sslmode': config.get('sslmode', 'prefer')
        }
        
        # Connection pool
        self.pool_size = config.get('pool_size', 10)
        self._connection_pool = []
        
        # Initialize tables
        self._init_database()
    
    def _get_connection(self):
        """Get a connection from the pool."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        try:
            if self._connection_pool:
                return self._connection_pool.pop()
        except IndexError:
            pass
        
        # Create new connection
        conn = psycopg2.connect(**self.connection_params)
        return conn
    
    def _return_connection(self, conn):
        """Return a connection to the pool."""
        if len(self._connection_pool) < self.pool_size:
            self._connection_pool.append(conn)
        else:
            conn.close()
    
    def _init_database(self):
        """Initialize database tables."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Create users table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id VARCHAR(255) PRIMARY KEY,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        tier VARCHAR(50) DEFAULT 'free',
                        credits_remaining INTEGER DEFAULT 0,
                        videos_processed_this_month INTEGER DEFAULT 0,
                        monthly_video_limit INTEGER DEFAULT 3,
                        total_videos_processed INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        stripe_customer_id VARCHAR(255),
                        stripe_subscription_id VARCHAR(255),
                        subscription_end_date TIMESTAMP,
                        settings JSONB DEFAULT '{}',
                        is_active BOOLEAN DEFAULT TRUE,
                        is_admin BOOLEAN DEFAULT FALSE
                    )
                """)
                
                # Create videos table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS videos (
                        id VARCHAR(255) PRIMARY KEY,
                        user_id VARCHAR(255) REFERENCES users(id),
                        original_filename VARCHAR(255),
                        file_size BIGINT,
                        duration FLOAT,
                        video_type VARCHAR(50) DEFAULT 'unknown',
                        status VARCHAR(50) DEFAULT 'uploaded',
                        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processing_started TIMESTAMP,
                        processing_completed TIMESTAMP,
                        transcription TEXT,
                        transcription_language VARCHAR(50),
                        title TEXT,
                        description TEXT,
                        tags TEXT[],
                        ai_thumbnails TEXT[],
                        extracted_thumbnails TEXT[],
                        selected_thumbnail VARCHAR(255),
                        output_quality VARCHAR(50) DEFAULT '720p',
                        applied_styles TEXT[],
                        output_video_url VARCHAR(255),
                        output_video_size BIGINT,
                        translated_transcription TEXT,
                        translation_language VARCHAR(50),
                        translated_title TEXT,
                        translated_description TEXT,
                        processing_time FLOAT,
                        ai_costs JSONB DEFAULT '{}',
                        total_cost FLOAT DEFAULT 0.0,
                        processed_tier VARCHAR(50) DEFAULT 'free',
                        scheduled_for_deletion TIMESTAMP,
                        is_deleted BOOLEAN DEFAULT FALSE,
                        error_message TEXT,
                        retry_count INTEGER DEFAULT 0
                    )
                """)
                
                # Create indexes
                cur.execute("CREATE INDEX IF NOT EXISTS idx_videos_user_id ON videos(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_videos_upload_date ON videos(upload_date)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier)")
                
                conn.commit()
                
        except Exception as e:
            conn.rollback()
            import logging
            logging.error(f"Failed to initialize database: {e}")
            raise
        finally:
            self._return_connection(conn)
    
    def get(self, 
            collection: str, 
            document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document from PostgreSQL."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                table_name = self._validate_collection(collection)
                cur.execute(
                    f"SELECT * FROM {table_name} WHERE id = %s",
                    (document_id,)
                )
                result = cur.fetchone()
                return dict(result) if result else None
                
        except Exception as e:
            import logging
            logging.error(f"PostgreSQL get error: {e}")
            return None
        finally:
            self._return_connection(conn)
    
    def save(self, 
             collection: str, 
             document_id: str, 
             data: Dict[str, Any]) -> bool:
        """Save a document to PostgreSQL."""
        conn = self._get_connection()
        try:
            table_name = self._validate_collection(collection)
            
            # Prepare data
            data_to_save = data.copy()
            data_to_save['id'] = document_id
            data_to_save['updated_at'] = 'NOW()'
            
            if 'created_at' not in data_to_save:
                data_to_save['created_at'] = 'NOW()'
            
            # Build SQL
            columns = []
            values = []
            placeholders = []
            updates = []
            
            for i, (key, value) in enumerate(data_to_save.items(), 1):
                columns.append(key)
                values.append(value)
                placeholders.append(f"%s")
                
                if key != 'id':
                    updates.append(f"{key} = EXCLUDED.{key}")
            
            sql = f"""
                INSERT INTO {table_name} ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                ON CONFLICT (id) DO UPDATE SET
                {', '.join(updates)}
            """
            
            with conn.cursor() as cur:
                cur.execute(sql, values)
                conn.commit()
                return True
                
        except Exception as e:
            conn.rollback()
            import logging
            logging.error(f"PostgreSQL save error: {e}")
            return False
        finally:
            self._return_connection(conn)
    
    def delete(self, 
               collection: str, 
               document_id: str) -> bool:
        """Delete a document from PostgreSQL."""
        conn = self._get_connection()
        try:
            table_name = self._validate_collection(collection)
            
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {table_name} WHERE id = %s",
                    (document_id,)
                )
                conn.commit()
                return cur.rowcount > 0
                
        except Exception as e:
            conn.rollback()
            import logging
            logging.error(f"PostgreSQL delete error: {e}")
            return False
        finally:
            self._return_connection(conn)
    
    def query(self, 
              collection: str,
              filters: Optional[Dict[str, Any]] = None,
              order_by: Optional[str] = None,
              descending: bool = False,
              limit: int = 100,
              offset: int = 0) -> List[Dict[str, Any]]:
        """Query documents in PostgreSQL."""
        conn = self._get_connection()
        try:
            table_name = self._validate_collection(collection)
            
            # Build WHERE clause
            where_clause = ""
            params = []
            
            if filters:
                conditions = []
                for field, condition in filters.items():
                    if isinstance(condition, dict):
                        for op, value in condition.items():
                            if op == '==':
                                conditions.append(f"{field} = %s")
                                params.append(value)
                            elif op == '!=':
                                conditions.append(f"{field} != %s")
                                params.append(value)
                            elif op == '>':
                                conditions.append(f"{field} > %s")
                                params.append(value)
                            elif op == '>=':
                                conditions.append(f"{field} >= %s")
                                params.append(value)
                            elif op == '<':
                                conditions.append(f"{field} < %s")
                                params.append(value)
                            elif op == '<=':
                                conditions.append(f"{field} <= %s")
                                params.append(value)
                            elif op == 'in':
                                placeholders = ', '.join(['%s'] * len(value))
                                conditions.append(f"{field} IN ({placeholders})")
                                params.extend(value)
                    else:
                        conditions.append(f"{field} = %s")
                        params.append(condition)
                
                if conditions:
                    where_clause = "WHERE " + " AND ".join(conditions)
            
            # Build ORDER BY clause
            order_clause = ""
            if order_by:
                direction = "DESC" if descending else "ASC"
                order_clause = f"ORDER BY {order_by} {direction}"
            
            # Build SQL
            sql = f"""
                SELECT * FROM {table_name}
                {where_clause}
                {order_clause}
                LIMIT %s OFFSET %s
            """
            
            params.extend([limit, offset])
            
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                results = cur.fetchall()
                return [dict(row) for row in results]
                
        except Exception as e:
            import logging
            logging.error(f"PostgreSQL query error: {e}")
            return []
        finally:
            self._return_connection(conn)
    
    def count(self, 
              collection: str,
              filters: Optional[Dict[str, Any]] = None) -> int:
        """Count documents in PostgreSQL."""
        conn = self._get_connection()
        try:
            table_name = self._validate_collection(collection)
            
            # Build WHERE clause
            where_clause = ""
            params = []
            
            if filters:
                conditions = []
                for field, condition in filters.items():
                    if isinstance(condition, dict):
                        for op, value in condition.items():
                            if op == '==':
                                conditions.append(f"{field} = %s")
                                params.append(value)
                    else:
                        conditions.append(f"{field} = %s")
                        params.append(condition)
                
                if conditions:
                    where_clause = "WHERE " + " AND ".join(conditions)
            
            # Build SQL
            sql = f"SELECT COUNT(*) FROM {table_name} {where_clause}"
            
            with conn.cursor() as cur:
                cur.execute(sql, params)
                result = cur.fetchone()
                return result[0] if result else 0
                
        except Exception as e:
            import logging
            logging.error(f"PostgreSQL count error: {e}")
            return 0
        finally:
            self._return_connection(conn)
    
    def exists(self, 
               collection: str, 
               document_id: str) -> bool:
        """Check if document exists in PostgreSQL."""
        conn = self._get_connection()
        try:
            table_name = self._validate_collection(collection)
            
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT 1 FROM {table_name} WHERE id = %s",
                    (document_id,)
                )
                result = cur.fetchone()
                return result is not None
                
        except Exception as e:
            import logging
            logging.error(f"PostgreSQL exists error: {e}")
            return False
        finally:
            self._return_connection(conn)
    
    def batch_get(self, 
                  collection: str, 
                  document_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get multiple documents from PostgreSQL."""
        if not document_ids:
            return {}
        
        conn = self._get_connection()
        try:
            table_name = self._validate_collection(collection)
            
            # Create placeholders
            placeholders = ', '.join(['%s'] * len(document_ids))
            
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"SELECT * FROM {table_name} WHERE id IN ({placeholders})",
                    document_ids
                )
                results = cur.fetchall()
                
                # Convert to dictionary
                return {
                    row['id']: dict(row)
                    for row in results
                }
                
        except Exception as e:
            import logging
            logging.error(f"PostgreSQL batch_get error: {e}")
            return {}
        finally:
            self._return_connection(conn)
    
    def batch_save(self, 
                   collection: str, 
                   documents: Dict[str, Dict[str, Any]]) -> bool:
        """Save multiple documents to PostgreSQL."""
        if not documents:
            return True
        
        conn = self._get_connection()
        try:
            table_name = self._validate_collection(collection)
            
            # Build SQL for batch insert/update
            with conn.cursor() as cur:
                for doc_id, data in documents.items():
                    # Prepare data
                    data_to_save = data.copy()
                    data_to_save['id'] = doc_id
                    data_to_save['updated_at'] = 'NOW()'
                    
                    if 'created_at' not in data_to_save:
                        data_to_save['created_at'] = 'NOW()'
                    
                    # Build columns and values
                    columns = []
                    values = []
                    placeholders = []
                    updates = []
                    
                    for i, (key, value) in enumerate(data_to_save.items(), 1):
                        columns.append(key)
                        values.append(value)
                        placeholders.append(f"%s")
                        
                        if key != 'id':
                            updates.append(f"{key} = EXCLUDED.{key}")
                    
                    sql = f"""
                        INSERT INTO {table_name} ({', '.join(columns)})
                        VALUES ({', '.join(placeholders)})
                        ON CONFLICT (id) DO UPDATE SET
                        {', '.join(updates)}
                    """
                    
                    cur.execute(sql, values)
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            import logging
            logging.error(f"PostgreSQL batch_save error: {e}")
            return False
        finally:
            self._return_connection(conn)
    
    def batch_delete(self, 
                     collection: str, 
                     document_ids: List[str]) -> bool:
        """Delete multiple documents from PostgreSQL."""
        if not document_ids:
            return True
        
        conn = self._get_connection()
        try:
            table_name = self._validate_collection(collection)
            
            # Create placeholders
            placeholders = ', '.join(['%s'] * len(document_ids))
            
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {table_name} WHERE id IN ({placeholders})",
                    document_ids
                )
                conn.commit()
                return True
                
        except Exception as e:
            conn.rollback()
            import logging
            logging.error(f"PostgreSQL batch_delete error: {e}")
            return False
        finally:
            self._return_connection(conn)
    
    def _validate_collection(self, collection: str) -> str:
        """Validate collection/table name."""
        # Prevent SQL injection
        if not collection.isidentifier():
            raise ValueError(f"Invalid collection name: {collection}")
        
        # Map collections to table names
        table_map = {
            'users': 'users',
            'videos': 'videos',
            'processing_jobs': 'processing_jobs',
            'subscriptions': 'subscriptions',
            'credit_transactions': 'credit_transactions',
            'api_logs': 'api_logs'
        }
        
        if collection not in table_map:
            raise ValueError(f"Unknown collection: {collection}")
        
        return table_map[collection]