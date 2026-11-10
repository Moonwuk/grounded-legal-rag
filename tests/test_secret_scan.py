"""A scanner error, warning or inconsistent report must never become a clean run."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/run_secret_scan.py"
SPEC = importlib.util.spec_from_file_location("run_secret_scan", SCRIPT)
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)

CANARY = "DO_NOT_EXPORT_" + "THIS_PRIVATE_VALUE"


def finding():
    return {"RuleID": "fixture-rule", "File": "synthetic.txt", "StartLine": 1, "EndLine": 1,
            "Commit": "a" * 40, "Secret": CANARY, "Match": CANARY,
            "Description": CANARY, "Message": CANARY, "Author": CANARY, "Email": CANARY}


class SecretScanTests(unittest.TestCase):
    def invoke(self, report, code=0, stderr=b"", stdout=b"", failure=None, mode="dir"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            config = root / "gitleaks.toml"
            config.write_text('title = "synthetic test config"\n', encoding="utf-8")
            output = root / "reports/scan.json"
            calls = []

            def run(command, **options):
                calls.append((command, options))
                raw = Path(command[command.index("--report-path") + 1])
                self.assertNotIn(scanner.ROOT, raw.parents)
                self.assertNotIn(target, raw.parents)
                ignore = Path(command[command.index("--gitleaks-ignore-path") + 1])
                self.assertTrue(ignore.is_dir())
                self.assertFalse((ignore / ".gitleaksignore").exists())
                if report is not None:
                    raw.write_text(report if isinstance(report, str) else json.dumps(report), encoding="utf-8")
                options["stdout"].write(stdout)
                options["stderr"].write(stderr)
                if failure:
                    raise failure
                return subprocess.CompletedProcess(command, code)

            logs = io.StringIO()
            with patch.object(scanner.subprocess, "run", side_effect=run):
                with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
                    result = scanner.main([str(root / "verified-gitleaks"), mode, "--report", str(output),
                                           "--target", str(target), "--config", str(config)])
            sanitized = json.loads(output.read_text(encoding="utf-8"))
            summary = json.loads(output.with_name("scan.summary.json").read_text(encoding="utf-8"))
            if calls:
                raw = Path(calls[0][0][calls[0][0].index("--report-path") + 1])
                self.assertFalse(raw.parent.exists(), "raw report and logs must be deleted")
            return result, sanitized, summary, logs.getvalue(), calls

    def test_clean_completed_scan_returns_zero(self):
        result, sanitized, summary, _, _ = self.invoke([])
        self.assertEqual(result, 0)
        self.assertEqual(sanitized, [])
        self.assertEqual(summary["status"], "clean")
        self.assertEqual(summary["finding_count"], 0)

    def test_findings_are_sanitized_and_expected_warning_is_allowed(self):
        result, sanitized, summary, logs, _ = self.invoke(
            [finding()], code=1, stderr=b"11:42AM WRN leaks found: 1\n")
        self.assertEqual(result, 1)
        self.assertEqual(summary["status"], "findings")
        self.assertEqual(summary["finding_count"], 1)
        self.assertEqual(set(sanitized[0]), {"RuleID", "FileSHA256", "StartLine", "EndLine", "Commit"})
        self.assertNotIn(CANARY, json.dumps(sanitized) + json.dumps(summary) + logs)

    def test_token_in_filename_is_hashed_instead_of_published(self):
        token = "sk" + "-" + hashlib.sha256(b"synthetic-filename-unit-fixture").hexdigest()[:32]
        source_path = "nested/" + token + ".txt"
        item = dict(finding(), File=source_path, Secret="REDACTED", Match="REDACTED")
        result, sanitized, summary, logs, _ = self.invoke([item], code=1)
        self.assertEqual(result, 1)
        self.assertNotIn("File", sanitized[0])
        self.assertEqual(sanitized[0]["FileSHA256"], hashlib.sha256(source_path.encode()).hexdigest())
        self.assertNotIn(token, json.dumps(sanitized) + json.dumps(summary) + logs)

    def test_findings_with_quiet_diagnostics_still_fail(self):
        self.assertEqual(self.invoke([finding()], code=1)[0], 1)

    def test_missing_or_malformed_report_never_passes(self):
        for payload in (None, "{", "null", "{}", [None], [{"RuleID": "fixture-rule"}]):
            with self.subTest(payload=payload):
                result, _, summary, _, _ = self.invoke(payload)
                self.assertEqual(result, 2)
                self.assertIn(summary["reason"], {"missing_report", "invalid_report"})

    def test_exit_code_and_findings_must_agree(self):
        for payload, code in (([finding()], 0), ([], 1)):
            result, sanitized, summary, _, _ = self.invoke(payload, code=code)
            self.assertEqual(result, 2)
            self.assertEqual(len(sanitized), len(payload))
            self.assertEqual(summary["reason"], "inconsistent_exit_and_findings")

    def test_tool_errors_preserve_sanitized_findings(self):
        result, sanitized, summary, logs, _ = self.invoke(
            [finding()], code=3, stderr=CANARY.encode())
        self.assertEqual(result, 2)
        self.assertEqual(summary["reason"], "unexpected_tool_exit")
        self.assertEqual(summary["finding_count"], 1)
        self.assertEqual(len(sanitized), 1)
        self.assertNotIn(CANARY, logs)

    def test_archive_skips_and_unrecognized_warnings_fail_closed(self):
        for diagnostic in (b"11:42AM WRN could not inspect archive\n", b"unknown diagnostic\n",
                           b"11:42AM ERR scan failed\n", b"\n"):
            with self.subTest(diagnostic=diagnostic):
                result, _, summary, _, _ = self.invoke([], stderr=diagnostic)
                self.assertEqual(result, 2)
                self.assertEqual(summary["reason"], "unexpected_diagnostics")

    def test_expected_summary_must_be_exact_and_count_consistent(self):
        for diagnostic in (b"11:42AM WRN leaks found: 2\n",
                           b"11:42AM WRN leaks found: 1\n11:42AM WRN skipped archive\n",
                           b"prefix WRN leaks found: 1\n", b"WRN leaks found: 1\n\n"):
            with self.subTest(diagnostic=diagnostic):
                result, sanitized, summary, _, _ = self.invoke([finding()], code=1, stderr=diagnostic)
                self.assertEqual(result, 2)
                self.assertEqual(summary["reason"], "unexpected_diagnostics")
                self.assertEqual(len(sanitized), 1)

    def test_nonempty_stdout_is_not_a_quiet_success(self):
        result, _, summary, logs, _ = self.invoke([], stdout=CANARY.encode())
        self.assertEqual(result, 2)
        self.assertEqual(summary["reason"], "unexpected_diagnostics")
        self.assertNotIn(CANARY, logs)

    def test_timeout_retains_partial_findings_and_does_not_leak_exception_output(self):
        error = subprocess.TimeoutExpired([CANARY], timeout=330, output=CANARY, stderr=CANARY)
        result, sanitized, summary, logs, _ = self.invoke([finding()], failure=error)
        self.assertEqual(result, 2)
        self.assertEqual(summary["reason"], "tool_timeout")
        self.assertEqual(summary["finding_count"], 1)
        self.assertEqual(len(sanitized), 1)
        self.assertNotIn(CANARY, logs)

    def test_launch_failure_is_reported_without_exception_details(self):
        result, _, summary, logs, _ = self.invoke(None, failure=OSError(CANARY))
        self.assertEqual(result, 2)
        self.assertEqual(summary["reason"], "tool_launch_failed")
        self.assertIsNone(summary["finding_count"])
        self.assertNotIn(CANARY, logs)

    def test_invalid_metadata_is_rejected_but_valid_records_are_kept(self):
        invalid = dict(finding(), StartLine=True)
        result, sanitized, summary, _, _ = self.invoke([finding(), invalid], code=1)
        self.assertEqual(result, 2)
        self.assertEqual(summary["reason"], "invalid_report")
        self.assertEqual(summary["finding_count"], 2)
        self.assertEqual(summary["sanitized_count"], 1)
        self.assertEqual(len(sanitized), 1)

    def test_flags_do_not_allow_baselines_or_inline_skips(self):
        for mode in ("git", "dir"):
            with self.subTest(mode=mode):
                _, _, _, _, calls = self.invoke([], mode=mode)
                command, options = calls[0]
                self.assertFalse(options["shell"])
                self.assertEqual(options["timeout"], 330)
                for flag in ("--redact=100", "--no-banner", "--no-color", "--log-level=warn",
                             "--timeout=300", "--max-archive-depth=3", "--max-decode-depth=3",
                             "--ignore-gitleaks-allow", "--exit-code=1"):
                    self.assertIn(flag, command)
                self.assertNotIn("--baseline-path", command)
                self.assertEqual("--log-opts=--all" in command, mode == "git")


if __name__ == "__main__":
    unittest.main()
