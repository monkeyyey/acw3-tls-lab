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
Allow at least 1 GiB free storage. The default uses checksum-pinned, portable
CPython builds from Astral's `python-build-standalone` project, the same
distribution project used by uv. ARM64 (`aarch64`) and x86-64 are supported.
Each interpreter and its bundled libraries stay under `~/acw3`; no PATH
changes, global symlinks or system Python replacements are made.

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
   If Step 1 contains only some versions, each saved entry must still match.
   A notice identifies the incomplete history, and a complete fresh baseline
   is used for this run's before/after checks. Empty or mismatching saved
   baselines still stop setup.
2. Installs only missing runtime tools: Python 3, Git, curl, CA certificates,
   OpenSSL CLI and iproute2. An APT pre-install guard rejects
   replacement of any installed package, including dependency upgrades.
   `--no-remove` blocks package removal. This policy applies to that command.
3. Downloads both portable interpreters into their own
   `~/acw3/python-VERSION` directories after verifying pinned SHA-256 hashes.
   Version, architecture, vendor URLs and digests are recorded in
   [python-downloads.json](python-downloads.json), with a link to the exact
   upstream metadata commit. Both interpreters must import the lab's modules
   and pass vulnerable/patched behaviour checks.
4. Checks vulnerable/patched behaviour and prepares project certificates.
   Existing valid certificates are reused; a partial main certificate set
   stops setup rather than deleting existing files.
5. Checks ports 8443/8444, starts its own loopback server, runs T01-T07,
   checks the client results and server receipts, then stops its own server.
6. Compares existing application versions, every previously installed
   package version, Apache configuration and recorded MCPJam manifests.

The default does not request SQLite, OpenSSL or other development packages.
This avoids a dependency conflict such as `libsqlite3-dev` requesting an
upgrade of the VM's existing `libsqlite3-0`. Downloaded APT packages from a
previous blocked attempt can remain cached; this setup does not install
those cached development packages.

If setup still prints `BLOCKED`, stop and inspect the error. Even a missing
runtime tool can require replacing an installed library; that transaction
is refused. Do not remove the guard to force an upgrade.

The installer does not edit Apache/MCPJam configuration, restart their
services, change the default Python command, change network settings, or
install the generated CA into system trust. Adding missing packages
still changes the VM; your snapshot provides a rollback if needed.

### Optional source build

`bash setup.sh source` retains the original build-from-source approach. It
uses official python.org archives and `make altinstall` in private prefixes,
and requests `xz-utils`, `build-essential`, `pkg-config`, `libssl-dev` and
`zlib1g-dev` with the same package guard. Optional SQLite, Tk and database
development packages are omitted. Source mode can still be blocked when
development headers require replacing existing runtime libraries. Allow
6 GiB free; `ACW3_JOBS=1 bash setup.sh source` reduces compiler parallelism.

## Logs and live demonstration

Local logs are saved outside Git under `~/acw3/checks/runs/`. A successful
automatic run prints `7/7 tests passed` and finishes with preservation
checks passed. Logs include builds, client output, `server.txt` and
`results.tsv`. Reruns reuse healthy private Python installations.

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

Local validation passed all 31 guard/archive tests. All four pinned Linux
archives were downloaded and their checksums and layouts verified. T01-T07
and the expected server receipt counts also passed with the equivalent
macOS portable builds. These checks do not constitute an Ubuntu execution.

The GitHub Actions workflow targets Ubuntu 24.04, checks the guards,
preinstalls runtime tools in that disposable runner, and runs the default
portable installer with both Pythons and all seven TLS tests. Check Actions
for the latest result. A known account billing restriction has prevented
hosted jobs from starting, so this is not a claim of a successful Ubuntu run.
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
- [Astral's portable Python distributions](https://docs.astral.sh/python-build-standalone/)
- [Ubuntu APT hooks](https://manpages.ubuntu.com/manpages/noble/man5/apt.conf.5.html)
- [GitHub CLI login](https://cli.github.com/manual/gh_auth_login)
