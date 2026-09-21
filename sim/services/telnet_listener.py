#!/usr/bin/env python3
"""10.0.100.10:23 で待ち受けるダミーtelnetリスナ。

サービス自体は生きているのに ACL で遮断されている、という状態を
証明するために置く（禁止通信テストの根拠）。
"""

import socket
import sys

HOST, PORT = "10.0.100.10", 23


def main() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(4)
    print(f"telnet listener on {HOST}:{PORT}", flush=True)
    while True:
        try:
            conn, _addr = srv.accept()
            conn.sendall(b"NETWALKER-TELNET (this port must be blocked by policy)\r\n")
            conn.close()
        except Exception as exc:  # noqa: BLE001
            print(f"telnet listener error: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
