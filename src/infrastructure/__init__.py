"""
Infrastructure abstraction layer.
"""
from .cache import Cache, RedisCache, MemoryCache
from .queue import Queue, RedisQueue, MemoryQueue
from .storage import Storage, LocalStorage, S3Storage, GCSStorage
from .database import Database, FirebaseDatabase, PostgreSQLDatabase

__all__ = [
    'Cache',
    'RedisCache',
    'MemoryCache',
    'Queue',
    'RedisQueue',
    'MemoryQueue',
    'Storage',
    'LocalStorage',
    'S3Storage',
    'GCSStorage',
    'Database',
    'FirebaseDatabase',
    'PostgreSQLDatabase',
]

# Factory for creating infrastructure components
class InfrastructureFactory:
    """Factory for creating infrastructure components."""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self._components = {}
    
    def get_cache(self, cache_type: str = None, config: dict = None) -> Cache:
        """Get cache instance."""
        cache_type = cache_type or self.config.get('CACHE_TYPE', 'redis')
        
        if cache_type not in self._components.get('cache', {}):
            if cache_type == 'redis':
                cache_config = config or self.config.get('REDIS_CONFIG', {})
                self._components.setdefault('cache', {})[cache_type] = RedisCache(cache_config)
            elif cache_type == 'memory':
                self._components.setdefault('cache', {})[cache_type] = MemoryCache()
            else:
                raise ValueError(f"Unsupported cache type: {cache_type}")
        
        return self._components['cache'][cache_type]
    
    def get_queue(self, queue_type: str = None, config: dict = None) -> Queue:
        """Get queue instance."""
        queue_type = queue_type or self.config.get('QUEUE_TYPE', 'redis')
        
        if queue_type not in self._components.get('queue', {}):
            if queue_type == 'redis':
                queue_config = config or self.config.get('REDIS_CONFIG', {})
                self._components.setdefault('queue', {})[queue_type] = RedisQueue(queue_config)
            elif queue_type == 'memory':
                self._components.setdefault('queue', {})[queue_type] = MemoryQueue()
            else:
                raise ValueError(f"Unsupported queue type: {queue_type}")
        
        return self._components['queue'][queue_type]
    
    def get_storage(self, storage_type: str = None, config: dict = None) -> Storage:
        """Get storage instance."""
        storage_type = storage_type or self.config.get('STORAGE_TYPE', 'local')
        
        if storage_type not in self._components.get('storage', {}):
            if storage_type == 'local':
                storage_config = config or self.config.get('STORAGE_CONFIG', {})
                self._components.setdefault('storage', {})[storage_type] = LocalStorage(storage_config)
            elif storage_type == 's3':
                storage_config = config or self.config.get('S3_CONFIG', {})
                self._components.setdefault('storage', {})[storage_type] = S3Storage(storage_config)
            elif storage_type == 'gcs':
                storage_config = config or self.config.get('GCS_CONFIG', {})
                self._components.setdefault('storage', {})[storage_type] = GCSStorage(storage_config)
            else:
                raise ValueError(f"Unsupported storage type: {storage_type}")
        
        return self._components['storage'][storage_type]
    
    def get_database(self, database_type: str = None, config: dict = None) -> Database:
        """Get database instance."""
        database_type = database_type or self.config.get('DATABASE_TYPE', 'firebase')
        
        if database_type not in self._components.get('database', {}):
            if database_type == 'firebase':
                db_config = config or self.config.get('FIREBASE_CONFIG', {})
                self._components.setdefault('database', {})[database_type] = FirebaseDatabase(db_config)
            elif database_type == 'postgresql':
                db_config = config or self.config.get('POSTGRES_CONFIG', {})
                self._components.setdefault('database', {})[database_type] = PostgreSQLDatabase(db_config)
            else:
                raise ValueError(f"Unsupported database type: {database_type}")
        
        return self._components['database'][database_type]
    
    def clear_cache(self, component_type: str = None):
        """Clear cached component instances."""
        if component_type:
            if component_type in self._components:
                del self._components[component_type]
        else:
            self._components.clear()

# Global infrastructure factory
infrastructure = InfrastructureFactory()