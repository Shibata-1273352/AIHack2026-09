#!/bin/bash
# srv netns 内で受注サービス(nginx https)とtelnetリスナを起動する。
# 使い方: start-services.sh {t-|v-}
set -eu

P="${1:?prefix required: t- or v-}"
RUN=/run/netwalker
export PATH="$PATH:/usr/sbin:/sbin"
mkdir -p "$RUN"

# 既存プロセスを止める（冪等）
for name in nginx telnet; do
  pidf="$RUN/${P}${name}.pid"
  if [ -f "$pidf" ]; then
    kill "$(cat "$pidf")" 2>/dev/null || true
    rm -f "$pidf"
  fi
done

# nginx 設定をプレフィックスで実体化
sed "s/__PREFIX__/${P}/g" /opt/netwalker/services/nginx.conf.tpl > "$RUN/${P}nginx.conf"

ip netns exec "${P}srv" nginx -c "$RUN/${P}nginx.conf"

ip netns exec "${P}srv" python3 /opt/netwalker/services/telnet_listener.py \
  > "$RUN/${P}telnet.log" 2>&1 &
echo $! > "$RUN/${P}telnet.pid"

# 起動確認（srv netns 内から直接）
for i in 1 2 3 4 5; do
  if ip netns exec "${P}srv" curl -sk --max-time 1 https://10.0.100.10/ | grep -q NETWALKER-ORDER-OK; then
    echo "services up (${P})"
    exit 0
  fi
  sleep 0.5
done
echo "WARNING: ${P}srv service check failed" >&2
exit 1
