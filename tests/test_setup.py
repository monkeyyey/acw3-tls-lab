"""Regression checks for preservation guards; no sudo or package installs."""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest

SETUP = Path(__file__).resolve().parents[1] / 'setup.sh'


class SetupGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='acw3-guards-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.bin = self.folder / 'bin'
        self.bin.mkdir()
        self.env = os.environ.copy()
        self.env['PATH'] = str(self.bin) + os.pathsep + self.env['PATH']
        self.env['ACW3_TEST_STATE'] = 'not-installed'
        self.mock('dpkg-deb', '''case "$3" in
            Package) echo example-package;;
            Architecture) echo "${ACW3_TEST_ARCH:-arm64}";;
            *) exit 1;;
        esac''')
        self.mock('dpkg-query', 'printf "%s" "$ACW3_TEST_STATE"')
        self.mock('ss', 'printf "%s\\n" "${ACW3_TEST_LISTENERS:-}"')
        self.deb = self.folder / 'package with spaces.deb'
        self.deb.touch()
        result = self.shell('RUN_DIR=' + shlex.quote(str(self.folder)) + '; write_guard')
        self.assertEqual(result.returncode, 0, result.stderr)

    def mock(self, name, body):
        file = self.bin / name
        file.write_text('#!/bin/sh\nset -eu\n' + body + '\n')
        file.chmod(0o700)

    def shell(self, command):
        return subprocess.run(
            ['bash', '-c', f'source {shlex.quote(str(SETUP))}; {command}'],
            capture_output=True, text=True, env=self.env, timeout=10)

    def guard(self, data=None):
        return subprocess.run(
            ['/bin/sh', str(self.folder / 'apt-no-replace.sh')],
            input=str(self.deb) + '\n' if data is None else data,
            capture_output=True, text=True, env=self.env, timeout=10)

    def test_new_package_is_allowed(self):
        self.assertEqual(self.guard().returncode, 0)

    def test_existing_package_is_blocked(self):
        self.env['ACW3_TEST_STATE'] = 'installed'
        result = self.guard()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('BLOCKED: would replace installed package example-package:arm64', result.stderr)

    def test_architecture_independent_package_is_blocked(self):
        self.env['ACW3_TEST_STATE'] = 'installed'
        self.env['ACW3_TEST_ARCH'] = 'all'
        self.assertNotEqual(self.guard().returncode, 0)

    def test_bad_package_metadata_is_blocked(self):
        self.mock('dpkg-deb', 'exit 1')
        self.assertNotEqual(self.guard().returncode, 0)

    def test_unknown_hook_protocol_is_blocked(self):
        self.assertNotEqual(self.guard('VERSION 3\n').returncode, 0)

    def test_empty_transaction_is_allowed(self):
        self.assertEqual(self.guard('').returncode, 0)

    def test_package_path_with_spaces_is_supported(self):
        self.assertEqual(self.guard().returncode, 0)

    def test_free_ports_are_accepted(self):
        self.assertEqual(self.shell('ports_free').returncode, 0)

    def test_occupied_ipv4_port_is_blocked(self):
        self.env['ACW3_TEST_LISTENERS'] = 'LISTEN 0 128 127.0.0.1:8443 0.0.0.0:*'
        self.assertNotEqual(self.shell('ports_free').returncode, 0)

    def test_occupied_ipv6_port_is_blocked(self):
        self.env['ACW3_TEST_LISTENERS'] = 'LISTEN 0 128 [::]:8444 [::]:*'
        self.assertNotEqual(self.shell('ports_free').returncode, 0)

    def test_apache_and_mcpjam_ports_are_not_blocked(self):
        self.env['ACW3_TEST_LISTENERS'] = ('LISTEN 0 128 0.0.0.0:80 0.0.0.0:*\n'
                                        'LISTEN 0 128 0.0.0.0:6274 0.0.0.0:*')
        self.assertEqual(self.shell('ports_free').returncode, 0)

    def test_both_loopback_endpoints_are_required(self):
        self.env['ACW3_TEST_LISTENERS'] = ('LISTEN 0 128 127.0.0.1:8443 0.0.0.0:*\n'
                                        'LISTEN 0 128 127.0.0.1:8444 0.0.0.0:*')
        self.assertEqual(self.shell('listeners_ready').returncode, 0)

    def test_missing_second_endpoint_is_rejected(self):
        self.env['ACW3_TEST_LISTENERS'] = 'LISTEN 0 128 127.0.0.1:8443 0.0.0.0:*'
        self.assertNotEqual(self.shell('listeners_ready').returncode, 0)

    def test_wildcard_endpoint_is_rejected(self):
        self.env['ACW3_TEST_LISTENERS'] = ('LISTEN 0 128 0.0.0.0:8443 0.0.0.0:*\n'
                                        'LISTEN 0 128 127.0.0.1:8444 0.0.0.0:*')
        self.assertNotEqual(self.shell('listeners_ready').returncode, 0)

    def test_help_needs_no_ubuntu_or_sudo(self):
        result = subprocess.run(['bash', str(SETUP), 'help'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn('bash setup.sh', result.stdout)


if __name__ == '__main__':
    unittest.main()
