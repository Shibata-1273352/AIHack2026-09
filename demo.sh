#!/bin/bash
# NetWalker デモ起動スクリプト
#   ./demo.sh          … シミュレータ + バックエンド(+フロント配信) を起動
#   ./demo.sh stop     … 停止
#   ./demo.sh status   … 状態表示
set -u
cd "$(dirname "$0")"

SIM_PORT=9000
API_PORT=8000

say() { printf "\033[1;34m[demo]\033[0m %s\n" "$*"; }
err() { printf "\033[1;31m[demo]\033[0m %s\n" "$*" >&2; }

stop_all() {
  pkill -f "uvicorn app.main:app" 2>/dev/null && say "backend を停止しました" || true
  docker rm -f nwsim >/dev/null 2>&1 && say "シミュレータを停止しました" || true
}

status() {
  echo "--- docker ---"
  docker ps --filter name=nwsim --format "{{.Names}} {{.Status}}" || true
  echo "--- sim ---"
  curl -s "localhost:${SIM_PORT}/healthz" || echo "(応答なし)"
  echo
  echo "--- backend ---"
  curl -s "localhost:${API_PORT}/api/config" || echo "(応答なし)"
  echo
}

case "${1:-start}" in
  stop) stop_all; exit 0 ;;
  status) status; exit 0 ;;
  start) ;;
  *) err "usage: ./demo.sh [start|stop|status]"; exit 1 ;;
esac

# ---- 前提確認 ----
if ! docker info >/dev/null 2>&1; then
  say "Docker Desktop を起動しています…"
  open -a Docker
  for i in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker info >/dev/null 2>&1 || { err "Docker が起動しませんでした"; exit 1; }
fi
command -v uv >/dev/null || { err "uv が必要です (brew install uv)"; exit 1; }

# ---- ポート整理 ----
pkill -f "uvicorn app.main:app" 2>/dev/null || true

# ---- シミュレータ ----
# sim/ の変更（制御API・冗長化制御デーモン）を確実に反映するため毎回ビルドする。
# Docker のレイヤキャッシュが効くので、変更が無ければ数秒で終わる。
# 「イメージがあればスキップ」にすると、更新しても古い sim で動き続けてしまう。
say "シミュレータイメージをビルドします（変更が無ければキャッシュで即完了）…"
docker build -q -t netwalker-sim sim/ >/dev/null || { err "シミュレータのビルドに失敗しました"; exit 1; }
docker rm -f nwsim >/dev/null 2>&1 || true
say "シミュレータを起動します（privileged / 127.0.0.1:${SIM_PORT}）…"
docker run -d --name nwsim --privileged -p "127.0.0.1:${SIM_PORT}:9000" \
  --restart unless-stopped netwalker-sim >/dev/null

say "シミュレータの healthz を待機中…"
for i in $(seq 1 30); do
  if curl -sf "localhost:${SIM_PORT}/healthz" | grep -q '"ok":true'; then break; fi
  sleep 1
done
curl -sf "localhost:${SIM_PORT}/healthz" | grep -q '"ok":true' \
  || { err "シミュレータが起動しません: docker logs nwsim を確認"; exit 1; }
say "シミュレータ OK（netns トポロジ稼働中）"

# ---- フロントエンド（ビルド成果物が無ければビルド） ----
if [ ! -f backend/static/index.html ]; then
  say "フロントエンドをビルドします…"
  (cd frontend && npm install && npm run build)
fi

# ---- 操作トークン（M-09/N-02: 承認・注入・リセットの認証） ----
# 環境変数 APPROVAL_TOKEN があればそれを使い、無ければ起動ごとに生成する。
APPROVAL_TOKEN="${APPROVAL_TOKEN:-$(openssl rand -hex 12 2>/dev/null || date +%s%N | shasum | cut -c1-24)}"

# ---- バックエンド ----
say "バックエンドを起動します（:${API_PORT}）…"
(cd backend && uv sync -q && APPROVAL_TOKEN="${APPROVAL_TOKEN}" nohup uv run uvicorn app.main:app \
  --host 0.0.0.0 --port "${API_PORT}" > ../backend.out.log 2>&1 &)
for i in $(seq 1 20); do
  curl -sf "localhost:${API_PORT}/api/config" >/dev/null && break
  sleep 1
done

CFG=$(curl -sf "localhost:${API_PORT}/api/config") || { err "backend が起動しません: backend.out.log を確認"; exit 1; }
MODE=$(echo "$CFG" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['agent_mode'], d['route_mode'], 'key=' + ('あり' if d['has_api_key'] else 'なし'))")
IP=$(ipconfig getifaddr en0 2>/dev/null || echo "<MacのIP>")

say "起動完了！"
echo ""
echo "  実行モード      : ${MODE}"
echo "  Mac コンソール  : http://localhost:${API_PORT}/console?token=${APPROVAL_TOKEN}"
echo "  iPad 承認端末   : http://${IP}:${API_PORT}/approve?token=${APPROVAL_TOKEN}   （同一Wi-Fi）"
echo "  デモ運転席      : http://localhost:${API_PORT}/ops?token=${APPROVAL_TOKEN}"
echo "  ※ 承認・注入・リセットは上記 token 付きURLから開いた画面のみ実行可能"
echo ""
echo "  デモ手順: /ops で ①リセット → ②複合障害を注入 → ③申告→調査開始"
echo "  停止:     ./demo.sh stop"
