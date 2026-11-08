# Ubuntu Python TLS lab

This local CVE-2026-19553 lab compares CPython 3.13.15 with patched CPython
3.13.16. The installer targets an existing Ubuntu 24.04 LTS VM, including
Ubuntu 24.04.5 with MCPJam and Apache already installed.

## Download and run

This repository is public. Cloning and pulling do not require a GitHub login.
Type these commands in Ubuntu, one line at a time:

```bash
cd ~
git clone https://github.com/monkeyyey/acw3-tls-lab.git lab
cd lab
bash setup.sh
```

For an existing clone, use `cd ~/lab`, `git pull --ff-only`, then `bash setup.sh`.
Keep your VM snapshot. Run as your normal account, without sudo; the script
requests sudo for dependencies and reading protected Apache configuration.
Allow at least 6 GiB free storage and time for two source builds.
On a low-memory VM use `ACW3_JOBS=1 bash setup.sh`.

If Git is missing but curl is available:

```bash
cd ~
curl -fL https://github.com/monkeyyey/acw3-tls-lab/archive/refs/heads/main.tar.gz -o lab.tar.gz
tar -xf lab.tar.gz
cd acw3-tls-lab-main
bash setup.sh
```

## What setup.sh does

1. Records existing application versions, installed package versions, Apache
   configuration hashes, and MCPJam package manifests if `~/mcpjam` exists.
   Set `MCPJAM_DIR` if your MCPJam project is elsewhere. Your existing
   `~/acw3/checks/versions-before.txt` from Step 1 is retained and compared.
2. Installs missing build dependencies. An APT pre-install guard rejects
   replacement of any installed package, including dependency upgrades.
   `--no-remove` blocks package removal. This policy applies to that command.
3. Verifies official source archive checksums, then builds each interpreter
   into its own `~/acw3/python-VERSION` prefix with `make altinstall`.
4. Checks vulnerable/patched behaviour and prepares project certificates.
   Existing valid certificates are reused; a partial main certificate set
   stops setup rather than deleting existing files.
5. Checks ports 8443/8444, starts its own loopback server, runs T01-T07,
   checks the client results and server receipts, then stops its own server.
6. Compares existing application versions, every previously installed
   package version, Apache configuration and recorded MCPJam manifests.

If setup prints `BLOCKED`, stop and inspect the error. For example, the
available `libssl-dev` may require upgrading the existing OpenSSL library.
That transaction is refused. Matching development packages or an isolated
VM copy may be needed; do not remove the guard to force an upgrade.

The installer does not edit Apache/MCPJam configuration, restart their
services, change the default Python command, change network settings, or
install the generated CA into system trust. Adding new build dependencies
still changes the VM; your snapshot provides a rollback if needed.

## Logs and live demonstration

Local logs are saved outside Git under `~/acw3/checks/runs/`. A successful
automatic run prints `7/7 tests passed` and finishes with preservation
checks passed. Logs include builds, client output, `server.txt` and
`results.tsv`. Reruns reuse healthy private Python builds.

For two terminals, run these commands from the repository folder:

```bash
# Terminal 1
bash setup.sh server
```

```bash
# Terminal 2
bash setup.sh test
```

Press Ctrl+C in Terminal 1 when finished. `bash setup.sh check` gives a
read-only status check; `bash setup.sh deps` runs only dependency setup.

| Test | Python | Expected result |
|---|---|---|
| T01 | 3.13.15 | Missing hostname permits the mock request to reach other.lab |
| T02 | 3.13.15 | Explicit hostname rejects other.lab |
| T03 | 3.13.15 | service.lab succeeds |
| T04 | 3.13.16 | Missing hostname rejected before connection |
| T05 | 3.13.16 | Explicit hostname rejects other.lab |
| T06 | 3.13.16 | service.lab succeeds |
| T07 | 3.13.15 | An unrelated CA rejects the attacker certificate |

The endpoints bind to `127.0.0.1:8443` and `127.0.0.1:8444`. MCPJam's normal
port 6274 and Apache's ports 80/443 are separate. No DNS or hosts-file
changes are needed. See [the runbook](demo/DEMO_RUNBOOK.md) for individual tests.

## GitHub terminal sign-in

Public downloads need no sign-in. To authenticate for future pushes, run:

```bash
bash setup.sh login
```

This installs GitHub CLI with the same package guard, starts the browser
login flow, then configures Git's HTTPS credential helper. Open the displayed
GitHub device page on your Mac if Ubuntu has no browser. Never commit tokens
or put them in repository URLs.

## Validation

```bash
bash -n setup.sh
python3 -m unittest discover -s tests -v
```

GitHub Actions runs on Ubuntu 24.04, checks the guards, preinstalls build
tools in that disposable runner, and runs the full installer with both
Python builds and all seven TLS tests. Check Actions for the latest result.
Hosted-runner validation cannot guarantee dependency installation on every
existing VM; the guard checks the actual VM's package transaction.

## Original project

The client, server and demonstration sources were copied unchanged from
`sh-yap/ACW3-CVE-2026-19553` at commit
`bd2d9a86204e06109a1d406101fd46a88f5685f8`. The source repository lists
sh-yap and WilsonTeng8778 as contributors. Its original README is retained
as [ORIGINAL_README.md](ORIGINAL_README.md). The installer, preservation
checks, regression tests and CI workflow are additions in this copy.
No new licence is asserted for the original code.

Generated certificates, private keys, logs and Python builds are excluded
from the published source.

## Primary references

- [Python 3.13.15 and checksum](https://www.python.org/downloads/release/python-31315/)
- [Python 3.13.16 and fix](https://www.python.org/downloads/release/python-31316/)
- [SSLContext.wrap_bio](https://docs.python.org/3.13/library/ssl.html#ssl.SSLContext.wrap_bio)
- [Python source installation](https://docs.python.org/3.13/using/unix.html#building-python)
- [Ubuntu APT hooks](https://manpages.ubuntu.com/manpages/noble/man5/apt.conf.5.html)
- [GitHub CLI login](https://cli.github.com/manual/gh_auth_login)
