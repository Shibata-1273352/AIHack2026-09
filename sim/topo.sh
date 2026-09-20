#!/bin/bash
# NetWalker 擬似ネットワーク トポロジ管理（冪等）
#
#   client --- gw ---(主)--- r1 --- srv(order.example.com = 10.0.100.10)
#                \---(予備)-- r2 ---/
#
# 使い方: topo.sh {create|destroy} {t-|v-}
#   t- = 対象環境（本番役）、v- = 検証用環境（クローン）
# netns 内のインターフェース名は t-/v- で共通（diff 可能にするため）。
set -u

CMD="${1:?usage: topo.sh create-or-destroy t-or-v-}"
P="${2:?prefix required: t- or v-}"

case "$P" in
  t-|v-) ;;
  *) echo "invalid prefix: $P" >&2; exit 1 ;;
esac

RUN=/run/netwalker
mkdir -p "$RUN"

NSLIST=(client gw r1 r2 srv)

destroy() {
  # srv netns 内のサービスを止めてから netns を消す
  for name in nginx telnet; do
    pidf="$RUN/${P}${name}.pid"
    if [ -f "$pidf" ]; then
      kill "$(cat "$pidf")" 2>/dev/null || true
      rm -f "$pidf"
    fi
  done
  for n in "${NSLIST[@]}"; do
    ip netns del "${P}${n}" 2>/dev/null || true
  done
}

# link <nsA> <ifA> <ipA/len> <nsB> <ifB> <ipB/len>
mklink() {
  local a=$1 ifa=$2 ipa=$3 b=$4 ifb=$5 ipb=$6
  # veth 一時名は 15 文字以内
  ip link add nwtmpA type veth peer name nwtmpB
  ip link set nwtmpA netns "${P}${a}"
  ip link set nwtmpB netns "${P}${b}"
  ip -n "${P}${a}" link set nwtmpA name "$ifa"
  ip -n "${P}${b}" link set nwtmpB name "$ifb"
  ip -n "${P}${a}" addr add "$ipa" dev "$ifa"
  ip -n "${P}${b}" addr add "$ipb" dev "$ifb"
  ip -n "${P}${a}" link set "$ifa" up
  ip -n "${P}${b}" link set "$ifb" up
}

create() {
  destroy

  for n in "${NSLIST[@]}"; do
    ip netns add "${P}${n}"
    ip -n "${P}${n}" link set lo up
  done

  # 配線（アドレス設計は docs/requirements 準拠）
  mklink client eth-gw 10.0.1.10/24  gw eth-cl 10.0.1.1/24
  mklink gw     eth-r1 10.0.2.1/24   r1 eth-gw 10.0.2.2/24
  mklink gw     eth-r2 10.0.3.1/24   r2 eth-gw 10.0.3.2/24
  mklink r1     eth-srv 10.0.4.1/24  srv eth-r1 10.0.4.2/24
  mklink r2     eth-srv 10.0.5.1/24  srv eth-r2 10.0.5.2/24

  # サービスIP（受注サービス order.example.com）
  ip -n "${P}srv" addr add 10.0.100.10/32 dev lo

  # 転送を有効化
  for n in gw r1 r2; do
    ip netns exec "${P}${n}" sysctl -qw net.ipv4.ip_forward=1
  done

  # 経路（通常時は主回線 r1 経由）
  ip -n "${P}client" route add default via 10.0.1.1
  ip -n "${P}gw"  route add 10.0.100.10/32 via 10.0.2.2 dev eth-r1
  ip -n "${P}gw"  route add 10.0.4.0/24 via 10.0.2.2 dev eth-r1
  ip -n "${P}gw"  route add 10.0.5.0/24 via 10.0.3.2 dev eth-r2
  ip -n "${P}r1"  route add 10.0.100.10/32 via 10.0.4.2 dev eth-srv
  ip -n "${P}r1"  route add 10.0.1.0/24 via 10.0.2.1 dev eth-gw
  ip -n "${P}r2"  route add 10.0.100.10/32 via 10.0.5.2 dev eth-srv
  ip -n "${P}r2"  route add 10.0.1.0/24 via 10.0.3.1 dev eth-gw
  # srv の戻り経路（通常時は主回線 r1 経由）
  ip -n "${P}srv" route add 10.0.1.0/24 via 10.0.4.1 dev eth-r1
  ip -n "${P}srv" route add 10.0.2.0/24 via 10.0.4.1 dev eth-r1
  ip -n "${P}srv" route add 10.0.3.0/24 via 10.0.5.1 dev eth-r2

  # ベースライン ACL（正当ルール: telnet 遮断ポリシーは初期状態から存在する）
  for n in r1 r2; do
    ip netns exec "${P}${n}" nft -f - <<EOF
table inet fw {
  chain forward {
    type filter hook forward priority 0; policy accept;
    ip daddr 10.0.100.10 tcp dport 23 drop comment "POLICY-DENY-TELNET"
  }
}
EOF
  done
}

case "$CMD" in
  create)  create ;;
  destroy) destroy ;;
  *) echo "unknown command: $CMD" >&2; exit 1 ;;
esac
