#!/bin/bash
# SSL certificate generation script for development

set -e

SSL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN="localhost"
DAYS=3650

echo "🔐 Generating SSL certificates for $DOMAIN..."

# Create SSL directory if it doesn't exist
mkdir -p "$SSL_DIR"

# Generate private key
openssl genrsa -out "$SSL_DIR/server.key" 2048

# Generate CSR
openssl req -new -key "$SSL_DIR/server.key" -out "$SSL_DIR/server.csr" \
  -subj "/C=US/ST=State/L=City/O=Organization/OU=IT Department/CN=$DOMAIN"

# Generate self-signed certificate
openssl x509 -req -days $DAYS -in "$SSL_DIR/server.csr" \
  -signkey "$SSL_DIR/server.key" -out "$SSL_DIR/server.crt"

# Set proper permissions
chmod 600 "$SSL_DIR/server.key"
chmod 644 "$SSL_DIR/server.crt"

echo "✅ SSL certificates generated:"
echo "   - Private key: $SSL_DIR/server.key"
echo "   - Certificate: $SSL_DIR/server.crt"
echo "   - CSR: $SSL_DIR/server.csr"
echo ""
echo "⚠️  These are self-signed certificates for development only!"
echo "   For production, use certificates from a trusted CA like Let's Encrypt."