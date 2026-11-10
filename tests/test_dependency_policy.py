"""Regression tests for the non-executing runtime dependency contract."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/check_dependencies.py"
SPEC = importlib.util.spec_from_file_location("check_dependencies", SCRIPT)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)
HASH = "--hash=sha256:" + "a" * 64


class DependencyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runtime = self.root / "prototype"
        self.runtime.mkdir()
        (self.runtime / "requirements.txt").write_text("# Standard library only.\n", encoding="utf-8")
        (self.runtime / "solution.py").write_text("import json\nfrom pathlib import Path\n", encoding="utf-8")

    def test_stdlib_report_and_actions_output_without_importing_runtime(self):
        (self.runtime / "solution.py").write_text(
            "import json\nfrom helper import answer\nfrom .local import value\nraise RuntimeError('must not execute')\n",
            encoding="utf-8",
        )
        (self.runtime / "helper.py").write_text("answer = 42\n", encoding="utf-8")
        output = self.root / "github-output"
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), redirect_stdout(io.StringIO()):
            self.assertEqual(policy.main(["--root", str(self.root)]), 0)
        report = json.loads((self.root / "reports/runtime-dependencies.json").read_text())
        self.assertEqual(report["status"], "stdlib_only")
        self.assertFalse(report["has_dependencies"])
        self.assertEqual(report["foreign_imports"], {})
        self.assertEqual(output.read_text(), "has_dependencies=false\n")

    def test_third_party_import_with_empty_requirements_fails(self):
        (self.runtime / "solution.py").write_text("import requests\n", encoding="utf-8")
        with self.assertRaisesRegex(policy.PolicyError, "Third-party imports.*requests"):
            policy.inspect_runtime(self.root)

    def test_pinned_hashed_direct_and_transitive_inventory(self):
        (self.runtime / "requirements.txt").write_text("example-pkg==1.2.3\n", encoding="utf-8")
        (self.runtime / "requirements.lock").write_text(
            f"example-pkg==1.2.3 \\\n    {HASH} \\\n    --hash=sha256:{'b' * 64}\n# via example-pkg\ntransitive-pkg==2.0 {HASH}\n",
            encoding="utf-8",
        )
        result = policy.inspect_runtime(self.root)
        self.assertEqual(result["status"], "pinned_dependencies")
        self.assertTrue(result["has_dependencies"])
        self.assertEqual(result["locked_dependencies"], {"example-pkg": "1.2.3", "transitive-pkg": "2.0"})
        self.assertFalse(result["lock_closure_verified"])

    def test_requirement_directives_ranges_urls_markers_extras_and_noncanonical_names_rejected(self):
        invalid = [
            "--extra-index-url https://example.invalid/simple",
            "-r other.txt", "example>=1.0", "example @ https://example.invalid/p.whl",
            "example==1.0;python_version>'3'", "example[extra]==1.0", "Example_Pkg==1.0",
            "example==1.0#fragment",
        ]
        for entry in invalid:
            with self.subTest(entry=entry):
                (self.runtime / "requirements.txt").write_text(entry + "\n", encoding="utf-8")
                with self.assertRaises(policy.PolicyError):
                    policy.inspect_runtime(self.root)

    def test_lock_missing_unhashed_or_mismatched_fails(self):
        (self.runtime / "requirements.txt").write_text("example==1.0\n", encoding="utf-8")
        with self.assertRaisesRegex(policy.PolicyError, "require.*requirements.lock"):
            policy.inspect_runtime(self.root)
        for entry in ["example==1.0", f"example==2.0 {HASH}", f"other==1.0 {HASH}", "example==1.0 --hash=sha256:abc"]:
            with self.subTest(entry=entry):
                (self.runtime / "requirements.lock").write_text(entry + "\n", encoding="utf-8")
                with self.assertRaises(policy.PolicyError):
                    policy.inspect_runtime(self.root)

    def test_lock_rejects_extra_options_duplicates_and_truncated_continuation(self):
        (self.runtime / "requirements.txt").write_text("example==1.0\n", encoding="utf-8")
        invalid = [
            f"example==1.0 {HASH} --index-url=https://example.invalid\n",
            f"example==1.0 {HASH}\nexample==1.0 {HASH}\n",
            "example==1.0 \\\n",
            f"example==1.0 {HASH}\n-r other.txt\n",
        ]
        for entry in invalid:
            with self.subTest(entry=entry):
                (self.runtime / "requirements.lock").write_text(entry, encoding="utf-8")
                with self.assertRaises(policy.PolicyError):
                    policy.inspect_runtime(self.root)

    def test_incomplete_runtime_scope_and_stale_lock_fail(self):
        (self.runtime / "requirements.lock").write_text(f"example==1.0 {HASH}\n", encoding="utf-8")
        with self.assertRaisesRegex(policy.PolicyError, "stale lock"):
            policy.inspect_runtime(self.root)
        (self.runtime / "requirements.lock").unlink()
        (self.runtime / "solution.py").write_text("def broken(\n", encoding="utf-8")
        with self.assertRaisesRegex(policy.PolicyError, "invalid Python syntax"):
            policy.inspect_runtime(self.root)
        (self.runtime / "solution.py").unlink()
        with self.assertRaisesRegex(policy.PolicyError, "no Python source"):
            policy.inspect_runtime(self.root)

    def test_failure_does_not_publish_success_output(self):
        (self.runtime / "requirements.txt").unlink()
        output = self.root / "github-output"
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), redirect_stderr(io.StringIO()):
            self.assertEqual(policy.main(["--root", str(self.root)]), 1)
        self.assertFalse(output.exists())
        self.assertFalse((self.root / "reports/runtime-dependencies.json").exists())


if __name__ == "__main__":
    unittest.main()
