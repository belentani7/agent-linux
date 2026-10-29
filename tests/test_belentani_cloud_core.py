import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import belentani_cloud_core as core


class TestCloudCore(unittest.TestCase):
    def test_catalog(self):
        assert len(core.catalog()) == 8
        assert all(x["repo"].startswith("https://") for x in core.catalog())

    def test_cost_estimation(self):
        self.assertEqual(core.estimate_cost(10, .34, 5, .2)["estimated_total_usd"], "4.40")
        with self.assertRaises(ValueError):
            core.estimate_cost(-1, .34)
        with self.assertRaises(ValueError):
            core.estimate_cost(float("nan"), .34)

    def test_music_preview_sends_no_request(self):
        with patch.dict(os.environ, {"BELENTANI_GPU_SUBMIT_ENABLED": "0"}):
            with patch.object(core, "_json_api", side_effect=AssertionError("network")):
                got = core.create_music("original dance pop", "my own lyrics", 40, 128)
        self.assertEqual(got["status"], "dry-run")

    def test_music_invalid_inputs(self):
        for data in [{"prompt": ""}, {"prompt": "x", "duration_s": 3},
                     {"prompt": "x", "bpm": 900}]:
            with self.assertRaises(ValueError):
                core.create_music(**data)

    def test_loopback_only(self):
        for url in ["http://example.com", "http://127.0.0.1.evil.com", "https://127.0.0.1:80",
                    "http://127.0.0.1:8188/path", "http://u:p@127.0.0.1:8188"]:
            with patch.dict(os.environ, {"BELENTANI_COMFY_URL": url}):
                with self.assertRaises(ValueError):
                    core._loopback_url("BELENTANI_COMFY_URL", "http://127.0.0.1:8188")

    def test_gpu_budget_gate(self):
        with patch.dict(os.environ, {"BELENTANI_GPU_RATE_USD_H": "1.00",
                                    "BELENTANI_GPU_MAX_ESTIMATED_USD": "0.10"}):
            with self.assertRaises(ValueError):
                core._submission_gate(.5)
            self.assertEqual(core._submission_gate(.05)["estimated_usd"], "0.05")

    def test_comfy_dryrun_valid_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "good.json").write_text('{"1":{"class_type":"EmptyLatentImage"}}')
            with patch.dict(os.environ, {"BELENTANI_WORKFLOW_DIR": tmp,
                                        "BELENTANI_GPU_SUBMIT_ENABLED": "0"}):
                with patch.object(core, "_json_api", side_effect=AssertionError("network")):
                    result = core.submit_video("good.json")
                self.assertEqual(result["status"], "dry-run")
                with self.assertRaises(ValueError):
                    core.submit_video("../../secrets.json")
                with self.assertRaises(ValueError):
                    core.submit_video("missing.json")

    def test_comfy_submit_with_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "graph.json").write_text('{"1":{"class_type":"CheckpointLoaderSimple"}}')
            env = {"BELENTANI_WORKFLOW_DIR": tmp, "BELENTANI_GPU_SUBMIT_ENABLED": "1",
                   "BELENTANI_GPU_RATE_USD_H": "0.50", "BELENTANI_GPU_MAX_ESTIMATED_USD": "1.00"}
            with patch.dict(os.environ, env):
                with patch.object(core, "_json_api", return_value={"prompt_id": "test-id"}) as mock:
                    result = core.submit_video("graph.json", .2)
            self.assertEqual(result["status"], "submitted")
            self.assertEqual(result["estimated_usd"], "0.10")
            self.assertEqual(mock.call_args.args[0], "http://127.0.0.1:8188/prompt")

    def test_bad_uuid_rejected(self):
        with self.assertRaises(ValueError):
            core.video_status("../../bad")


if __name__ == "__main__":
    unittest.main()
