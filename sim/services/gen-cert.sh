#!/bin/bash
# 受注サービス用の自己署名証明書を生成する（ビルド時/初回起動時）。
# クライアント側は --cacert でこの証明書を信頼する。
set -eu

DIR=/etc/netwalker/certs
mkdir -p "$DIR"

if [ -f "$DIR/server.crt" ] && [ -f "$DIR/server.key" ]; then
  exit 0
fi

openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout "$DIR/server.key" -out "$DIR/server.crt" \
  -subj "/CN=order.example.com" \
  -addext "subjectAltName=DNS:order.example.com,IP:10.0.100.10" \
  2>/dev/null

chmod 644 "$DIR/server.crt"
chmod 600 "$DIR/server.key"
echo "certificate generated: $DIR/server.crt"
