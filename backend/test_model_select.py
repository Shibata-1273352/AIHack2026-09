"""Run with: python -m unittest test_model_select -v (no simulator / no API key required).

画面からのモデル切替（S8-5）の安全策を検証する。

- 選べるのは**構造化出力の実タスク検証に合格したモデルだけ**。
  未検証モデルを API 直叩きで指定しても 422 で拒否する
  （構造化出力に非対応のモデルは 400 を返し、400 は再試行不可なので調査が落ちる）
- 調査・適用の処理中は 409（走っている推論の方式を途中で変えない）
- 変更系APIなので操作トークンが要る（未設定時は開発モード）
- 上書きは**メモリのみ・永続化しない**（A/B/R 比較は別プロセスなので混入しない）
"""
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import db, runtime
from app.config import settings
from app.llm.route_policy import policy
from app.main import app


class ModelSelectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = settings.data_dir
        settings.data_dir = Path(self.temp.name)
        if db._conn:
            db._conn.close()
        db._conn = None
        runtime.workers.clear()
        policy.set_override(None)
        self.client = TestClient(app)

    def tearDown(self):
        if db._conn:
            db._conn.close()
        db._conn = None
        settings.data_dir = self.old_dir
        settings.approval_token = None
        runtime.workers.clear()
        policy.set_override(None)
        self.temp.cleanup()

    # ---------------------------------------------------------------- 選択肢

    def test_options_only_contain_verified_structured_output_models(self):
        body = self.client.get("/api/models").json()
        self.assertTrue(body["options"], "選択肢が空")
        for option in body["options"]:
            self.assertTrue(policy.supports_json_schema(option["model"]),
                            f"未検証のモデルが選択肢に出ている: {option['model']}")
            # 単価はサーバが返す（フロントにハードコードしない）
            self.assertIn("pricing", option)
        self.assertIsNone(body["current"])
        self.assertEqual(body["default"], policy.resolve("decide").routes[0])

    # ---------------------------------------------------------------- 拒否

    def test_unverified_model_is_rejected(self):
        # 実タスク検証に不合格だったモデルを直接指定しても通さない
        response = self.client.post("/api/models/select",
                                    json={"model": "z-ai/glm-5.3-flash"})
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(policy.current_override())

    def test_unknown_model_is_rejected(self):
        response = self.client.post("/api/models/select",
                                    json={"model": "vendor/does-not-exist"})
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(policy.current_override())

    def test_rejected_while_workers_are_running(self):
        runtime.workers.add("inc-running")
        chosen = self._first_selectable()
        response = self.client.post("/api/models/select", json={"model": chosen})
        self.assertEqual(response.status_code, 409)
        self.assertIsNone(policy.current_override())
        self.assertTrue(self.client.get("/api/models").json()["locked"])

    def test_requires_token_when_configured(self):
        settings.approval_token = SecretStr("secret-token")
        chosen = self._first_selectable()
        self.assertEqual(
            self.client.post("/api/models/select", json={"model": chosen}).status_code, 403)
        self.assertIsNone(policy.current_override())
        ok = self.client.post("/api/models/select", json={"model": chosen},
                              headers={"X-Netwalker-Token": "secret-token"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(policy.current_override(), chosen)

    # ---------------------------------------------------------------- 反映

    def test_selection_changes_resolved_routes_and_is_recorded_as_override(self):
        chosen = self._first_selectable()
        self.assertEqual(
            self.client.post("/api/models/select", json={"model": chosen}).status_code, 200)
        profile = policy.resolve("decide")
        self.assertEqual(profile.routes, [chosen])
        # 案件に「設定どおりか、画面からの選択か」を刻めるよう出所が分かること
        self.assertEqual(profile.source, "override")
        # decide 以外のプロファイルは巻き込まない
        self.assertEqual(policy.resolve("vlm").source, "policy")

    def test_selection_can_be_cleared_back_to_policy(self):
        chosen = self._first_selectable()
        self.client.post("/api/models/select", json={"model": chosen})
        self.assertEqual(
            self.client.post("/api/models/select", json={"model": None}).status_code, 200)
        self.assertIsNone(policy.current_override())
        self.assertEqual(policy.resolve("decide").source, "policy")

    def test_override_is_not_persisted(self):
        """上書きは設定ファイルへ書き戻さない（A/B/R の実測へ混入させないため）。"""
        from app.llm.route_policy import POLICY_PATH, RoutePolicy
        before = POLICY_PATH.read_text(encoding="utf-8")
        chosen = self._first_selectable()
        self.client.post("/api/models/select", json={"model": chosen})
        self.assertEqual(POLICY_PATH.read_text(encoding="utf-8"), before)
        # 別プロセス相当（読み直し）では上書きが見えない
        self.assertIsNone(RoutePolicy().current_override())

    # ---------------------------------------------------------------- helper

    def _first_selectable(self) -> str:
        options = self.client.get("/api/models").json()["options"]
        self.assertTrue(options, "選択肢が空")
        return options[0]["model"]


if __name__ == "__main__":
    unittest.main()
