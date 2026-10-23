"""Offline, non-privileged checks of the opt-in Ubuntu update entrypoint."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'update.sh'


class UpdateSafetyTests(unittest.TestCase):
    def invoke(self, *args):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'privileged-command-ran'
            fake = Path(tmp) / 'sudo'
            fake.write_text('#!/bin/sh\nprintf called >> "$UPDATE_TEST_MARKER"\nexit 99\n')
            fake.chmod(0o755)
            env = os.environ.copy()
            env['PATH'] = tmp + os.pathsep + env.get('PATH', '')
            env['UPDATE_TEST_MARKER'] = str(marker)
            result = subprocess.run(['bash', str(SCRIPT), *args], env=env,
                                    text=True, capture_output=True, timeout=10)
            self.assertFalse(marker.exists(), 'A privileged command was invoked')
            return result

    def test_default_is_read_only(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('[dry-run]', result.stdout)
        self.assertIn('nothing executed', result.stdout)

    def test_explicit_dry_run_is_read_only(self):
        result = self.invoke('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('sudo apt-get upgrade', result.stdout)

    def test_reject_unknown_flags(self):
        result = self.invoke('--execute')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Unknown argument', result.stderr)

    def test_reject_conflicting_modes(self):
        for args in [('--apply', '--dry-run'), ('--apply', '--apply')]:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(*args).returncode, 2)

    def test_reject_tool_updates_without_apply(self):
        result = self.invoke('--with-tools')
        self.assertEqual(result.returncode, 2)
        self.assertIn('requires --apply', result.stderr)

    def test_help_does_not_mutate(self):
        result = self.invoke('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--with-tools', result.stdout)

    def test_apply_refuses_root_or_non_ubuntu_without_sudo(self):
        # The test sandbox may be root or Debian. On a supported non-root
        # Ubuntu host, --apply is deliberately NOT tested (would mutate OS).
        release = Path('/etc/os-release').read_text()
        if os.geteuid() == 0 or 'ID=ubuntu' not in release:
            result = self.invoke('--apply')
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        else:
            self.skipTest('Would mutate supported Ubuntu; no --apply in tests')


if __name__ == '__main__':
    unittest.main()
