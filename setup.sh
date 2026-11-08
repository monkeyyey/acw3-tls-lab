#!/usr/bin/env bash
# Ubuntu 24.04 local TLS lab. Run as your normal account: bash setup.sh
set -Eeuo pipefail
umask 077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
LAB_DIR="$HOME/acw3"
CHECK_DIR="$LAB_DIR/checks"
RUN_DIR=""
SERVER_PID=""
VULNERABLE="$LAB_DIR/python-3.13.15/bin/python3.13"
PATCHED="$LAB_DIR/python-3.13.16/bin/python3.13"
JOBS="${ACW3_JOBS:-2}"
DEPS=(python3 git curl ca-certificates xz-utils openssl iproute2
      build-essential pkg-config libssl-dev zlib1g-dev libbz2-dev
      libreadline-dev libsqlite3-dev libffi-dev liblzma-dev libncurses-dev
      libgdbm-dev libgdbm-compat-dev uuid-dev tk-dev)

say() { printf '\n[ACW3] %s\n' "$*"; }
die() { printf '\n[STOP] %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "Required command missing: $1"; }

cleanup() {
    if [[ -n "$SERVER_PID" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        SERVER_PID=""
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'rc=$?; printf "\n[STOP] Step failed (exit %s), line %s. Logs: %s\n" "$rc" "$LINENO" "${RUN_DIR:-not started}" >&2; exit "$rc"' ERR

usage() {
    cat <<'TEXT'
Run from your normal Ubuntu account, without sudo:
  bash setup.sh          Install missing dependencies, build both Pythons,
                         prepare certificates, run all seven tests, and
                         compare existing packages and Apache configuration.
  bash setup.sh deps     Install dependencies only, using the package guard.
  bash setup.sh check    Read-only readiness and port checks.
  bash setup.sh server   Run the prepared dual-endpoint server in this terminal.
  bash setup.sh test     Run T01-T07 against a server already running.
  bash setup.sh login    Install GitHub CLI with the guard and start login.
  bash setup.sh help     Show these commands.

Python installations: ~/acw3/python-3.13.15 and ~/acw3/python-3.13.16
Local logs: ~/acw3/checks/runs (never committed to this repository)
If a package replacement is blocked, stop and inspect the error.
TEXT
}

platform_check() {
    [[ "$EUID" -ne 0 ]] || die "Run bash setup.sh without sudo; the dependency step requests sudo itself."
    [[ -f /etc/os-release ]] || die "This installer requires Ubuntu 24.04."
    # shellcheck disable=SC1091
    source /etc/os-release
    [[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || die "Use Ubuntu 24.04; detected ${PRETTY_NAME:-unknown}."
    need python3
    need sudo
    [[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || die "ACW3_JOBS must be a positive integer."
    [[ "$HOME" != *$'\n'* && "$HOME" != *"'"* ]] || die "The home path contains unsupported quoting characters."
}

new_run() {
    mkdir -p "$CHECK_DIR/runs"
    RUN_DIR="$(mktemp -d "$CHECK_DIR/runs/$(date +%Y%m%d-%H%M%S)-XXXXXX")"
    say "Logs: $RUN_DIR"
}

versions() {
    local command
    for command in /usr/bin/python3 node npm apache2 openssl; do
        if command -v "$command" >/dev/null; then
            if [[ "$command" == apache2 ]]; then "$command" -v
            elif [[ "$command" == openssl ]]; then "$command" version
            else "$command" --version
            fi
        else
            printf '%s: not installed\n' "$command"
        fi
    done
}

packages() {
    dpkg-query -W -f='${binary:Package}\t${Version}\t${db:Status-Status}\n' \
        | awk -F '\t' '$3 == "installed" {print $1 "\t" $2}' | LC_ALL=C sort
}

apache_manifest() {
    if [[ -d /etc/apache2 ]]; then
        sudo find /etc/apache2 -type f -exec sha256sum {} + | LC_ALL=C sort
    fi
}

mcp_manifest() {
    local directory="${MCPJAM_DIR:-$HOME/mcpjam}" file
    for file in package.json package-lock.json node_modules/@mcpjam/inspector/package.json; do
        [[ ! -f "$directory/$file" ]] || sha256sum "$directory/$file"
    done
    return 0
}

compare_step1_baseline() {
    python3 - "$RUN_DIR/step1-versions.txt" "$RUN_DIR/versions-before.txt" <<'PY'
from collections import Counter
from pathlib import Path
import sys

def lines(filename):
    return [line.strip() for line in Path(filename).read_text().splitlines() if line.strip()]

saved, current = map(lines, sys.argv[1:])
if not saved:
    print('[FAIL] The saved Step 1 baseline is empty. Inspect it before continuing.')
    sys.exit(1)
missing = Counter(saved) - Counter(current)
if missing:
    print('[FAIL] These saved Step 1 entries do not match the current environment:')
    for line, count in missing.items():
        print(f'  {line}' + (f' ({count} entries)' if count > 1 else ''))
    sys.exit(1)
if len(saved) < len(current):
    print('[NOTICE] Step 1 recorded only part of the version information.')
    print('[PASS] Every recorded entry still matches. The original file is retained.')
    print('[NOTICE] Missing historical versions cannot be checked; the complete current')
    print('         baseline will be used to verify changes made by this setup run.')
else:
    print('[PASS] The saved Step 1 versions match the current environment.')
PY
}

capture_before() {
    versions > "$RUN_DIR/versions-before.txt" 2>&1
    packages > "$RUN_DIR/packages-before.tsv"
    apache_manifest > "$RUN_DIR/apache-before.sha256"
    mcp_manifest > "$RUN_DIR/mcp-before.sha256"
    if [[ -f "$CHECK_DIR/versions-before.txt" ]]; then
        cp -- "$CHECK_DIR/versions-before.txt" "$RUN_DIR/step1-versions.txt"
        if ! compare_step1_baseline; then
            die "Current versions differ from your saved Step 1 baseline. Check the difference before continuing."
        fi
    fi
}

check_preservation() {
    say "Comparing existing versions, installed packages and Apache configuration"
    versions > "$RUN_DIR/versions-after.txt" 2>&1
    apache_manifest > "$RUN_DIR/apache-after.sha256"
    mcp_manifest > "$RUN_DIR/mcp-after.sha256"
    packages > "$RUN_DIR/packages-after.tsv"
    diff -u "$RUN_DIR/versions-before.txt" "$RUN_DIR/versions-after.txt"
    diff -u "$RUN_DIR/apache-before.sha256" "$RUN_DIR/apache-after.sha256"
    diff -u "$RUN_DIR/mcp-before.sha256" "$RUN_DIR/mcp-after.sha256"
    python3 - "$RUN_DIR" <<'PY'
from pathlib import Path
import sys
folder = Path(sys.argv[1])
def read(name):
    return dict(line.split('\t', 1) for line in (folder / name).read_text().splitlines())
before, after = read('packages-before.tsv'), read('packages-after.tsv')
changes = [(name, old, after.get(name, 'REMOVED')) for name, old in before.items()
           if after.get(name) != old]
for name, old, new in changes:
    print(f'[FAIL] Existing package changed: {name}: {old} -> {new}')
if changes:
    sys.exit(1)
print('[PASS] Every previously installed package retains its version.')
PY
    say "Preservation checks passed. New build dependencies may have been added."
}

write_guard() {
    cat > "$RUN_DIR/apt-no-replace.sh" <<'SH'
#!/bin/sh
set -eu
while IFS= read -r deb; do
    [ -n "$deb" ] || continue
    [ -f "$deb" ] || { echo 'BLOCKED: unexpected package input' >&2; exit 1; }
    package=$(dpkg-deb -f "$deb" Package)
    architecture=$(dpkg-deb -f "$deb" Architecture)
    state=$(dpkg-query -W -f='${db:Status-Status}' "$package:$architecture" 2>/dev/null || true)
    if [ "$state" = installed ]; then
        echo "BLOCKED: would replace installed package $package:$architecture" >&2
        exit 1
    fi
done
SH
    chmod 700 "$RUN_DIR/apt-no-replace.sh"
}

install_dependencies() {
    local audit package state missing=()
    audit="$(sudo dpkg --audit)"
    [[ -z "$audit" ]] || die "Existing package issue: $audit"
    for package in "$@"; do
        state="$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null || true)"
        [[ "$state" == installed ]] || missing+=("$package")
    done
    if [[ "${#missing[@]}" -eq 0 ]]; then
        say "All requested dependencies are already installed."
        return
    fi
    write_guard
    say "Installing missing packages: ${missing[*]}"
    sudo apt-get update
    sudo apt-get --no-upgrade --no-remove --no-install-recommends \
        -o "DPkg::Pre-Install-Pkgs::=/bin/sh '$RUN_DIR/apt-no-replace.sh'" \
        install "${missing[@]}"
}

project_check() {
    local file
    for file in client/check_wrap_bio.py server/make_test_certs.sh \
        demo/make_service_cert.sh demo/make_t07_ca.sh demo/impact_server.py \
        demo/impact_client.py demo/t07_untrusted_ca.py demo/preflight.sh; do
        [[ -f "$PROJECT_DIR/$file" ]] || die "Missing project file: $file. Clone the complete repository."
    done
    [[ ! -L "$LAB_DIR" && ! -L "$PROJECT_DIR/certs" ]] || die "Lab and certificate directories must not be symbolic links."
}

ports_free() {
    local listeners
    listeners="$(ss -H -ltn | awk '$4 ~ /:(8443|8444)$/')"
    [[ -z "$listeners" ]] || die "Ports 8443/8444 are occupied. Stop your old lab server yourself, then retry. $listeners"
}

python_check() {
    local executable="$1" version="$2"
    [[ -x "$executable" ]] || return 1
    "$executable" - "$version" <<'PY'
import ssl, sys
assert sys.version.split()[0] == sys.argv[1], (sys.version, sys.argv[1])
print('Python', sys.version.split()[0], '|', ssl.OPENSSL_VERSION)
PY
}

build_python() {
    local version="$1" checksum="$2" archive prefix
    archive="$LAB_DIR/src/Python-$version.tar.xz"
    prefix="$LAB_DIR/python-$version"
    [[ ! -L "$prefix" && ! -L "$archive" && ! -L "$LAB_DIR/src/Python-$version" ]] \
        || die "Build paths must not be symbolic links."
    if [[ -e "$prefix" ]]; then
        python_check "$prefix/bin/python3.13" "$version" \
            || die "Existing private Python $version is incomplete. Inspect $prefix before rebuilding."
        say "Reusing healthy private Python $version"
        return
    fi
    mkdir -p "$LAB_DIR/src"
    if [[ ! -f "$archive" ]]; then
        curl --fail --location --retry 3 \
            "https://www.python.org/ftp/python/$version/Python-$version.tar.xz" \
            --output "$archive.part"
        mv -- "$archive.part" "$archive"
    fi
    printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check
    if [[ ! -d "$LAB_DIR/src/Python-$version" ]]; then
        tar -xf "$archive" -C "$LAB_DIR/src"
    fi
    say "Building Python $version with $JOBS jobs (this takes several minutes)"
    (
        cd "$LAB_DIR/src/Python-$version"
        ./configure --prefix="$prefix" --with-ensurepip=install
        make -j"$JOBS"
        make altinstall
    ) 2>&1 | tee "$RUN_DIR/build-$version.txt"
    python_check "$prefix/bin/python3.13" "$version"
}

standalone_checks() {
    "$VULNERABLE" "$PROJECT_DIR/client/check_wrap_bio.py" | tee "$RUN_DIR/wrap-bio-vulnerable.txt"
    grep -Fq 'RESULT: Missing hostname accepted' "$RUN_DIR/wrap-bio-vulnerable.txt"
    "$PATCHED" "$PROJECT_DIR/client/check_wrap_bio.py" | tee "$RUN_DIR/wrap-bio-patched.txt"
    grep -Fq 'RESULT: Missing hostname rejected' "$RUN_DIR/wrap-bio-patched.txt"
}

verify_certificates() {
    local pair cert_key expected_name public_cert public_key
    for pair in 'server other.lab' 'service service.lab'; do
        read -r cert_key expected_name <<< "$pair"
        openssl verify -x509_strict -purpose sslserver -verify_hostname "$expected_name" \
            -CAfile "$PROJECT_DIR/certs/ca.crt" "$PROJECT_DIR/certs/$cert_key.crt"
        public_cert="$(openssl x509 -in "$PROJECT_DIR/certs/$cert_key.crt" -pubkey -noout \
            | openssl pkey -pubin -outform DER | sha256sum)"
        public_key="$(openssl pkey -in "$PROJECT_DIR/certs/$cert_key.key" -pubout -outform DER | sha256sum)"
        [[ "$public_cert" == "$public_key" ]] || die "Certificate/key mismatch: $cert_key"
    done
    openssl x509 -in "$PROJECT_DIR/certs/t07/ca.crt" -noout -checkend 0
    if openssl verify -CAfile "$PROJECT_DIR/certs/t07/ca.crt" \
        "$PROJECT_DIR/certs/server.crt" > "$RUN_DIR/t07-chain-check.txt" 2>&1; then
        die "The independent T07 CA unexpectedly trusts the attacker certificate."
    fi
    grep -Fq 'unable to get local issuer certificate' "$RUN_DIR/t07-chain-check.txt" \
        || die "T07 chain check failed for an unexpected reason; inspect its log."
}

prepare_certificates() {
    cd "$PROJECT_DIR"
    if [[ ! -f certs/ca.crt || ! -f certs/ca.key || ! -f certs/server.crt || ! -f certs/server.key ]]; then
        if [[ -d certs && -n "$(find certs -mindepth 1 -print -quit)" ]]; then
            die "Partial certificate directory found. Existing certificates were preserved; inspect certs before retrying."
        fi
        bash server/make_test_certs.sh
    fi
    bash demo/make_service_cert.sh
    bash demo/make_t07_ca.sh
    verify_certificates
}

listeners_ready() {
    local port listeners
    for port in 8443 8444; do
        listeners="$(ss -H -ltn | awk -v port="$port" '$4 ~ (":" port "$") {print $4}')"
        [[ "$listeners" == "127.0.0.1:$port" ]] || return 1
    done
}

run_one() {
    local id="$1" interpreter="$2" filename="$3" mode="$4" marker="$5"
    say "$id"
    timeout 30s "$interpreter" "$PROJECT_DIR/$filename" --mode "$mode" 2>&1 | tee "$RUN_DIR/$id.txt"
    grep -Fq "$marker" "$RUN_DIR/$id.txt" || die "$id returned without its expected result marker."
    printf '%s\tPASS\n' "$id" >> "$RUN_DIR/results.tsv"
}

run_tests() {
    python_check "$VULNERABLE" 3.13.15
    python_check "$PATCHED" 3.13.16
    verify_certificates
    listeners_ready || die "Expected exactly 127.0.0.1:8443 and 127.0.0.1:8444. Start bash setup.sh server in another terminal."
    bash "$PROJECT_DIR/demo/preflight.sh"
    : > "$RUN_DIR/results.tsv"
    run_one T01 "$VULNERABLE" demo/impact_client.py missing 'HOSTNAME VERIFICATION BYPASS CONFIRMED'
    run_one T02 "$VULNERABLE" demo/impact_client.py wrong '[BLOCKED] HOSTNAME MISMATCH'
    run_one T03 "$VULNERABLE" demo/impact_client.py correct 'LEGITIMATE SERVER RECEIVED REQUEST'
    run_one T04 "$PATCHED" demo/impact_client.py missing '[PATCHED] MISSING HOSTNAME REJECTED'
    run_one T05 "$PATCHED" demo/impact_client.py wrong '[BLOCKED] HOSTNAME MISMATCH'
    run_one T06 "$PATCHED" demo/impact_client.py correct 'LEGITIMATE SERVER RECEIVED REQUEST'
    run_one T07 "$VULNERABLE" demo/t07_untrusted_ca.py missing '[BLOCKED] UNTRUSTED CERTIFICATE'
    say "7/7 tests passed. Results: $RUN_DIR/results.tsv"
}

automated_demo() {
    local attempt ready=no attacker_count legitimate_count
    ports_free
    "$PATCHED" -u "$PROJECT_DIR/demo/impact_server.py" > "$RUN_DIR/server.txt" 2>&1 &
    SERVER_PID="$!"
    for attempt in {1..100}; do
        kill -0 "$SERVER_PID" 2>/dev/null || { cat "$RUN_DIR/server.txt"; die "The lab server exited."; }
        if grep -Fq '[READY] LEGITIMATE' "$RUN_DIR/server.txt" && listeners_ready; then ready=yes; break; fi
        sleep 0.1
    done
    [[ "$ready" == yes ]] || die "The lab server did not become ready."
    run_tests
    attacker_count="$(awk '/ATTACKER RECEIVED MOCK SESSION TOKEN/ {n++} END {print n+0}' "$RUN_DIR/server.txt")"
    legitimate_count="$(awk '/LEGITIMATE SERVER RECEIVED REQUEST/ {n++} END {print n+0}' "$RUN_DIR/server.txt")"
    [[ "$attacker_count" == 1 && "$legitimate_count" == 2 ]] \
        || die "Unexpected server receipt counts. Inspect $RUN_DIR/server.txt."
    cleanup
}

main() {
    local mode="${1:-setup}" free_kb
    case "$mode" in help|-h|--help) usage; return;; esac
    platform_check
    project_check
    case "$mode" in
        check)
            say 'Read-only environment check'
            versions
            df -h "$HOME"
            for binary in "$VULNERABLE" "$PATCHED"; do
                [[ ! -x "$binary" ]] || "$binary" --version
            done
            need ss
            ss -ltn | awk 'NR == 1 || $4 ~ /:(80|443|6274|8443|8444)$/'
            return;;
        server)
            need ss
            python_check "$PATCHED" 3.13.16
            ports_free
            exec "$PATCHED" -u "$PROJECT_DIR/demo/impact_server.py";;
        setup|deps|test|login) ;;
        *) usage; die "Unknown command: $mode";;
    esac
    new_run
    if [[ "$mode" == test ]]; then run_tests; return; fi
    sudo -v
    capture_before
    if [[ "$mode" == login ]]; then
        install_dependencies git gh
        check_preservation
        gh auth login --hostname github.com --git-protocol https --web
        gh auth setup-git --hostname github.com
        return
    fi
    install_dependencies "${DEPS[@]}"
    check_preservation
    [[ "$mode" != deps ]] || return
    ports_free
    free_kb="$(df -Pk "$LAB_DIR" | awk 'END {print $4}')"
    [[ "$free_kb" -ge 6291456 ]] || die "Allow at least 6 GiB free for the two source builds."
    build_python 3.13.15 1e66a7945a48390ee4c2a4268a0e4185884059a13c4aab6d148aa208deea4a76
    build_python 3.13.16 f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d
    standalone_checks
    prepare_certificates
    automated_demo
    check_preservation
    say 'Setup complete. The temporary lab server has been stopped.'
    printf '\nFor a live demonstration:\n  Terminal 1: bash setup.sh server\n  Terminal 2: bash setup.sh test\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
