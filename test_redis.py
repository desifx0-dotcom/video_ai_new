# test_redis.py
import redis
import os

# Your Redis URL
url = "redis://default:i0vxoRUATzYYZHNSWW5aBgrZvQPCV6Rr@redis-18771.crce286.ap-south-1-1.ec2.cloud.redislabs.com:18771"

print(f"Testing connection to Redis...")
print(f"Host: redis-18771.crce286.ap-south-1-1.ec2.cloud.redislabs.com")
print(f"Port: 18771")

try:
    r = redis.from_url(url)
    print("Ping response:", r.ping())
    print("✅ Redis connection successful!")

    # Test setting and getting a value
    r.set("test_key", "Hello from Video AI Studio")
    value = r.get("test_key")
    print(f"Test value: {value}")
    print("✅ Redis is fully functional!")

except Exception as e:
    print(f"❌ Redis connection failed: {e}")
