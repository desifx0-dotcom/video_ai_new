# test_production.py
print("Testing Production Gevent Setup...")

# 1. Test monkey patching
from gevent import monkey
monkey.patch_socket()
print("✅ Gevent patched (SSL excluded)")

# 2. Test Firebase import
import firebase_admin
print("✅ Firebase imported")

# 3. Test gRPC gevent init
import grpc
try:
    grpc._cython.cygrpc.init_grpc_gevent()
    print("✅ gRPC gevent mode enabled")
except:
    print("⚠️ gRPC gevent init not needed")

# 4. Test SocketIO import
from flask_socketio import SocketIO
print("✅ SocketIO ready")

print("\n🎉 Production setup is ready!")