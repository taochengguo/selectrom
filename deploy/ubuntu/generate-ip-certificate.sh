#!/usr/bin/env bash
set -euo pipefail

PUBLIC_IP="${1:-113.250.177.180}"
CERT_DIR="${2:-/etc/selectrom/tls}"

python3 - "$PUBLIC_IP" <<'PY'
import ipaddress
import sys

ipaddress.IPv4Address(sys.argv[1])
PY

install -d -m 700 "$CERT_DIR"
umask 077
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 30 \
    -subj "/CN=${PUBLIC_IP}" \
    -addext "subjectAltName=IP:${PUBLIC_IP}" \
    -keyout "${CERT_DIR}/ip.key" \
    -out "${CERT_DIR}/ip.crt"
chmod 600 "${CERT_DIR}/ip.key"
chmod 644 "${CERT_DIR}/ip.crt"
openssl x509 -in "${CERT_DIR}/ip.crt" -noout -ext subjectAltName -fingerprint -sha256
