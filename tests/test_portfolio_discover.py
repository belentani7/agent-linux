"""Offline manifest-discovery tests; no access to GitHub or API tokens."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("portfolio_discover", ROOT / "scripts" / "portfolio_discover.py")
assert spec and spec.loader
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


def repo(index: int, archived: bool = False) -> dict:
    return {
        "full_name": f"belentani7/existing-{index}",
        "archived": archived,
        "default_branch": "main",
        "pushed_at": f"2026-10-{(index % 28) + 1:02d}T11:00:00Z",
    }


class ManifestTests(unittest.TestCase):
    def test_490_rows_become_disabled_config_without_any_remote_actions(self):
        lines = "\n".join(json.dumps(repo(i)) for i in range(490))
        config, stats = discovery.build_manifest(lines, "belentani7", "ci.yml")
        self.assertEqual(len(config["repositories"]), 490)
        self.assertEqual(config["enabled"], False)
        self.assertEqual(config["max_dispatches"], 5)
        self.assertEqual(stats["active"], 490)
        self.assertTrue(all(row["workflow"] == "ci.yml" for row in config["repositories"]))
        self.assertTrue(all(row["ref"] == "main" for row in config["repositories"]))

    def test_archived_skipped_and_oldest_pushed_first(self):
        rows = [
            {**repo(1), "pushed_at": "2026-10-20T00:00:00Z"},
            {**repo(2), "archived": True},
            {**repo(3), "pushed_at": "2025-03-01T00:00:00Z"},
            {"full_name": "another-user/outside", "archived": False,
             "default_branch": "main", "pushed_at": "2020-01-01T00:00:00Z"},
        ]
        config, stats = discovery.build_manifest("\n".join(map(json.dumps, rows)), "belentani7", "build.yml")
        self.assertEqual([v["repository"] for v in config["repositories"]],
                         ["belentani7/existing-3", "belentani7/existing-1"])
        self.assertEqual(stats["archived_excluded"], 1)

    def test_invalid_branch_duplicate_and_untrusted_metadata_fail_closed(self):
        rows = [repo(1), {**repo(2), "default_branch": "bad..ref"}]
        with self.assertRaises(discovery.ConfigurationError):
            discovery.build_manifest("\n".join(map(json.dumps, rows)), "belentani7", "ci.yml")
        with self.assertRaises(discovery.ConfigurationError):
            discovery.build_manifest("\n".join(map(json.dumps, [repo(1), repo(1)])), "belentani7", "ci.yml")
        with self.assertRaises(discovery.ConfigurationError):
            discovery.build_manifest(json.dumps({**repo(1), "archived": None}), "belentani7", "ci.yml")
        with self.assertRaises(discovery.ConfigurationError):
            discovery.build_manifest("invalid json", "belentani7", "ci.yml")
        with self.assertRaises(discovery.ConfigurationError):
            discovery.build_manifest("{}", "--bad-owner", "ci.yml")


if __name__ == "__main__":
    unittest.main()
