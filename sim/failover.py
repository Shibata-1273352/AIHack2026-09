#!/usr/bin/env python3
"""冗長化制御デーモン（AIの修正操作とは独立、§7.2）。

拠点GWの主回線側リンク（eth-r1）の operstate を 1 秒周期で監視し、
3 回連続 down で予備経路（r2）へネクストホップを切り替える。
srv 側の戻り経路も同時に切り替える（往復経路の確認、§7.2）。
復旧を 3 回連続で確認したら主回線へ戻す。

対象環境（t-）専用。検証用環境（v-）ではデーモンを動かさず、
クローン時に経路状態をリプレイする。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

POLL_SEC = 1.0
THRESHOLD = 3  # 3回連続で切替（§7.2 検知・収束）

RUN = Path("/run/netwalker")


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=5)


def link_is_up(prefix: str) -> bool | None:
    """gw から見た主回線リンクの状態。DOWN/LOWERLAYERDOWN は down 扱い。"""
    r = sh(["ip", "-n", f"{prefix}gw", "-j", "link", "show", "eth-r1"])
    if r.returncode != 0:
        return None  # netns 再作成中など。判定不能
    try:
        data = json.loads(r.stdout)[0]
    except (json.JSONDecodeError, IndexError):
        return None
    # operstate: UP / DOWN / LOWERLAYERDOWN / UNKNOWN
    return data.get("operstate") == "UP"


def switch_to(prefix: str, path: str) -> None:
    if path == "r2":
        sh(["ip", "-n", f"{prefix}gw", "route", "replace",
            "10.0.100.10/32", "via", "10.0.3.2", "dev", "eth-r2"])
        sh(["ip", "-n", f"{prefix}srv", "route", "replace",
            "10.0.1.0/24", "via", "10.0.5.1", "dev", "eth-r2"])
    else:
        sh(["ip", "-n", f"{prefix}gw", "route", "replace",
            "10.0.100.10/32", "via", "10.0.2.2", "dev", "eth-r1"])
        sh(["ip", "-n", f"{prefix}srv", "route", "replace",
            "10.0.1.0/24", "via", "10.0.4.1", "dev", "eth-r1"])


def main() -> None:
    prefix = sys.argv[1] if len(sys.argv) > 1 else "t-"
    if prefix != "t-":
        print(f"failover daemon is for t- only, got {prefix}", file=sys.stderr)
        sys.exit(1)

    RUN.mkdir(parents=True, exist_ok=True)
    state_file = RUN / f"{prefix}failover.json"
    log_file = RUN / f"{prefix}failover.log"

    active = "r1"
    down_count = 0
    up_count = 0
    history: list[dict] = []

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        with log_file.open("a") as f:
            f.write(line + "\n")

    def save() -> None:
        state_file.write_text(json.dumps({
            "active_path": active,
            "primary_link_up": down_count == 0,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "history": history[-20:],
        }, ensure_ascii=False))

    log(f"failover daemon start (poll={POLL_SEC}s, threshold={THRESHOLD})")
    save()

    while True:
        up = link_is_up(prefix)
        if up is None:
            # 環境再作成中。状態を初期化して追従する
            active = "r1"
            down_count = up_count = 0
            time.sleep(POLL_SEC)
            continue

        if not up:
            down_count += 1
            up_count = 0
            if down_count == THRESHOLD and active == "r1":
                switch_to(prefix, "r2")
                active = "r2"
                history.append({"at": time.strftime("%H:%M:%S"),
                                "event": "switch_to_backup",
                                "reason": f"eth-r1 down {THRESHOLD}回連続"})
                log("主回線リンク断を3回連続検知 → 予備経路(r2)へ切替")
                save()
        else:
            up_count += 1
            down_count = 0
            if up_count == THRESHOLD and active == "r2":
                switch_to(prefix, "r1")
                active = "r1"
                history.append({"at": time.strftime("%H:%M:%S"),
                                "event": "switch_to_primary",
                                "reason": f"eth-r1 up {THRESHOLD}回連続"})
                log("主回線リンク復旧を3回連続確認 → 主回線(r1)へ復帰")
                save()

        # 常時 state を更新（UI の鮮度確認用）
        save()
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
