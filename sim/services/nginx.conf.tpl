# 受注サービス（order.example.com）。__PREFIX__ は t-/v- に置換される。
pid /run/netwalker/__PREFIX__nginx.pid;
worker_processes 1;
error_log /run/netwalker/__PREFIX__nginx-error.log warn;

events { worker_connections 64; }

http {
  access_log /run/netwalker/__PREFIX__nginx-access.log;
  default_type text/html;

  server {
    listen 10.0.100.10:443 ssl;
    server_name order.example.com;
    ssl_certificate     /etc/netwalker/certs/server.crt;
    ssl_certificate_key /etc/netwalker/certs/server.key;

    # 受注画面（業務テストは 200 + マーカー文字列を期待する）
    location / {
      return 200 '<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>受注管理システム</title></head><body><h1>受注管理システム</h1><p>本日の受注一覧を表示しています。</p><ul><li>注文 #10241 — 部品A ×120</li><li>注文 #10242 — 部品B ×40</li></ul><!-- NETWALKER-ORDER-OK env=__PREFIX__ --></body></html>';
    }

    location /api/health {
      default_type application/json;
      return 200 '{"service":"order","status":"ok","marker":"NETWALKER-ORDER-OK","env":"__PREFIX__"}';
    }
  }
}
