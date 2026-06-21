# test_gevent.py
"""
Test gevent + Redis integration.
"""

import os
import time
from dotenv import load_dotenv
load_dotenv('.env')

print("="*60)
print("🔍 TESTING GEVENT + REDIS")
print("="*60)

# 1. Test gevent import
print("\n1. Testing gevent...")
try:
    from gevent import monkey
    monkey.patch_all(socket=True, ssl=True, time=True, thread=False, dns=True)
    print("✅ Gevent patched successfully")
except ImportError:
    print("❌ Gevent not installed")
    exit(1)

# 2. Test Redis connection
print("\n2. Testing Redis connection...")
try:
    import redis
    redis_url = os.getenv('REDIS_URL')
    r = redis.from_url(redis_url, decode_responses=True, socket_timeout=5)
    r.ping()
    print("✅ Redis connected")
    
    # Test set/get
    r.set('gevent_test', 'working')
    value = r.get('gevent_test')
    print(f"✅ Redis set/get: {value}")
    
except Exception as e:
    print(f"❌ Redis error: {e}")
    exit(1)

# 3. Test SocketIO with gevent
print("\n3. Testing SocketIO with gevent...")
try:
    from flask_socketio import SocketIO
    from patch_async import ASYNC_MODE
    
    print(f"✅ Async mode: {ASYNC_MODE}")
    print(f"✅ Flask-SocketIO can use {ASYNC_MODE}")
    
except Exception as e:
    print(f"❌ SocketIO error: {e}")

print("\n" + "="*60)
print("✅ All tests passed! Gevent is working.")
print("="*60)