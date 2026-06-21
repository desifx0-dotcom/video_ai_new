# patch_async.py
"""
Universal async patch for production.
Uses gevent for production-ready async I/O.
"""

import os
import sys

# ============================================
# 🔥 CRITICAL: Disable greendns BEFORE imports
# ============================================
os.environ['EVENTLET_NO_GREENDNS'] = '1'
os.environ['GEVENT_NO_GREENDNS'] = '1'

# ============================================
# PREFER GEVENT FOR PRODUCTION
# ============================================
ASYNC_MODE = 'threading'  # Default fallback

try:
    from gevent import monkey
    monkey.patch_all(
        socket=True,   # Async I/O
        ssl=True,      # HTTPS support
        time=True,     # Timeouts
        thread=False,  # DON'T patch threading
        dns=True       # DNS resolution
    )
    print("✅ Gevent patched successfully (production mode)")
    ASYNC_MODE = 'gevent'
    
except ImportError:
    print("⚠️ Gevent not available, using threading mode")
    ASYNC_MODE = 'threading'
    
except Exception as e:
    print(f"⚠️ Gevent patch failed: {e}, using threading mode")
    ASYNC_MODE = 'threading'

# Export for other modules
__all__ = ['ASYNC_MODE']