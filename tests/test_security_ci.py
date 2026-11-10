"""The CI gate must distinguish a clean scan from a missing or failed scan."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/check_codeql.py"
SPEC = importlib.util.spec_from_file_location("check_codeql", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def report(score="7.0", results=None):
    rule = {"id": "py/security-example", "properties": {
        "tags": ["security"], "security-severity": score}}
    return {"version": "2.1.0", "runs": [{
        "tool": {"driver": {"name": "CodeQL", "rules": [rule]}},
        "invocations": [{"executionSuccessful": True}],
        "results": [] if results is None else results,
    }]}


class CodeQLGateTests(unittest.TestCase):
    def invoke(self, payload, raw=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "python.sarif"
            path.write_text(payload if raw else json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = gate.main([directory])
            return code, output.getvalue()

    def test_clean_report_passes(self):
        self.assertEqual(self.invoke(report())[0], 0)

    def test_high_and_critical_block_at_exact_threshold(self):
        for score in ("7.0", "9.8", 10):
            with self.subTest(score=score):
                data = report(score, [{"ruleIndex": 0, "level": "warning"}])
                self.assertEqual(self.invoke(data)[0], 1)

    def test_medium_is_reported_but_does_not_block(self):
        code, output = self.invoke(report("6.9", [{"ruleIndex": 0}]))
        self.assertEqual(code, 0)
        self.assertIn("1 below threshold", output)

    def test_rule_id_without_index_is_resolved(self):
        data = report(results=[{"ruleId": "py/security-example"}])
        self.assertEqual(self.invoke(data)[0], 1)

    def test_unknown_or_conflicting_rule_references_fail_closed(self):
        for result in ({"ruleId": "missing"}, {"ruleIndex": 9},
                       {"ruleIndex": -1}, {"ruleIndex": True}, {},
                       {"ruleIndex": 0, "ruleId": "wrong"},
                       {"ruleIndex": 0, "rule": {"index": 4}}):
            with self.subTest(result=result):
                self.assertEqual(self.invoke(report(results=[result]))[0], 2)

    def test_extension_rule_reference_is_resolved(self):
        data = report()
        run = data["runs"][0]
        run["tool"]["extensions"] = [{"name": "custom-pack", "guid": "extension-guid",
                                        "rules": [copy.deepcopy(run["tool"]["driver"]["rules"][0])]}]
        for component_ref in ({"index": 0, "name": "custom-pack"}, {"guid": "extension-guid"}):
            with self.subTest(reference=component_ref):
                run["results"] = [{"rule": {"index": 0, "toolComponent": component_ref}}]
                self.assertEqual(self.invoke(data)[0], 1)

    def test_invalid_extension_reference_fails_closed(self):
        for reference in ({"index": 3}, {"guid": "unknown"}, {"name": "not-driver"}):
            data = report(results=[{"rule": {"index": 0, "toolComponent": reference}}])
            self.assertEqual(self.invoke(data)[0], 2)

    def test_missing_or_invalid_scan_output_is_not_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(gate.main([directory]), 2)
                self.assertEqual(gate.main([str(Path(directory) / "absent")]), 2)
        for payload in ("{", "null", '{"version":"2.1.0","runs":[]}'):
            self.assertEqual(self.invoke(payload, raw=True)[0], 2)
        for field in ("results", "tool", "invocations"):
            data = report()
            del data["runs"][0][field]
            self.assertEqual(self.invoke(data)[0], 2)
        data = report()
        data["runs"][0]["results"] = {}
        self.assertEqual(self.invoke(data)[0], 2)
        data = report()
        data["runs"][0]["invocations"] = []
        self.assertEqual(self.invoke(data)[0], 2)

    def test_failed_invocation_or_tool_error_blocks(self):
        for invocation in ({"executionSuccessful": False}, {},
                           {"executionSuccessful": "true"},
                           {"executionSuccessful": True, "toolExecutionNotifications": [{"level": "error"}]},
                           {"executionSuccessful": True, "toolConfigurationNotifications": [{"level": "error"}]}):
            data = report()
            data["runs"][0]["invocations"] = [invocation]
            self.assertEqual(self.invoke(data)[0], 2)

    def test_missing_security_score_or_invalid_values_fail_closed(self):
        data = report(results=[{"ruleIndex": 0}])
        del data["runs"][0]["tool"]["driver"]["rules"][0]["properties"]["security-severity"]
        self.assertEqual(self.invoke(data)[0], 2)
        for score in ("NaN", "inf", "high", -1, 10.1, True, None, {}):
            with self.subTest(score=score):
                self.assertEqual(self.invoke(report(score, [{"ruleIndex": 0}]))[0], 2)

    def test_non_security_error_level_blocks(self):
        data = report(results=[{"ruleIndex": 0}])
        rule = data["runs"][0]["tool"]["driver"]["rules"][0]
        rule["properties"] = {}
        rule["defaultConfiguration"] = {"level": "error"}
        self.assertEqual(self.invoke(data)[0], 1)
        data["runs"][0]["results"][0]["level"] = "warning"
        self.assertEqual(self.invoke(data)[0], 0)

    def test_suppressions_and_baseline_do_not_hide_findings(self):
        result = {"ruleIndex": 0, "baselineState": "unchanged",
                  "suppressions": [{"kind": "inSource", "status": "accepted"}]}
        self.assertEqual(self.invoke(report(results=[result]))[0], 1)

    def test_no_rule_metadata_is_not_scan_coverage(self):
        data = report()
        data["runs"][0]["tool"]["driver"]["rules"] = []
        self.assertEqual(self.invoke(data)[0], 2)

    def test_report_messages_are_not_echoed_to_logs(self):
        result = {"ruleIndex": 0, "message": {"text": "PRIVATE_SOURCE_OR_SECRET"}}
        code, output = self.invoke(report(results=[result]))
        self.assertEqual(code, 1)
        self.assertNotIn("PRIVATE_SOURCE_OR_SECRET", output)

    def test_every_report_and_run_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "clean.sarif").write_text(json.dumps(report()), encoding="utf-8")
            (base / "nested").mkdir()
            (base / "nested/high.sarif").write_text(
                json.dumps(report(results=[{"ruleIndex": 0}])), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(gate.main([directory]), 1)
            (base / "nested/high.sarif").write_text("{}", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(gate.main([directory]), 2)


if __name__ == "__main__":
    unittest.main()
