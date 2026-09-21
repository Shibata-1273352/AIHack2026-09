"""Run with: python -m unittest test_handoff -v (no simulator / no API key required).

却下からの復帰（M-12 / §14.3）を検証する。

却下すると担当者対応待ちで止まるが、そこで画面が行き止まりになると
4分の発表で却下を実演した瞬間に詰む。却下は失敗ではなく**正常な安全動作**なので、
「何も変更していない」ことを明示したうえで次へ進む道が要る。

- 却下で**引き継ぎレコードが起票**され、却下者・理由・証拠・計画への参照が残る
- 引き継ぎの**受領／保留が記録**される（§14.3）
- **障害状態はそのままに**調べ直せる（sim をリセットしないので実演を続けられる）
- 却下理由は人間向けの記録・表示のみ（LLM の履歴には入れない）
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import approval, db, incident, runtime
from app.config import settings
from app.main import app

PLAN_BODY = {"action": "delete_nft_rule", "node": "r2", "table": "fw",
             "chain": "forward", "rule_comment": "BAD-ACL-443"}


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = settings.data_dir
        settings.data_dir = Path(self.temp.name)
        if db._conn:
            db._conn.close()
        db._conn = None
        runtime.workers.clear()
        self.client = TestClient(app)

        self.inc = incident.create("受注画面が開かない", "拠点A", "受注業務",
                                   "拠点担当者", mode="scripted")
        self.plan = db.add_record(self.inc["id"], "plan", {
            "version": 1, "hash": approval.plan_hash(PLAN_BODY),
            "title": "予備経路r2の誤設定ACLルールを1件削除",
            "title_plain": "予備回線ルータから、業務通信を止めているルールを1件だけ削除します",
            "body": PLAN_BODY, "status": "validated"})
        db.add_record(self.inc["id"], "evidence", {"tool": "observe_node", "summary": "x"})
        db.add_record(self.inc["id"], "hypothesis", {"text": "h", "status": "supported"})
        self.ap = approval.create_request(self.inc["id"], self.plan)

    def tearDown(self):
        if db._conn:
            db._conn.close()
        db._conn = None
        settings.data_dir = self.old_dir
        runtime.workers.clear()
        self.temp.cleanup()

    def _reject(self, reason="メンテナンス時間外のため"):
        return self.client.post(f"/api/incidents/{self.inc['id']}/approval", json={
            "plan_id": self.plan["id"], "plan_hash": self.plan["hash"],
            "decision": "reject", "approver": "田中（変更承認権限）", "reason": reason})

    # ---------------------------------------------------------------- 却下

    def test_rejection_opens_handoff_and_stops_safely(self):
        self.assertEqual(self._reject().status_code, 200)

        current = db.load_incident(self.inc["id"])
        self.assertEqual(current["status"], "NEEDS_HUMAN")
        # 画面見出しは平易層。対象環境を変更していないことを明示する
        self.assertIn("変更していません", current["current_activity"])

        handoffs = db.list_records(self.inc["id"], "handoff")
        self.assertEqual(len(handoffs), 1)
        rec = handoffs[0]
        self.assertEqual(rec["status"], "open")
        self.assertEqual(rec["trigger"], "approval_rejected")
        self.assertEqual(rec["rejected_by"], "田中（変更承認権限）")
        self.assertEqual(rec["reason"], "メンテナンス時間外のため")
        # 担当交代後も再入力が要らないよう、証拠・仮説・計画への参照を持つ
        self.assertEqual(rec["plan_id"], self.plan["id"])
        self.assertEqual(len(rec["evidence_ids"]), 1)
        self.assertEqual(len(rec["hypothesis_ids"]), 1)
        self.assertTrue(rec["candidates"])

        # 却下では一切適用しない
        self.assertEqual(db.list_records(self.inc["id"], "execution"), [])

    def test_rejection_reason_is_optional(self):
        self.assertEqual(self._reject(reason="").status_code, 200)
        self.assertEqual(db.list_records(self.inc["id"], "handoff")[0]["reason"], "")

    def test_handoff_records_accept_and_hold(self):
        self._reject()
        for action, expected in (("accept", "accepted"), ("hold", "held")):
            response = self.client.post(f"/api/incidents/{self.inc['id']}/handoff",
                                        json={"action": action,
                                              "assignee": "ネットワーク運用担当",
                                              "note": "翌営業日に再検討"})
            self.assertEqual(response.status_code, 200)
            rec = db.list_records(self.inc["id"], "handoff")[-1]
            self.assertEqual(rec["status"], expected)
            self.assertEqual(rec["notes"][-1]["assignee"], "ネットワーク運用担当")

    def test_handoff_rejects_unknown_action(self):
        self._reject()
        response = self.client.post(f"/api/incidents/{self.inc['id']}/handoff",
                                    json={"action": "delete"})
        self.assertEqual(response.status_code, 422)

    # ---------------------------------------------------------------- 調べ直し

    def test_reinvestigate_starts_a_new_case_without_resetting_the_fault(self):
        self._reject()
        with patch("app.main.agent.start_investigation") as start, \
             patch("app.main.scenario.reset") as sim_reset:
            response = self.client.post(f"/api/incidents/{self.inc['id']}/reinvestigate")
            self.assertEqual(response.status_code, 200)
            start.assert_called_once()
            # 障害状態はそのまま。sim をリセットしないので実演を続けられる
            sim_reset.assert_not_called()

        new_id = response.json()["id"]
        self.assertNotEqual(new_id, self.inc["id"])
        self.assertEqual(db.latest_incident()["id"], new_id)
        self.assertEqual(db.load_incident(new_id)["reinvestigation_of"], self.inc["id"])
        # 却下した計画・証拠・引き継ぎは退避された案件に残る（履歴は消えない）
        self.assertEqual(len(db.list_records(self.inc["id"], "handoff")), 1)
        self.assertIsNotNone(db.load_incident(self.inc["id"]))

    def test_reinvestigate_refused_unless_needs_human(self):
        response = self.client.post(f"/api/incidents/{self.inc['id']}/reinvestigate")
        self.assertEqual(response.status_code, 409)   # まだ承認待ち
        self.assertEqual(db.latest_incident()["id"], self.inc["id"])

    def test_reinvestigate_refused_while_workers_are_running(self):
        self._reject()
        runtime.workers.add("busy")
        response = self.client.post(f"/api/incidents/{self.inc['id']}/reinvestigate")
        self.assertEqual(response.status_code, 409)

    def test_bundle_exposes_handoffs(self):
        self._reject()
        bundle = self.client.get("/api/incidents/latest").json()
        self.assertEqual(len(bundle["handoffs"]), 1)


if __name__ == "__main__":
    unittest.main()
