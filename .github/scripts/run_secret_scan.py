"""Run a verified Gitleaks binary without publishing secret-bearing output.

Exit codes: 0 = completed clean scan, 1 = findings, 2 = incomplete/invalid scan.
Only an exact, count-consistent Gitleaks finding-summary warning is expected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
# Invoke a checksum-verified binary with fixed argv and no shell.
import subprocess  # nosec B404
import tempfile


ROOT = Path(__file__).resolve().parents[2]
FINDING_SUMMARY = re.compile(
    rb"(?:[0-9]{1,2}:[0-9]{2}(?:AM|PM) )?WRN leaks found: ([0-9]+)\r?\n?"
)


def sanitize_report(raw_path):
    """Keep location metadata, retaining valid records even in an invalid report."""
    if not raw_path.is_file():
        return [], None, "missing_report"
    try:
        with raw_path.open(encoding="utf-8") as handle:
            findings = json.load(handle)
    except (OSError, UnicodeError, ValueError, RecursionError):
        return [], None, "invalid_report"
    if not isinstance(findings, list):
        return [], None, "invalid_report"
    sanitized = []
    reason = None
    for finding in findings:
        if not isinstance(finding, dict):
            reason = "invalid_report"
            continue
        rule = finding.get("RuleID")
        file_name = finding.get("File")
        first = finding.get("StartLine")
        last = finding.get("EndLine")
        commit = finding.get("Commit", "")
        if (not isinstance(rule, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", rule)
                or not isinstance(file_name, str) or not file_name
                or type(first) is not int or type(last) is not int or not 0 <= first <= last
                or not isinstance(commit, str)
                or (commit and not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", commit))):
            reason = "invalid_report"
            continue
        # A filename can itself contain a credential. Publish no raw path,
        # even when Gitleaks has redacted the finding's Secret and Match fields.
        path_digest = hashlib.sha256(file_name.encode("utf-8")).hexdigest()
        sanitized.append({"RuleID": rule, "FileSHA256": path_digest, "StartLine": first,
                          "EndLine": last, "Commit": commit})
    return sanitized, len(findings), reason


def expected_diagnostics(stdout_path, stderr_path, return_code, finding_count):
    if stdout_path.stat().st_size:
        return False
    stderr_size = stderr_path.stat().st_size
    if not stderr_size:
        return True
    if return_code != 1 or not finding_count or stderr_size > 128:
        return False
    summary = FINDING_SUMMARY.fullmatch(stderr_path.read_bytes())
    return summary is not None and int(summary.group(1)) == finding_count


def scan(binary, mode, target, config):
    """Raw findings and logs exist only in an external temporary directory."""
    target = Path(target).resolve()
    config = Path(config).resolve()
    binary = Path(binary).resolve()
    if not config.is_file():
        return [], None, None, "missing_configuration"
    if not target.exists() or (mode == "git" and not target.is_dir()):
        return [], None, None, "invalid_target"
    with tempfile.TemporaryDirectory(prefix="psb-gitleaks-") as temporary:
        temp = Path(temporary).resolve()
        if temp == ROOT or ROOT in temp.parents or (target.is_dir() and target in temp.parents):
            return [], None, None, "unsafe_temporary_directory"
        raw_path = temp / "raw.json"
        stdout_path = temp / "stdout.log"
        stderr_path = temp / "stderr.log"
        ignore_dir = temp / "ignore"
        ignore_dir.mkdir()
        command = [str(binary), mode, str(target), "--config", str(config),
                   "--redact=100", "--no-banner", "--no-color", "--log-level=warn",
                   "--timeout=300", "--max-archive-depth=3", "--max-decode-depth=3",
                   "--ignore-gitleaks-allow", "--gitleaks-ignore-path", str(ignore_dir),
                   "--report-format=json", "--report-path", str(raw_path), "--exit-code=1"]
        if mode == "git":
            command.append("--log-opts=--all")
        reason = None
        return_code = None
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            try:
                # CI verifies the binary checksum; arguments are explicit and shell=False.
                process = subprocess.run(  # nosec B603
                    command, stdout=stdout, stderr=stderr, timeout=330,
                    check=False, shell=False,
                )
                return_code = process.returncode
            except subprocess.TimeoutExpired:
                reason = "tool_timeout"
            except OSError:
                reason = "tool_launch_failed"
        sanitized, count, report_error = sanitize_report(raw_path)
        if reason is None:
            if return_code not in (0, 1):
                reason = "unexpected_tool_exit"
            elif report_error:
                reason = report_error
            elif (return_code == 0 and count != 0) or (return_code == 1 and count == 0):
                reason = "inconsistent_exit_and_findings"
            elif not expected_diagnostics(stdout_path, stderr_path, return_code, count):
                reason = "unexpected_diagnostics"
        return sanitized, count, return_code, reason


def write_reports(report_path, records, summary):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = report_path.with_name(report_path.stem + ".summary.json")
    report_path.write_text(json.dumps(records, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", help="path to the checksum-verified Gitleaks executable")
    parser.add_argument("mode", choices=("git", "dir"))
    parser.add_argument("--report", required=True, type=Path, help="sanitized JSON output path")
    parser.add_argument("--target", default=".", type=Path)
    parser.add_argument("--config", default=ROOT / ".gitleaks.toml", type=Path)
    args = parser.parse_args(argv)
    try:
        records, count, tool_code, reason = scan(args.binary, args.mode, args.target, args.config)
    except (OSError, ValueError, RuntimeError):
        records, count, tool_code, reason = [], None, None, "scan_io_error"
    exit_code = 2 if reason else (1 if count else 0)
    status = "error" if reason else ("findings" if count else "clean")
    summary = {"status": status, "reason": reason or "scan_completed", "mode": args.mode,
               "finding_count": count, "sanitized_count": len(records),
               "tool_exit_code": tool_code, "exit_code": exit_code}
    try:
        write_reports(args.report, records, summary)
    except (OSError, ValueError):
        print("Secret scan ERROR: unable_to_write_reports")
        return 2
    # Never echo diagnostics, arbitrary report values, file names or credentials.
    displayed_count = count if count is not None else "unknown"
    print(f"Secret scan: status={status}; findings={displayed_count}; reason={summary['reason']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
