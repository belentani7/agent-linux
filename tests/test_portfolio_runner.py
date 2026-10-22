"""Offline security and control flow tests; no GitHub account or token is needed."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "portfolio_runner.py"
spec = importlib.util.spec_from_file_location("portfolio_runner", SOURCE)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(runner)


def valid(**overrides):
    data = {"version": 1, "enabled": True, "max_dispatches": 2,
            "repositories": [{"repository": "example/real-project",
                              "workflow": "ci.yml", "ref": "main"}]}
    return {**data, **overrides}


class PortfolioRunnerTests(unittest.TestCase):
    def test_config_is_fail_closed(self):
        self.assertEqual(runner.validate(valid())["max_dispatches"], 2)
        with self.assertRaises(runner.ConfigurationError):
            runner.validate(valid(enabled="yes"))
        with self.assertRaises(runner.ConfigurationError):
            runner.validate(valid(max_dispatches=500))
        with self.assertRaises(runner.ConfigurationError):
            runner.validate({**valid(), "remote_command": "rm -rf /"})

    def test_reject_injection_and_cross_repository_ambiguity(self):
        for patch in (
            {"repository": "example/x;echo BAD"},
            {"repository": "-option/repo"},
            {"workflow": "../deploy.yml"},
            {"workflow": "ci.yml --ref other"},
            {"ref": "-main"},
            {"ref": "main..evil"},
            {"ref": "heads//main"},
        ):
            entry = {**valid()["repositories"][0], **patch}
            with self.subTest(patch=patch):
                with self.assertRaises(runner.ConfigurationError):
                    runner.validate(valid(repositories=[entry]))
        row = valid()["repositories"][0]
        with self.assertRaises(runner.ConfigurationError):
            runner.validate(valid(repositories=[row, row]))

    def test_dry_run_never_calls_gh(self):
        calls = []
        def fake(argv):
            calls.append(argv)
            raise AssertionError("Dry-run touched the network")
        result = runner.dispatch(runner.validate(valid()), execute=False, runner=fake)
        self.assertEqual(calls, [])
        self.assertEqual(result["dispatches"], 0)
        self.assertEqual(result["results"][0]["status"], "dry_run")
        disabled = runner.dispatch(runner.validate(valid(enabled=False)), execute=True, runner=fake)
        self.assertEqual(disabled["results"][0]["status"], "disabled")

    def test_execute_only_existing_nonarchived_workflows_with_budget(self):
        data = valid(repositories=[
            {"repository": f"example/repo-{n}", "workflow": "ci.yml", "ref": "main"}
            for n in range(4)
        ], max_dispatches=2)
        calls = []
        def fake(argv):
            calls.append(argv)
            if len(argv) >= 5 and argv[1] == "api" and argv[-2:] == ["--jq", ".archived"]:
                return subprocess.CompletedProcess(argv, 0, "false\n", "")
            return subprocess.CompletedProcess(argv, 0, "{}\n", "")
        result = runner.dispatch(runner.validate(data), execute=True, runner=fake)
        self.assertEqual(result["dispatches"], 2)
        self.assertEqual([x["status"] for x in result["results"]],
                         ["dispatched_unverified", "dispatched_unverified",
                          "budget_exhausted", "budget_exhausted"])
        dispatches = [x for x in calls if x[1:3] == ["workflow", "run"]]
        self.assertEqual(len(dispatches), 2)
        self.assertTrue(all(x[0] == "gh" and x[-2:] == ["--ref", "main"] for x in dispatches))

    def test_no_dispatch_for_archived_repository(self):
        calls = []
        def fake(argv):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "true\n", "")
        result = runner.dispatch(runner.validate(valid()), execute=True, runner=fake)
        self.assertEqual(result["results"][0]["status"], "archived_or_unavailable")
        self.assertEqual(len(calls), 1)

    def test_restricted_report_and_offline_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = root / "config.json"
            report = root / "result.json"
            cfg.write_text(json.dumps(valid(enabled=False)), encoding="utf-8")
            self.assertEqual(runner.main(["--validate", "--config", str(cfg)]), 0)
            self.assertEqual(runner.main(["--execute", "--config", str(cfg)]), 2)
            self.assertEqual(runner.main(["--config", str(cfg), "--output", str(report)]), 0)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "dry_run")
            self.assertEqual(data["dispatches"], 0)
            if os.name == "posix":
                self.assertEqual(report.stat().st_mode & 0o777, 0o600)


    def test_rotation_prevents_starvation_with_small_dispatch_budget(self):
        data = valid(repositories=[
            {"repository": f"example/repo-{n}", "workflow": "ci.yml", "ref": "main"}
            for n in range(5)
        ], max_dispatches=2)
        def fake(argv):
            if argv[1] == "api" and argv[-2:] == ["--jq", ".archived"]:
                return subprocess.CompletedProcess(argv, 0, "false\n", "")
            return subprocess.CompletedProcess(argv, 0, "{}\n", "")
        config = runner.validate(data)
        first = runner.dispatch(config, execute=True, runner=fake)
        second = runner.dispatch(config, execute=True, runner=fake, start_index=first["next_index"])
        third = runner.dispatch(config, execute=True, runner=fake, start_index=second["next_index"])
        self.assertEqual(first["next_index"], 2)
        self.assertEqual(second["next_index"], 4)
        self.assertEqual(third["next_index"], 1)
        self.assertEqual([x["repository"] for x in first["results"][:2]],
                         ["example/repo-0", "example/repo-1"])
        self.assertEqual([x["repository"] for x in second["results"][:2]],
                         ["example/repo-2", "example/repo-3"])
        self.assertEqual(third["results"][0]["repository"], "example/repo-4")

    def test_cursor_is_private_persistent_and_config_sensitive(self):
        config = runner.validate(valid())
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "cursor.json"
            self.assertEqual(runner.load_cursor(state, config), 0)
            runner.write_report(state, {"version": 1, "targets_sha256": runner.targets_hash(config),
                                        "next_index": 0})
            self.assertEqual(runner.load_cursor(state, config), 0)
            changed = runner.validate(valid(repositories=[
                {"repository": "example/another", "workflow": "ci.yml", "ref": "main"}
            ]))
            self.assertEqual(runner.load_cursor(state, changed), 0)
            runner.write_report(state, {"version": 1, "targets_sha256": runner.targets_hash(config),
                                        "next_index": True})
            with self.assertRaises(runner.ConfigurationError):
                runner.load_cursor(state, config)
            if os.name == "posix":
                self.assertEqual(state.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
