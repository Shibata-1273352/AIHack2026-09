"""Run with: python -m unittest test_demo_reset -v (no simulator required)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import db, runtime
from app.config import settings
from app.main import app


class DemoResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = settings.data_dir
        settings.data_dir = Path(self.temp.name)
        if db._conn:
            db._conn.close()
        db._conn = None
        runtime.workers.clear()
        self.client = TestClient(app)
        db.save_incident({"id": "old", "created_at": "2026-09-21T00:00:00",
                          "status": "AWAITING_APPROVAL"})
        db.add_record("old", "evidence", {"summary": "retained evidence"})

    def tearDown(self):
        db._conn.close()
        db._conn = None
        settings.data_dir = self.old_dir
        runtime.workers.clear()
        self.temp.cleanup()

    def test_reset_clears_current_but_preserves_history_and_rejects_old_approval(self):
        with patch("app.main.scenario.reset", return_value={"reset": True}):
            self.assertEqual(self.client.post("/api/demo/reset").status_code, 200)
        self.assertIsNone(self.client.get("/api/incidents/latest").json()["incident"])
        self.assertEqual(db.list_records("old", "evidence")[0]["summary"], "retained evidence")
        self.assertIsNotNone(db.load_incident("old"))
        response = self.client.post("/api/incidents/old/approval", json={
            "plan_id": "old-plan", "plan_hash": "old-hash", "decision": "approve", "approver": "demo"})
        self.assertEqual(response.status_code, 409)
        # Reconnect/restart still sees no active incident.
        db._conn.close()
        db._conn = None
        self.assertIsNone(db.latest_incident())
        with patch("app.main.agent.start_investigation"):
            self.assertEqual(self.client.post("/api/incidents", json={}).status_code, 200)
        self.assertNotEqual(db.latest_incident()["id"], "old")
        self.assertEqual(self.client.post("/api/incidents", json={}).status_code, 409)

    def test_reset_and_inject_refused_during_worker(self):
        runtime.workers.add("old")
        with patch("app.main.scenario.reset") as reset:
            self.assertEqual(self.client.post("/api/demo/reset").status_code, 409)
            reset.assert_not_called()
        self.assertEqual(self.client.post("/api/demo/inject", json={"fault": "both"}).status_code, 409)
        self.assertEqual(db.latest_incident()["id"], "old")

    def test_failed_reset_keeps_case(self):
        with patch("app.main.scenario.reset", side_effect=RuntimeError("sim unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post("/api/demo/reset")
        self.assertEqual(db.latest_incident()["id"], "old")

    def test_worker_releases_on_error(self):
        runtime.workers.add("old")
        def fails():
            raise RuntimeError("failed")
        with self.assertRaises(RuntimeError):
            runtime.run_worker("old", fails)
        self.assertFalse(runtime.workers)


if __name__ == "__main__":
    unittest.main()
