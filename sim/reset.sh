#!/bin/bash
# 対象環境(t-)を初期状態へ戻す。検証用環境(v-)は破棄する。
# 冗長化制御デーモンも再起動して主回線状態から始める。
set -eu

RUN=/run/netwalker
mkdir -p "$RUN"

# 冗長化制御デーモン停止
if [ -f "$RUN/failover.pid" ]; then
  kill "$(cat "$RUN/failover.pid")" 2>/dev/null || true
  rm -f "$RUN/failover.pid"
fi
rm -f "$RUN/t-failover.json" "$RUN/t-failover.log"

# 検証用環境は破棄
/opt/netwalker/topo.sh destroy v- || true

# 対象環境を再構築
/opt/netwalker/topo.sh create t-
/opt/netwalker/start-services.sh t-

# 冗長化制御デーモン起動（対象環境のみ。AIの修正操作とは独立）
python3 /opt/netwalker/failover.py t- > "$RUN/failover-daemon.log" 2>&1 &
echo $! > "$RUN/failover.pid"

echo "reset done"
