import redis

r = redis.Redis(
    host='redis-15622.crce206.ap-south-1-1.ec2.cloud.redislabs.com',
    port=15622,
    password='Gkn8sthCFB2PrbCTMkNPq8pYFaqhwBUA',
    decode_responses=True
)

print(r.ping())  # Should print: True