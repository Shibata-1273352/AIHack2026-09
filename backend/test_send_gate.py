"""Run with: python -m unittest test_send_gate -v (no simulator / no API key required).

送信ゲート（T-13/T-19）: external_allowed 以外の data_class を持つデータは
モード・キー有無に関わらずプロバイダ呼出前に遮断され、違反が監査記録される。
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app.config import settings
from app.llm.gateway import ModelGateway, SendPolicyViolation


class SendGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = settings.data_dir
        settings.data_dir = Path(self.temp.name)
        if db._conn:
            db._conn.close()
        db._conn = None
        self.gateway = ModelGateway()

    def tearDown(self):
        if db._conn:
            db._conn.close()
        db._conn = None
        settings.data_dir = self.old_dir
        self.temp.cleanup()

    def _call(self, data_class: str):
        return self.gateway.call(
            "inc-test", "gate-check", "decide",
            system="s", user="u", data_class=data_class)

    def test_local_only_is_blocked_before_any_provider_call(self):
        for mode in ("mock", "record", "live"):
            with self.subTest(mode=mode):
                self.gateway.mode = mode
                with patch("app.llm.gateway.OrcaRouterClient") as client:
                    with self.assertRaises(SendPolicyViolation):
                        self._call("local_only")
                    client.assert_not_called()

    def test_violation_is_recorded_as_model_run(self):
        with self.assertRaises(SendPolicyViolation):
            self._call("local_only")
        runs = db.list_records("inc-test", "model_run")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["outcome"], "send_policy_violation")
        self.assertIn("local_only", runs[0]["error"])

    def test_unknown_class_is_blocked_too(self):
        # 許可リスト方式: external_allowed 以外（未知の値・タイポ含む）は全て遮断
        with self.assertRaises(SendPolicyViolation):
            self._call("confidential")

    def test_external_allowed_passes_gate(self):
        # ゲート通過後は通常経路（mock）で応答が返る
        self.gateway.mode = "mock"
        resp = self.gateway.call("inc-test", "gate-ok", "decide",
                                 system="s", user="u",
                                 data_class="external_allowed")
        self.assertEqual(resp.outcome, "mock")


if __name__ == "__main__":
    unittest.main()
