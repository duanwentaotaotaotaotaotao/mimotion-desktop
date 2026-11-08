import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import backend


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = {**backend.DEFAULTS, "USER": "demo@example.com", "PWD": "test-password",
                       "MIN_STEP": "12000", "MAX_STEP": "12000", "AES_KEY": "0123456789abcdef"}

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, config=None):
        config = config or self.config
        self.root.joinpath(".env").write_text("# preserved comment\n" + "\n".join(
            key + "=" + backend.quote_env(value) for key, value in config.items()) + "\n", encoding="utf-8")

    def test_config_roundtrip_special_password_and_backup(self):
        self.config["PWD"] = "p a'ss\\word${SECRET}"
        self.config["PUSH_PLUS_TOKEN"] = "preserve-this-token"
        self.seed()
        before = self.root.joinpath(".env").read_bytes()
        store = backend.ConfigStore(self.root)
        current = store.load()
        self.assertEqual(current["PWD"], self.config["PWD"])
        backup = store.save({"MIN_STEP": "13000", "MAX_STEP": "14000"})
        after = store.load()
        self.assertEqual(after["PWD"], self.config["PWD"])
        self.assertEqual(after["AES_KEY"], self.config["AES_KEY"])
        self.assertEqual(after["PUSH_PLUS_TOKEN"], "preserve-this-token")
        self.assertEqual(backup.read_bytes(), before)
        self.assertIn("# preserved comment", store.path.read_text(encoding="utf-8"))

    def test_concurrent_external_edit_is_not_overwritten(self):
        self.seed()
        store = backend.ConfigStore(self.root)
        store.load()
        self.root.joinpath(".env").write_text("# edited externally\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "其他程序"):
            store.save(self.config)
        self.assertEqual(self.root.joinpath(".env").read_text(encoding="utf-8"), "# edited externally\n")

    def test_config_json_is_kept_consistent(self):
        full = {**self.config, "OTHER_FLAG": "keep-me"}
        self.seed({"CONFIG": json.dumps(full), "AES_KEY": self.config["AES_KEY"]})
        store = backend.ConfigStore(self.root)
        store.load()
        store.save({"MIN_STEP": "7", "MAX_STEP": "9"})
        loaded = store.load()
        self.assertEqual(loaded["MIN_STEP"], "7")
        self.assertEqual(json.loads(loaded["CONFIG"])["MAX_STEP"], "9")
        self.assertEqual(loaded["OTHER_FLAG"], "keep-me")

    def test_invalid_parameters_do_not_reach_engine(self):
        for changes in ({"MIN_STEP": "-1"}, {"MIN_STEP": "99999", "MAX_STEP": "1"},
                        {"SLEEP_GAP": "nan"}, {"USER": "invalid"}, {"PWD": ""},
                        {"USER": "demo@example.com#other@example.com"}):
            with self.subTest(changes=list(changes)):
                with self.assertRaises(ValueError):
                    backend.validate_config({**self.config, **changes})

    def test_worker_uses_real_engine_with_fake_transport(self):
        self.seed()
        import util.zepp_helper as helper
        import util.push_util as push
        result_path = self.root / "result.json"
        with mock.patch.object(helper, "login_access_token", return_value=("access-secret", None)), \
             mock.patch.object(helper, "grant_login_tokens", return_value=("login-secret", "app-secret", "test-user-id", None)), \
             mock.patch.object(helper, "get_user_device_id", return_value="TESTDEVICE"), \
             mock.patch.object(helper, "post_fake_brand_data", return_value=(True, "success")) as post, \
             mock.patch.object(push, "push_results"):
            code = backend.run_worker(self.root, result_path)
        self.assertEqual(code, 0)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["results"][0]["success"])
        self.assertEqual(post.call_args.args[0], "12000")
        self.assertEqual(post.call_args.kwargs["device_id"], "TESTDEVICE")
        self.assertTrue(self.root.joinpath("encrypted_tokens.data").is_file())
        text = next(self.root.joinpath("logs").glob("*.log")).read_text(encoding="utf-8")
        self.assertNotIn("test-password", text)
        self.assertNotIn("demo@example.com", text)
        self.assertIn("成功：1，失败：0", text)

    def test_worker_failure_and_dynamic_token_redaction(self):
        self.seed()
        import util.zepp_helper as helper
        import util.push_util as push

        def failure(*args, **kwargs):
            print('grant_app_token: {"app_token":"never-save-this-token"}')
            raise RuntimeError("password=" + self.config["PWD"])

        with mock.patch.object(helper, "login_access_token", side_effect=failure), \
             mock.patch.object(push, "push_results"):
            code = backend.run_worker(self.root, self.root / "result.json")
        self.assertEqual(code, 1)
        log = backend.log_entries(self.root, self.config)[0]
        self.assertEqual(log["state"], "failed")
        self.assertNotIn("never-save-this-token", log["text"])
        self.assertNotIn("test-password", log["text"])
        self.assertIn("[已隐藏]", log["text"])

    def test_project_lock_rejects_second_runner(self):
        with backend.project_lock(self.root):
            with self.assertRaisesRegex(RuntimeError, "已有"):
                with backend.project_lock(self.root):
                    self.fail("lock did not stop second worker")

    def test_no_config_does_not_submit(self):
        with mock.patch.object(backend, "run_engine") as engine:
            code = backend.run_worker(self.root, self.root / "result.json")
        self.assertEqual(code, 1)
        engine.assert_not_called()

    def test_times_and_ps_quoting(self):
        self.assertEqual(backend.validate_times("18:30，08:00 08:00"), ["08:00", "18:30"])
        for invalid in ("", "25:00", "1:00", "08:00;Remove-Item anything"):
            with self.assertRaises(ValueError):
                backend.validate_times(invalid)
        self.assertEqual(backend.ps_quote("O'Brien"), "'O''Brien'")


if __name__ == "__main__":
    unittest.main(verbosity=2)
