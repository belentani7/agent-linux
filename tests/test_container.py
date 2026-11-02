"""Portable source tests: container CI must still build and run the image."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ContainerGuards(unittest.TestCase):
    def test_dockerfile_nonroot_and_no_remote_install_pipe(self):
        src = (ROOT / "Dockerfile.rootless").read_text()
        self.assertIn("FROM ubuntu:26.04", src)
        self.assertIn("USER agent:agent", src)
        self.assertIn('ENTRYPOINT ["/usr/bin/tini", "--"]', src)
        self.assertNotIn("| bash", src)
        self.assertNotIn("| sh", src)

    def test_devcontainer_user_and_capabilities(self):
        cfg = json.loads((ROOT / ".devcontainer/rootless/devcontainer.json").read_text())
        self.assertEqual("agent", cfg["remoteUser"])
        self.assertEqual("agent", cfg["containerUser"])
        self.assertIn("--cap-drop=ALL", cfg["runArgs"])
        self.assertIn("--security-opt=no-new-privileges", cfg["runArgs"])

    def test_ci_build_and_rootless_smoke(self):
        ci = (ROOT / ".github/workflows/container.yml").read_text()
        self.assertIn("docker build", ci)
        self.assertIn("--network none", ci)
        self.assertIn("--read-only", ci)
        self.assertIn("scripts/container-smoke.sh", ci)
        smoke = (ROOT / "scripts/container-smoke.sh").read_text()
        self.assertIn("set -Eeuo pipefail", smoke)
        self.assertIn('id -u', smoke)
