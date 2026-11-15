"""Synthetic HTTPS and kernel checks, mounted into the CI container read-only."""
from __future__ import annotations

import csv
import errno
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import ssl
import stat
# A fixed Python argv runs the real bootstrap; output stays in memory.
import subprocess  # nosec B404
import sys
import threading


QUOTE = "Оплата производится в течение 30 календарных дней."
CLAIM = "Срок оплаты — 30 календарных дней."
# The complete trusted paragraph, including its clause number, reaches verification.
SOURCE_TEXT = "1. " + QUOTE + "\n"
VERIFIED_CLAIM = "«" + SOURCE_TEXT.strip() + "»"
EXPECTED_ANSWER = CLAIM + "\nИсточник: contract."
QUESTION_ID = "0001"
# Fixed container mount paths are observed; no shared host temporary files are opened.
CONTAINER_TMP = "/tmp"  # nosec B108
# An exclusive create must fail on the read-only container root filesystem.
ROOT_WRITE_PROBE = "/var/tmp/psb-probe-write"  # nosec B108
APP_FILES = {
    "solution.py", "psb_corpus.py", "psb_retrieval.py", "psb_llm.py", "psb_policy.py",
    "requirements.txt",
}
CHECK_NAMES = {
    "runtime-user", "runtime-capabilities", "runtime-no-new-privileges", "runtime-seccomp",
    "runtime-root-readonly", "runtime-data-readonly", "runtime-output-writable",
    "runtime-tmpfs", "runtime-network-none", "runtime-memory-limit", "runtime-pids-limit",
    "runtime-cpu-limit", "runtime-secret-mount", "image-minimal-app-files",
    "image-root-owned-code", "image-source-integrity", "https-bootstrap-exit",
    "https-provider-auth", "https-provider-requests", "answer-csv-schema", "answer-csv-id",
    "answer-csv-grounded", "runtime-cwd-import-isolation", "application-log-redaction",
}


def model_reply(payload: dict) -> dict:
    """Return a grounded candidate only when the actual retrieved evidence supports it."""
    evidence = payload.get("evidence", [])
    matching = [item for item in evidence if isinstance(item, dict)
                and isinstance(item.get("text"), str) and isinstance(item.get("id"), str)
                and item["text"] == SOURCE_TEXT]
    if not matching:
        raise ValueError("fixture_evidence_mismatch")
    # Context expansion may legitimately repeat this quote in an overlapping fragment.
    source = min(matching, key=lambda item: (len(item["text"]), item["id"]))
    candidate = {
        "status": "answer",
        "answer": CLAIM,
        "claims": [{"text": CLAIM, "sources": [{"fragment_id": source["id"], "quote": QUOTE}]}],
        "missing": [], "clarification": "", "requested_facts": [], "issue": "",
    }
    if "candidate" not in payload:
        return candidate
    candidate["claims"][0]["text"] = VERIFIED_CLAIM
    candidate["claims"][0]["sources"][0]["quote"] = SOURCE_TEXT
    if payload["candidate"] != candidate or payload.get("rendered_answer") != EXPECTED_ANSWER:
        raise ValueError("fixture_candidate_mismatch")
    return {
        "approved": True, "complete": True, "status": "answer",
        "answer_supported": True,
        "claim_checks": [{"index": 0, "supported": True, "applicable": True}],
        "reason": "Synthetic fixture matches the supplied source.",
    }


def csv_checks(path: Path) -> dict[str, bool]:
    result = {"answer-csv-schema": False, "answer-csv-id": False, "answer-csv-grounded": False}
    try:
        if path.stat().st_size > 32768:
            return result
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            result["answer-csv-schema"] = reader.fieldnames == ["id", "answer"] and len(rows) == 1
        if result["answer-csv-schema"]:
            result["answer-csv-id"] = rows[0].get("id") == QUESTION_ID
            result["answer-csv-grounded"] = rows[0].get("answer") == EXPECTED_ANSWER
    except (OSError, UnicodeError, csv.Error):
        pass
    return result


def serve_application(command: list[str], environment: dict[str, str], output: Path,
                      secret: bytes, certificate: Path, private_key: Path) -> dict[str, bool]:
    """Exercise real urllib TLS, bearer authentication, generation and verification."""
    state = {"requests": 0, "auth_ok": True, "payload_ok": True}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def do_POST(self):
            state["requests"] += 1
            authenticated = self.headers.get("Authorization", "").encode() == b"Bearer " + secret
            state["auth_ok"] = state["auth_ok"] and authenticated
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not authenticated or self.path != "/v1/chat/completions" or not 0 < size <= 512000:
                    raise ValueError("fixture_request_mismatch")
                body = json.loads(self.rfile.read(size))
                if body.get("model") != "fixture-model" or len(body.get("messages", [])) != 2:
                    raise ValueError("fixture_request_mismatch")
                payload = json.loads(body["messages"][1]["content"])
                reply = model_reply(payload)
                response = {"choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(reply, ensure_ascii=False),
                }}]}
                status_code = 200
            except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
                state["payload_ok"] = False
                response = {"error": "invalid_synthetic_request"}
                status_code = 400
            encoded = json.dumps(response, ensure_ascii=False).encode()
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, private_key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    child_env = dict(environment)
    for name in list(child_env):
        if name.lower().endswith("_proxy"):
            child_env.pop(name)
    child_env.update({
        "LLM_BASE_URL": "https://127.0.0.1:" + str(server.server_port) + "/v1",
        "LLM_MODEL": "fixture-model", "SSL_CERT_FILE": str(certificate),
        "MAX_WORKERS": "1", "PSB_RUN_SECONDS": "30", "PSB_VERIFY": "1",
    })
    try:
        # The caller provides an explicit Python executable and repository-controlled arguments.
        process = subprocess.run(  # nosec B603
            command, cwd=output, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=45, check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    checks = {
        "https-bootstrap-exit": process.returncode == 0,
        "https-provider-auth": state["auth_ok"] and state["requests"] == 2,
        "https-provider-requests": state["payload_ok"] and state["requests"] == 2,
        "application-log-redaction": secret not in process.stdout + process.stderr,
    }
    checks.update(csv_checks(output / "submission.csv"))
    checks["runtime-cwd-import-isolation"] = (
        process.returncode == 0 and checks["answer-csv-grounded"]
        and b"untrusted_cwd_imported" not in process.stdout + process.stderr
    )
    return checks


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def bounded_limit(paths: tuple[str, ...], maximum: int) -> bool:
    for path in paths:
        value = read_text(path)
        if value.isdecimal():
            return 0 < int(value) <= maximum
    return False


def mount_table() -> dict[str, tuple[set[str], str]]:
    result = {}
    for line in read_text("/proc/self/mountinfo").splitlines():
        left, right = line.split(" - ", 1)
        fields = left.split()
        result[fields[4]] = (set(fields[5].split(",")), right.split()[0])
    return result


def failed_write(path: Path) -> bool:
    try:
        with path.open("xb"):
            pass
        path.unlink()
        return False
    except OSError as exc:
        return exc.errno in {errno.EROFS, errno.EACCES, errno.EPERM}


def runtime_checks() -> dict[str, bool]:
    status = dict(line.split(":", 1) for line in read_text("/proc/self/status").splitlines())
    mounts = mount_table()
    checks = {
        "runtime-user": (os.getuid(), os.getgid(), os.geteuid(), os.getegid()) == (10001,) * 4,
        "runtime-capabilities": all(int(status.get(name, "1").strip(), 16) == 0 for name in (
            "CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb",
        )),
        "runtime-no-new-privileges": status.get("NoNewPrivs", "").strip() == "1",
        "runtime-seccomp": status.get("Seccomp", "").strip() == "2",
        "runtime-root-readonly": "ro" in mounts.get("/", (set(), ""))[0]
            and failed_write(Path(ROOT_WRITE_PROBE)),
        "runtime-data-readonly": "ro" in mounts.get("/data", (set(), ""))[0]
            and failed_write(Path("/data/psb-probe-write")),
        "runtime-tmpfs": mounts.get(CONTAINER_TMP, (set(), ""))[1] == "tmpfs"
            and {"rw", "nosuid", "nodev", "noexec"} <= mounts.get(CONTAINER_TMP, (set(), ""))[0],
        "runtime-network-none": {item.name for item in Path("/sys/class/net").iterdir()} == {"lo"},
        "runtime-memory-limit": bounded_limit((
            "/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes",
        ), 512 * 1024 * 1024),
        "runtime-pids-limit": bounded_limit((
            "/sys/fs/cgroup/pids.max", "/sys/fs/cgroup/pids/pids.max",
        ), 128),
    }
    cpu = read_text("/sys/fs/cgroup/cpu.max").split()
    if len(cpu) != 2:
        cpu = [read_text("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"),
               read_text("/sys/fs/cgroup/cpu/cpu.cfs_period_us")]
    checks["runtime-cpu-limit"] = (
        all(value.isdecimal() for value in cpu) and 0 < int(cpu[0]) <= int(cpu[1])
    )
    output = Path("/output/.write-probe")
    try:
        output.write_text("synthetic", encoding="utf-8")
        output.unlink()
        checks["runtime-output-writable"] = "rw" in mounts.get("/output", (set(), ""))[0]
    except OSError:
        checks["runtime-output-writable"] = False
    secret = Path("/run/secrets/llm_api_key")
    info = secret.lstat()
    checks["runtime-secret-mount"] = (
        stat.S_ISREG(info.st_mode) and info.st_uid == 10001
        and stat.S_IMODE(info.st_mode) in {0o400, 0o600}
        and "ro" in mounts.get(str(secret), (set(), ""))[0]
    )
    app = Path("/app")
    bootstrap = Path("/opt/psb/entrypoint.py")
    checks["image-minimal-app-files"] = (
        {item.name for item in app.iterdir()} == APP_FILES
        and {item.name for item in bootstrap.parent.iterdir()} == {"entrypoint.py"}
    )
    paths = [app, bootstrap.parent, bootstrap] + [app / name for name in APP_FILES]
    checks["image-root-owned-code"] = all(
        path.lstat().st_uid == 0 and path.lstat().st_gid == 0
        and not path.is_symlink() and path.lstat().st_mode & 0o022 == 0 for path in paths
    )
    expected = json.loads(Path("/probe/expected-sources.json").read_text(encoding="utf-8"))
    checks["image-source-integrity"] = all(
        hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
        for path, digest in expected.items()
    ) and set(expected) == {str(app / name) for name in APP_FILES} | {str(bootstrap)}
    return checks


def main() -> int:
    checks = {}
    try:
        checks.update(runtime_checks())
        # These writable-CWD modules must never shadow the trusted application or bootstrap.
        for name in ("sitecustomize.py", "psb_llm.py"):
            Path("/output", name).write_text("raise RuntimeError('untrusted_cwd_imported')\n", encoding="utf-8")
        environment = dict(os.environ)
        if any(environment.get(name) for name in ("LLM_API_KEY", "OPENAI_API_KEY")):
            raise ValueError("unexpected_inline_secret")
        environment["DATA_DIR"] = "/data"
        checks.update(serve_application(
            [sys.executable, "-I", "-B", "-u", "/opt/psb/entrypoint.py"], environment, Path("/output"),
            Path("/run/secrets/llm_api_key").read_bytes().strip(),
            Path("/probe/server.crt"), Path("/probe/server.key"),
        ))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        # Raw exceptions can include source material or command output; only named checks leave here.
        pass
    complete = set(checks) == CHECK_NAMES
    report = {"checks": {name: bool(checks.get(name, False)) for name in sorted(CHECK_NAMES)}}
    print(json.dumps(report, sort_keys=True))
    return 0 if complete and all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

