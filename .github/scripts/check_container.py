"""Run isolated container security checks and a synthetic HTTPS submission smoke test."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
# Docker/OpenSSL executables are resolved once; all commands use argv without a shell.
import subprocess  # nosec B404
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / ".github" / "container-tests"
MEMORY = 512 * 1024 * 1024
LOCAL_DOCKER_HOST = "unix:///var/run/docker.sock"
EXPECTED_ENTRYPOINT = ["python", "-I", "-B", "-u", "/opt/psb/entrypoint.py"]
# This names an isolated container tmpfs mount, never a host temporary file.
CONTAINER_TMPFS = "/tmp:rw,noexec,nosuid,nodev,size=33554432,mode=1777"  # nosec B108
APP_FILES = {
    "solution.py", "psb_corpus.py", "psb_retrieval.py", "psb_llm.py", "psb_policy.py",
    "requirements.txt",
}
PROBE_CHECKS = {
    "runtime-user", "runtime-capabilities", "runtime-no-new-privileges", "runtime-seccomp",
    "runtime-root-readonly", "runtime-data-readonly", "runtime-output-writable",
    "runtime-tmpfs", "runtime-network-none", "runtime-memory-limit", "runtime-pids-limit",
    "runtime-cpu-limit", "runtime-secret-mount", "image-minimal-app-files",
    "image-root-owned-code", "image-source-integrity", "https-bootstrap-exit",
    "https-provider-auth", "https-provider-requests", "answer-csv-schema", "answer-csv-id",
    "answer-csv-grounded", "runtime-cwd-import-isolation", "application-log-redaction",
}


class SmokeError(RuntimeError):
    """Messages are fixed diagnostic codes, never raw tool output."""


def execute(arguments: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    # A caller's Docker context must not redirect fixture mounts or CHOWN to another host.
    # Keep DOCKER_CONFIG (including registry authentication) and inherited proxy settings.
    environment = dict(os.environ)
    for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        environment.pop(name, None)
    # Executable and arguments are constructed by this harness; no command-string evaluation.
    return subprocess.run(  # nosec B603
        arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=timeout, env=environment,
    )


def inspected(arguments: list[str]) -> dict:
    process = execute(arguments)
    if process.returncode != 0:
        raise SmokeError("docker_inspect_failed")
    values = json.loads(process.stdout)
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise SmokeError("docker_inspect_invalid")
    return values[0]


def image_checks(info: dict) -> dict[str, bool]:
    config = info.get("Config", {})
    environment = config.get("Env") or []
    return {
        "image-nonroot-user": config.get("User") == "10001:10001",
        "image-workdir": config.get("WorkingDir") == "/output",
        "image-entrypoint": config.get("Entrypoint") == EXPECTED_ENTRYPOINT,
        "image-no-exposed-ports": not config.get("ExposedPorts"),
        "image-no-inline-api-key": not any(
            value.split("=", 1)[0] in {"LLM_API_KEY", "OPENAI_API_KEY"} for value in environment
        ),
    }


def host_limits(info: dict) -> bool:
    host = info.get("HostConfig", {})
    mounts = {item.get("Destination"): item for item in info.get("Mounts", [])}
    security = host.get("SecurityOpt") or []
    return (
        host.get("ReadonlyRootfs") is True and host.get("NetworkMode") == "none"
        and "ALL" in (host.get("CapDrop") or []) and not host.get("CapAdd")
        and any(value in {"no-new-privileges", "no-new-privileges:true"} for value in security)
        and not any("unconfined" in value for value in security)
        and host.get("Privileged") is False and host.get("PidsLimit") == 128
        and host.get("Memory") == MEMORY and host.get("MemorySwap") == MEMORY
        and host.get("NanoCpus") == 1_000_000_000
        and mounts.get("/data", {}).get("RW") is False
        and mounts.get("/output", {}).get("RW") is True
    )


def make_fixtures(base: Path, openssl: str) -> bytes:
    for name in ("data", "probe", "output-success", "output-missing", "output-unsafe"):
        (base / name).mkdir(mode=0o755)
    with (base / "data/questions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "question"])
        writer.writerow(["0001", "Каков срок оплаты по договору С-1/2026?"])
    with zipfile.ZipFile(base / "data/knowledge-base.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("contract.txt", "Договор С-1/2026\n1. Оплата производится в течение 30 календарных дней.\n")
    synthetic = ("fixture-" + hashlib.sha256(b"psb-container-local-https-fixture").hexdigest()).encode()
    for name, mode in (("key-safe", 0o400), ("key-unsafe", 0o644)):
        path = base / name
        path.write_bytes(synthetic)
        path.chmod(mode)
    shutil.copyfile(FIXTURES / "probe.py", base / "probe/probe.py")
    expected = {
        "/app/" + name: hashlib.sha256((ROOT / "prototype" / name).read_bytes()).hexdigest()
        for name in APP_FILES
    }
    expected["/opt/psb/entrypoint.py"] = hashlib.sha256(
        (ROOT / "containers/entrypoint.py").read_bytes()
    ).hexdigest()
    (base / "probe/expected-sources.json").write_text(json.dumps(expected), encoding="utf-8")
    process = execute([
        openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "1",
        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-keyout", str(base / "probe/server.key"), "-out", str(base / "probe/server.crt"),
    ])
    if process.returncode != 0:
        raise SmokeError("synthetic_certificate_generation_failed")
    (base / "probe/server.key").chmod(0o400)
    return synthetic


def change_fixture_owner(docker: list[str], image: str, directory: Path, uid: int, gid: int) -> bool:
    # Only this temporary fixture tree is mounted. Root has CHOWN, no other capabilities,
    # no network, no writable root filesystem, and no Docker socket or host mounts.
    program = (
        "import os,sys\n"
        "uid,gid=map(int,sys.argv[1:])\n"
        "for parent,dirs,files in os.walk('/fixtures',followlinks=False):\n"
        "    for name in dirs+files:\n"
        "        os.chown(os.path.join(parent,name),uid,gid,follow_symlinks=False)\n"
        "    os.chown(parent,uid,gid,follow_symlinks=False)\n"
    )
    process = execute(docker + [
        "run", "--rm", "--network", "none", "--read-only", "--user", "0:0",
        "--workdir", "/", "--cap-drop", "ALL", "--cap-add", "CHOWN",
        "--security-opt", "no-new-privileges:true", "--pids-limit", "32",
        "--memory", "128m", "--cpus", "1",
        "--mount", "type=bind,src=" + str(directory) + ",dst=/fixtures",
        "--entrypoint", "python", image, "-I", "-B", "-c", program, str(uid), str(gid),
    ])
    return process.returncode == 0


def run_case(docker: list[str], image: str, base: Path, case: str, name: str) -> tuple:
    arguments = docker + [
        "run", "--name", name, "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--pids-limit", "128", "--memory", str(MEMORY), "--memory-swap", str(MEMORY),
        "--cpus", "1", "--ulimit", "nofile=256:256",
        "--tmpfs", CONTAINER_TMPFS,
        "--mount", "type=bind,src=" + str(base / "data") + ",dst=/data,readonly",
        "--mount", "type=bind,src=" + str(base / ("output-" + case)) + ",dst=/output",
        "--env", "DATA_DIR=/data", "--env", "LLM_MODEL=fixture-model",
        "--env", "LLM_BASE_URL=https://127.0.0.1:1/v1",
    ]
    if case != "missing":
        secret = "key-safe" if case == "success" else "key-unsafe"
        arguments += ["--mount", "type=bind,src=" + str(base / secret)
                      + ",dst=/run/secrets/llm_api_key,readonly"]
    if case == "success":
        arguments += [
            "--mount", "type=bind,src=" + str(base / "probe") + ",dst=/probe,readonly",
            "--entrypoint", "python", image, "-I", "-B", "-u", "/probe/probe.py",
        ]
    else:
        # Negative cases use the actual image entrypoint, without an override.
        arguments += [image]
    try:
        result = execute(arguments, timeout=90)
        info = inspected(docker + ["container", "inspect", name])
        return result, info
    finally:
        removed = execute(docker + ["container", "rm", "--force", name], timeout=30)
        if removed.returncode != 0:
            raise SmokeError("fixture_container_cleanup_failed")


def run_checks(image: str, records: list[dict]):
    def record(name: str, passed: bool, count: int = 0):
        records.append({"name": name, "status": "passed" if passed else "failed", "count": count})

    docker_binary = shutil.which("docker")
    openssl = shutil.which("openssl")
    if docker_binary is None or openssl is None:
        raise SmokeError("docker_and_openssl_are_required")
    docker = [docker_binary, "--host", LOCAL_DOCKER_HOST]
    info = inspected(docker + ["image", "inspect", image])
    checks = image_checks(info)
    for name, passed in checks.items():
        record(name, passed)
    image_id = info.get("Id", "")
    if not all(checks.values()) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise SmokeError("image_contract_failed")

    with tempfile.TemporaryDirectory(prefix="psb-container-smoke-") as temporary:
        base = Path(temporary) / "fixtures"
        base.mkdir(mode=0o755)
        synthetic = make_fixtures(base, openssl)
        suffix = hashlib.sha256(str(base).encode()).hexdigest()[:12]
        try:
            prepared = change_fixture_owner(docker, image_id, base, 10001, 10001)
            record("fixture-ownership", prepared)
            if not prepared:
                raise SmokeError("fixture_ownership_failed")
            for case in ("success", "missing", "unsafe"):
                result, container = run_case(docker, image_id, base, case, "psb-smoke-" + suffix + "-" + case)
                record(case + "-host-limits", host_limits(container))
                record(case + "-no-secret-output", synthetic not in result.stdout + result.stderr)
                if case == "success":
                    record("hardened-https-smoke-exit", result.returncode == 0)
                    payload = json.loads(result.stdout)
                    observed = payload.get("checks", {}) if isinstance(payload, dict) else {}
                    valid = (
                        isinstance(observed, dict) and set(observed) == PROBE_CHECKS
                        and all(type(value) is bool for value in observed.values())
                    )
                    record("runtime-probe-complete", valid, len(PROBE_CHECKS))
                    for check in sorted(PROBE_CHECKS):
                        record(check, valid and observed[check])
                else:
                    record(case + "-secret-rejected", result.returncode == 2)
                    record(case + "-no-submission", not (base / ("output-" + case) / "submission.csv").exists())
        finally:
            restored = change_fixture_owner(docker, image_id, base, os.getuid(), os.getgid())
            record("fixture-cleanup-ownership", restored)
            if not restored:
                raise SmokeError("fixture_cleanup_ownership_failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="psb-submission:ci")
    parser.add_argument("--report", type=Path, default=Path("reports/container-smoke.json"))
    args = parser.parse_args(argv)
    records: list[dict] = []
    error = None
    try:
        run_checks(args.image, records)
    except SmokeError as exc:
        error = str(exc)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        error = "container_smoke_execution_failed"
    if error:
        records.append({"name": "harness-execution", "status": "failed", "count": 0})
    failed = sum(item["status"] != "passed" for item in records)
    report = {
        "schema_version": 1, "status": "failed" if failed else "passed",
        "synthetic_fixtures_only": True, "external_provider_requests": 0,
        "cases": records, "failed": failed, "total": len(records),
    }
    if error:
        report["error"] = error
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError:
        print("container-smoke: failed (sanitized report could not be written)", file=sys.stderr)
        return 1
    for record in records:
        print(f"{record['name']}: {record['status']} ({record['count']})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
