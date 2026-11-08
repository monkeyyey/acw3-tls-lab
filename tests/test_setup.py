"""Regression checks for preservation guards; no sudo or package installs."""
from pathlib import Path
import hashlib
import json
import os
import shlex
import subprocess
import tarfile
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

    def baseline(self, saved, current=None):
        if current is None:
            current = ('Python 3.12.3\nv22.23.4\n10.9.9\n'
                       'Server version: Apache/2.4.58 (Ubuntu)\n'
                       'Server built:   2026-10-08T19:58:01\n'
                       'OpenSSL 3.0.13 30 Jan 2024 (Library: OpenSSL 3.0.13 30 Jan 2024)\n')
        (self.folder / 'step1-versions.txt').write_text(saved)
        (self.folder / 'versions-before.txt').write_text(current)
        result = self.shell('RUN_DIR=' + shlex.quote(str(self.folder)) + '; compare_step1_baseline')
        self.assertEqual((self.folder / 'step1-versions.txt').read_text(), saved)
        self.assertEqual((self.folder / 'versions-before.txt').read_text(), current)
        return result

    def test_partial_step1_baseline_accepts_matching_python(self):
        result = self.baseline('Python 3.12.3\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Missing historical versions cannot be checked', result.stdout)

    def test_complete_step1_baseline_is_accepted(self):
        result = self.baseline('Python 3.12.3\nv22.23.4\n', 'Python 3.12.3\nv22.23.4\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('[NOTICE]', result.stdout)

    def test_changed_python_version_is_blocked(self):
        result = self.baseline('Python 3.12.2\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Python 3.12.2', result.stdout)

    def test_changed_apache_version_in_partial_baseline_is_blocked(self):
        result = self.baseline('Python 3.12.3\nServer version: Apache/2.4.57 (Ubuntu)\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Apache/2.4.57', result.stdout)

    def test_empty_step1_baseline_is_blocked(self):
        result = self.baseline('\n  \n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('baseline is empty', result.stdout)

    def test_duplicate_saved_entries_are_blocked(self):
        self.assertNotEqual(self.baseline('Python 3.12.3\nPython 3.12.3\n').returncode, 0)

    def test_baseline_whitespace_and_blank_lines_are_accepted(self):
        self.assertEqual(self.baseline('\n Python 3.12.3  \n\n').returncode, 0)

    def test_arm64_portable_versions_are_pinned(self):
        for version in ('3.13.15', '3.13.16'):
            result = self.shell(f'portable_spec {version} aarch64')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f'cpython-{version}%2B', result.stdout)
            self.assertIn('-aarch64-unknown-linux-gnu-', result.stdout)

    def test_x86_portable_versions_are_pinned(self):
        for version in ('3.13.15', '3.13.16'):
            result = self.shell(f'portable_spec {version} x86_64')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('-x86_64-unknown-linux-gnu-', result.stdout)

    def test_unsupported_portable_architecture_is_blocked(self):
        result = self.shell('portable_spec 3.13.15 riscv64')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unsupported portable Python request', result.stderr)

    def portable_metadata(self, field, value):
        data = json.loads((SETUP.parent / 'python-downloads.json').read_text())
        data['downloads']['3.13.15/aarch64'][field] = value
        (self.folder / 'python-downloads.json').write_text(json.dumps(data))
        return 'PROJECT_DIR=' + shlex.quote(str(self.folder)) + '; '

    def test_substituted_download_vendor_is_blocked(self):
        command = self.portable_metadata('url', 'https://example.invalid/python.tar.gz')
        result = self.shell(command + 'portable_spec 3.13.15 aarch64')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('does not match', result.stderr)

    def test_invalid_download_digest_is_blocked(self):
        command = self.portable_metadata('sha256', 'not-a-checksum')
        result = self.shell(command + 'portable_spec 3.13.15 aarch64')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Invalid pinned', result.stderr)

    def test_substituted_asset_api_vendor_is_blocked(self):
        command = self.portable_metadata('api_url', 'https://api.github.com/repos/example/other/releases/assets/1')
        result = self.shell(command + 'portable_spec 3.13.15 aarch64')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('API URL does not match', result.stderr)

    def portable_fixture(self, corrupt=False):
        fixture = self.folder / 'fixture' / 'python' / 'bin'
        fixture.mkdir(parents=True)
        executable = fixture / 'python3.13'
        executable.write_text('#!/bin/sh\ncat >/dev/null\nprintf "fixture interpreter\\n"\n')
        executable.chmod(0o700)
        archive = self.folder / 'fixture.tar.gz'
        with tarfile.open(archive, 'w:gz') as handle:
            handle.add(fixture.parent, arcname='python')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        command = self.portable_metadata('sha256', digest)
        self.lab = self.folder / 'private lab'
        cache = self.lab / 'src'
        cache.mkdir(parents=True)
        (cache / 'cpython-3.13.15-aarch64-portable.tar.gz').write_bytes(
            b'corrupted download' if corrupt else archive.read_bytes())
        self.mock('uname', 'echo aarch64')
        self.mock('curl', 'echo "Unexpected network request" >&2; exit 99')
        return (command + 'LAB_DIR=' + shlex.quote(str(self.lab)) + '; RUN_DIR='
                + shlex.quote(str(self.folder)) + '; install_portable_python 3.13.15')

    def test_verified_archive_is_installed_under_private_prefix(self):
        result = self.shell(self.portable_fixture())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.lab / 'python-3.13.15' / 'bin' / 'python3.13').is_file())
        self.assertEqual(list(self.lab.glob('.portable-*')), [])

    def test_corrupt_portable_archive_is_rejected_before_extraction(self):
        result = self.shell(self.portable_fixture(corrupt=True))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.lab / 'python-3.13.15').exists())
        self.assertEqual(list(self.lab.glob('.portable-*')), [])

    def test_incomplete_private_installation_is_preserved(self):
        command = self.portable_fixture()
        prefix = self.lab / 'python-3.13.15'
        prefix.mkdir()
        sentinel = prefix / 'preserve.txt'
        sentinel.write_text('existing files')
        result = self.shell(command)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('is incomplete', result.stderr)
        self.assertEqual(sentinel.read_text(), 'existing files')

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
