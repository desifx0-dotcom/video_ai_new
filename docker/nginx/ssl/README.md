# SSL Certificates

Place your SSL certificates in this directory:

1. `certificate.crt` - Your SSL certificate
2. `private.key` - Your private key
3. `chain.crt` - Certificate chain (optional)

## Development
For development, you can generate self-signed certificates:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout private.key \
    -out certificate.crt \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"