"""Offline security and control flow tests; no GitHub account or token is needed."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

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

    def test_reject_boolean_or_float_config_versions(self):
        for version in (True, 1.0, "1", None):
            with self.subTest(version=version):
                with self.assertRaises(runner.ConfigurationError):
                    runner.validate(valid(version=version))

    def test_cli_refuses_aliases_before_any_dispatch_or_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "config.json"
            report = root / "report.json"
            cursor = root / "cursor.json"
            original = json.dumps(valid())
            config.write_text(original, encoding="utf-8")
            cases = [
                ["--output", str(config)],
                ["--output", str(report), "--cursor", str(config), "--execute"],
                ["--output", str(report), "--cursor", str(report), "--execute"],
            ]
            if os.name == "posix":
                alias = root / "alias.json"
                alias.symlink_to(config)
                cases.append(["--output", str(alias)])
                hardlink = root / "hardlink.json"
                os.link(config, hardlink)
                cases.append(["--output", str(hardlink)])
            with mock.patch.object(runner, "dispatch", side_effect=AssertionError("dispatched")):
                for args in cases:
                    with self.subTest(args=args):
                        self.assertEqual(runner.main(["--config", str(config), *args]), 2)
                        self.assertEqual(config.read_text(encoding="utf-8"), original)
                        self.assertFalse(report.exists())
                        self.assertFalse(cursor.exists())

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

    def test_large_allowlist_cycling_across_runs_without_duplicate_first_batch(self):
        rows = [
            {"repository": f"example/real-{i}", "workflow": "ci.yml", "ref": "main"}
            for i in range(490)
        ]
        config = runner.validate(valid(repositories=rows, max_dispatches=5))
        self.assertEqual(len(config["repositories"]), 490)
        calls = []
        def fake(argv):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "false\n", "")
        first = runner.dispatch(config, execute=True, runner=fake)
        second = runner.dispatch(config, execute=True, runner=fake, start_index=first["cursor_after"])
        self.assertEqual(first["dispatches"], 5)
        self.assertEqual(second["dispatches"], 5)
        self.assertEqual(first["examined"], 5)
        self.assertEqual(first["cursor_after"], 5)
        self.assertEqual(second["cursor_after"], 10)
        first_visited = [item["repository"] for item in first["results"] if item["status"] == "dispatched_unverified"]
        second_visited = [item["repository"] for item in second["results"] if item["status"] == "dispatched_unverified"]
        self.assertEqual(first_visited, [f"example/real-{i}" for i in range(5)])
        self.assertEqual(second_visited, [f"example/real-{i}" for i in range(5, 10)])

    def test_probe_budget_skips_unavailable_repos_with_finite_calls(self):
        rows = [
            {"repository": f"example/archived-{i}", "workflow": "ci.yml", "ref": "main"}
            for i in range(40)
        ]
        config = runner.validate(valid(repositories=rows, max_dispatches=5))
        calls = []
        def unavailable(argv):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "true\n", "")
        result = runner.dispatch(config, execute=True, runner=unavailable)
        self.assertEqual(result["dispatches"], 0)
        self.assertEqual(result["examined"], runner.MAX_PROBES)
        self.assertEqual(result["cursor_after"], runner.MAX_PROBES)
        self.assertEqual(len(calls), runner.MAX_PROBES)
        self.assertEqual(result["results"][runner.MAX_PROBES]["status"], "probe_budget_exhausted")

    def test_cursor_rejects_changed_allowlist_and_corrupt_state(self):
        config = runner.validate(valid())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cursor.json"
            runner.write_report(path, {
                "fingerprint": runner.config_fingerprint(config), "next_index": 0,
            })
            self.assertEqual(runner.read_cursor(path, config), 0)
            changed = runner.validate(valid(repositories=[
                {**valid()["repositories"][0], "repository": "example/another"}]))
            self.assertEqual(runner.read_cursor(path, changed), 0)
            path.write_text("broken", encoding="utf-8")
            self.assertEqual(runner.read_cursor(path, config), 0)

    def test_no_dispatch_for_archived_repository(self):
        calls = []
        def fake(argv):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "true\n", "")
        result = runner.dispatch(runner.validate(valid()), execute=True, runner=fake)
        self.assertEqual(result["results"][0]["status"], "archived_or_unavailable")
        self.assertEqual(len(calls), 1)

    @unittest.skipUnless(os.name == "posix", "POSIX symlink semantics")
    def test_write_report_does_not_follow_predictable_temp_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            victim = root / "victim.txt"
            victim.write_text("keep private data intact", encoding="utf-8")
            report = root / "report.json"
            legacy_tmp = root / "report.json.tmp"
            legacy_tmp.symlink_to(victim)
            runner.write_report(report, {"status": "ok"})
            self.assertEqual(victim.read_text(encoding="utf-8"), "keep private data intact")
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")), {"status": "ok"})
            self.assertTrue(legacy_tmp.is_symlink())
            self.assertEqual(sorted(p.name for p in root.iterdir()),
                             ["report.json", "report.json.tmp", "victim.txt"])

    def test_write_report_preserves_existing_file_on_serialization_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = root / "report.json"
            runner.write_report(report, {"previous": True})
            with self.assertRaises(TypeError):
                runner.write_report(report, {"invalid": object()})
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")),
                             {"previous": True})
            self.assertEqual([p.name for p in root.iterdir()], ["report.json"])

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


if __name__ == "__main__":
    unittest.main()
