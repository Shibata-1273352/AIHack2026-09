"""Run with: python -m unittest test_approval -v (no simulator / no API key required).

承認ゲート（M-09・T-06/T-07）の単体検証。サーバ側で版・ハッシュ・期限・
承認者・二重決定を照合し、いずれか外れたら適用に進ませないことを確認する。
"""
import tempfile
import time
import unittest
from pathlib import Path

from app import approval, db
from app.config import settings

PLAN_BODY = {"action": "delete_nft_rule", "node": "r2", "table": "fw",
             "chain": "forward", "rule_comment": "BAD-ACL-443"}


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = settings.data_dir
        settings.data_dir = Path(self.temp.name)
        if db._conn:
            db._conn.close()
        db._conn = None
        self.incident_id = "inc-approval-test"
        self.plan = db.add_record(self.incident_id, "plan", {
            "version": "1", "hash": approval.plan_hash(PLAN_BODY),
            "body": PLAN_BODY, "status": "validated"})
        self.ap = approval.create_request(self.incident_id, self.plan)

    def tearDown(self):
        if db._conn:
            db._conn.close()
        db._conn = None
        settings.data_dir = self.old_dir
        self.temp.cleanup()

    def _decide(self, **overrides):
        args = {"incident_id": self.incident_id, "plan_id": self.plan["id"],
                "plan_hash_from_client": self.plan["hash"],
                "decision": "approve", "approver": "承認者A"}
        args.update(overrides)
        return approval.decide(**args)

    # ---------------------------------------------------------------- 正常系

    def test_approve_records_decision_and_approver(self):
        ap = self._decide()
        self.assertEqual(ap["decision"], "approved")
        self.assertEqual(ap["approver"], "承認者A")
        self.assertIsNotNone(ap["decided_at"])

    def test_reject_is_recorded_as_rejected(self):
        self.assertEqual(self._decide(decision="reject")["decision"], "rejected")

    # ---------------------------------------------------------------- T-06/T-07

    def test_hash_mismatch_is_refused(self):
        # 計画が差し替わった／古い画面から送られた場合
        with self.assertRaises(PermissionError):
            self._decide(plan_hash_from_client="0000000000000000")
        self.assertEqual(approval.pending_approval(self.incident_id)["decision"], "pending")

    def test_other_plan_id_is_refused(self):
        with self.assertRaises(PermissionError):
            self._decide(plan_id="pl-somethingelse")

    def test_expired_request_is_refused_and_marked_expired(self):
        self.ap["expires_epoch"] = time.time() - 1
        db.update_record(self.ap["id"], self.ap)
        with self.assertRaises(PermissionError):
            self._decide()
        # 期限切れは pending のまま放置せず expired として確定させる
        self.assertEqual(db.list_records(self.incident_id, "approval")[-1]["decision"], "expired")
        self.assertIsNone(approval.pending_approval(self.incident_id))

    def test_second_decision_is_refused(self):
        # 連打・二重承認（同じ依頼を2回決定させない）
        self._decide()
        with self.assertRaises(PermissionError):
            self._decide()

    def test_empty_approver_is_refused(self):
        with self.assertRaises(PermissionError):
            self._decide(approver="   ")

    def test_invalid_decision_value_is_refused(self):
        with self.assertRaises(ValueError):
            self._decide(decision="maybe")

    # ---------------------------------------------------------------- ハッシュ

    def test_plan_hash_is_stable_and_content_sensitive(self):
        # キー順に依存せず、内容が変われば必ず変わる
        reordered = dict(reversed(list(PLAN_BODY.items())))
        self.assertEqual(approval.plan_hash(PLAN_BODY), approval.plan_hash(reordered))
        tampered = {**PLAN_BODY, "rule_comment": "POLICY-DENY-TELNET"}
        self.assertNotEqual(approval.plan_hash(PLAN_BODY), approval.plan_hash(tampered))


if __name__ == "__main__":
    unittest.main()
