#!/bin/bash
# NetWalker シミュレータ起動: 自己診断 → トポロジ構築 → サービス → 制御API
set -eu

RUN=/run/netwalker
mkdir -p "$RUN"

echo "=== NetWalker sim self-check ==="
selfcheck() {
  # netns / veth / nft が privileged コンテナで動くかのスモークテスト
  ip netns add nw-selfck 2>/dev/null || { echo "NG: netns 作成不可"; return 1; }
  ip link add nwsc0 type veth peer name nwsc1 2>/dev/null || { echo "NG: veth 作成不可"; ip netns del nw-selfck; return 1; }
  ip link set nwsc0 netns nw-selfck
  ip netns exec nw-selfck nft add table inet sc 2>/dev/null || { echo "NG: nftables 不可"; ip link del nwsc1 2>/dev/null || true; ip netns del nw-selfck; return 1; }
  ip link del nwsc1 2>/dev/null || true
  ip netns del nw-selfck
  echo "OK: netns / veth / nftables"
}
if ! selfcheck; then
  echo "FATAL: このコンテナ環境では netns/veth/nftables が利用できません。" >&2
  echo "docker run に --privileged が付いているか確認してください。" >&2
  exit 1
fi

# 名前解決（拠点側に固定したテスト用の名前解決、§7.2）
grep -q order.example.com /etc/hosts || echo "10.0.100.10 order.example.com" >> /etc/hosts

# 証明書
bash /opt/netwalker/services/gen-cert.sh

# 対象環境の構築 + サービス + 冗長化制御
bash /opt/netwalker/reset.sh

echo "=== starting ctl API :9000 ==="
cd /opt/netwalker
exec uvicorn ctl:app --host 0.0.0.0 --port 9000 --log-level warning
