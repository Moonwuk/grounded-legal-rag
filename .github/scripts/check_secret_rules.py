#!/usr/bin/env python3
"""Exercise Gitleaks with synthetic fixtures; never print keys or raw scan logs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
# Fixed argv only, no shell; binaries are verified by CI before this harness.
import subprocess  # nosec B404
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]


class HarnessError(Exception):
    """A sanitized harness failure, without captured subprocess output."""


def generated(label: str, length: int, alphabet: str = "0123456789abcdef") -> str:
    """Deterministic test data, unrelated to credentials or random number APIs."""
    output = []
    counter = 0
    while len(output) < length:
        digest = hashlib.sha256(f"synthetic-fixture:{label}:{counter}".encode()).digest()
        output.extend(alphabet[value % len(alphabet)] for value in digest)
        counter += 1
    return "".join(output[:length])


def execute(argv: list[str], *, cwd: Path | None = None, env: dict | None = None):
    # Arguments are fixed by this harness; synthetic values are written to files,
    # never passed on the command line. stdout/stderr remain private in memory.
    return subprocess.run(  # nosec B603
        argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=180,
    )


def scan(binary: Path, config: Path, ignore: Path, target: Path, report: Path, *, history=False):
    argv = [
        str(binary), "git" if history else "dir", str(target),
        "--config", str(config), "--redact=100", "--no-banner",
        "--report-format=json", "--report-path", str(report), "--timeout=120",
        "--max-archive-depth=3", "--max-decode-depth=3",
        "--ignore-gitleaks-allow", "--gitleaks-ignore-path", str(ignore),
    ]
    if history:
        argv.append("--log-opts=--all")
    result = execute(argv)
    try:
        findings = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HarnessError("scanner report is absent or invalid") from exc
    if not isinstance(findings, list) or any(not isinstance(item, dict) for item in findings):
        raise HarnessError("scanner report has an unexpected structure")
    return result.returncode, findings


def archive_bytes(name: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


def run_checks(binary: Path, config: Path, records: list[dict]):
    def record(name: str, passed: bool, count: int = 0):
        records.append({"name": name, "status": "passed" if passed else "failed", "finding_count": count})

    version = execute([str(binary), "version"])
    correct_version = version.returncode == 0 and version.stdout.strip() == b"8.30.1"
    record("scanner-version-8.30.1", correct_version)
    if not correct_version:
        raise HarnessError("expected the CI-verified Gitleaks 8.30.1 binary")
    if not config.is_file():
        raise HarnessError("Gitleaks configuration is missing")

    with tempfile.TemporaryDirectory(prefix="psb-secret-rule-tests-") as temporary:
        base = Path(temporary)
        positive = base / "positive"
        negative = base / "negative"
        ignore = base / "empty-ignore"
        for directory in (positive, negative, ignore):
            directory.mkdir()
        (ignore / ".gitleaksignore").write_text("", encoding="utf-8")
        prefix = "sk" + "-"
        tokens = {
            "sk32": (prefix + generated("sk32", 32), "ai-sk32-key-candidate"),
            "openrouter": (prefix + "or-v1-" + generated("openrouter", 64), "openrouter-api-key"),
            "groq": ("gsk" + "_" + generated("groq", 52, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), "groq-api-key"),
        }
        expected = []

        def fixture(name: str, contents: str, rule: str):
            (positive / name).write_text(contents, encoding="utf-8")
            expected.append((name, rule))

        for label, (token, rule) in tokens.items():
            fixture(f"{label}-standalone-eof.txt", token, rule)
            fixture(f"{label}-env.txt", f"API_KEY={token}\n", rule)
            fixture(f"{label}-json.txt", json.dumps({"api_key": token}), rule)
            fixture(f"{label}-bearer.txt", "Authorization: Bearer " + token + "\n", rule)
            fixture(f"{label}-base64.txt", base64.b64encode(token.encode()).decode(), rule)
            fixture(f"{label}-hex.txt", token.encode().hex(), rule)
            fixture(f"{label}-percent.txt", "".join(f"%{value:02x}" for value in token.encode()), rule)
            invalid = {
                "short": token[:-1], "long": token + "7",
                "embedded-left": "identifier_" + token,
                "embedded-right": token + "_identifier",
                "embedded-hyphen": "identifier-" + token + "-suffix",
            }
            for kind, value in invalid.items():
                (negative / f"{label}-{kind}.txt").write_text(value, encoding="utf-8")

        fixture("sk32-nonhex.txt", prefix + generated("nonhex", 32, "ghijklmnopqrstuvwxyz0123456789"), "ai-sk32-key-candidate")
        fixture("builtin-openai.txt", prefix + generated("openai-left", 20) + "T3BlbkFJ" + generated("openai-right", 20), "openai-api-key")
        fixture("builtin-anthropic.txt", prefix + "ant-api03-" + generated("anthropic", 93) + "AA", "anthropic-api-key")
        (negative / "placeholder-names.txt").write_text(
            "DEEPSEEK_API_KEY=YOUR_DEEPSEEK_API_KEY\nOPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY\n"
            "GROQ_API_KEY=YOUR_GROQ_API_KEY\n", encoding="utf-8",
        )
        archive_token, archive_rule = tokens["sk32"]
        inner_zip = archive_bytes("secret.txt", archive_token.encode())
        (positive / "fixture.zip").write_bytes(inner_zip)
        expected.append(("fixture.zip!secret.txt", archive_rule))
        (positive / "nested.zip").write_bytes(archive_bytes("inner.zip", inner_zip))
        expected.append(("nested.zip!inner.zip!secret.txt", archive_rule))

        code, findings = scan(binary, config, ignore, positive, base / "positive.json")
        record("positive-scan-exit-code", code == 1, len(findings))
        for path, rule in expected:
            matches = [item for item in findings if item.get("RuleID") == rule and str(item.get("File", "")).replace("\\", "/").endswith("/" + path)]
            record(path, bool(matches), len(matches))

        code, findings = scan(binary, config, ignore, negative, base / "negative.json")
        record("negative-boundaries-and-placeholders", code == 0 and not findings, len(findings))

        git = shutil.which("git")
        if git is None:
            raise HarnessError("git is required for the deleted-archive regression")
        history = base / "history"
        history.mkdir()
        git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        git_env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        common = [git, "-c", "core.hooksPath=" + os.devnull, "-c", "commit.gpgsign=false",
                  "-c", "user.name=Security fixture", "-c", "user.email=fixture@example.invalid"]

        def git_command(*arguments: str):
            if execute(common + list(arguments), cwd=history, env=git_env).returncode != 0:
                raise HarnessError("temporary git history setup failed")

        git_command("init", "--quiet", "--template=" + str(ignore))
        (history / "removed-fixture.zip").write_bytes(inner_zip)
        git_command("add", "--", "removed-fixture.zip")
        git_command("commit", "--quiet", "-m", "Add synthetic archive fixture")
        git_command("rm", "--quiet", "--", "removed-fixture.zip")
        git_command("commit", "--quiet", "-m", "Remove synthetic archive fixture")
        code, findings = scan(binary, config, ignore, history, base / "history.json", history=True)
        matches = [item for item in findings if item.get("RuleID") == archive_rule
                   and str(item.get("File", "")).endswith("removed-fixture.zip!secret.txt")
                   and item.get("Commit")]
        record("deleted-archive-in-git-history", code == 1 and bool(matches), len(matches))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, help="Path to the CI-verified Gitleaks 8.30.1 executable")
    parser.add_argument("--config", type=Path, default=ROOT / ".gitleaks.toml")
    parser.add_argument("--report", type=Path, default=Path("reports/secret-rule-tests.json"))
    args = parser.parse_args(argv)
    records: list[dict] = []
    error = None
    try:
        run_checks(args.binary.resolve(strict=True), args.config.resolve(), records)
    except HarnessError as exc:
        error = str(exc)
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        error = "harness execution failed; no raw scanner output is published"
    if error:
        records.append({"name": "harness-execution", "status": "failed", "finding_count": 0})
    failed = sum(item["status"] != "passed" for item in records)
    result = {"schema_version": 1, "status": "failed" if failed else "passed",
              "synthetic_fixtures_only": True, "cases": records, "failed": failed, "total": len(records)}
    if error:
        result["error"] = error
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except OSError:
        print("secret-rule-tests: failed (report could not be written)", file=sys.stderr)
        return 1
    for item in records:
        print(f"{item['name']}: {item['status']} ({item['finding_count']} findings)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
