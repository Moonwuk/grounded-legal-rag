"""Image scanner reports must retain coverage, block unfixed issues and never publish source secrets."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / ".github/scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load("check_trivy_report")
secrets = load("run_image_secrets")


def image_report():
    return {"SchemaVersion": 2, "ArtifactType": "container_image", "Metadata": {"OS": {"Family": "debian"}},
            "Results": [{"Class": "os-pkgs", "Packages": [{"Name": "libc", "Version": "1"}]}]}


class ImageReportTests(unittest.TestCase):
    def test_vulnerability_artifact_drops_image_environment_history_and_paths(self):
        canary = "PRIVATE_VALUE_" + "MUST_NOT_BE_PUBLISHED"
        report = image_report()
        report["Metadata"]["ImageConfig"] = {"Env": [canary], "History": [canary]}
        report["Results"][0].update(Target="/app/" + canary,
                                    Vulnerabilities=[{"VulnerabilityID": "CVE-2099-0001", "Severity": "HIGH",
                                                      "PkgName": "libc", "Title": canary, "Description": canary}])
        report["Results"][0]["Packages"][0]["FilePath"] = canary
        result = gate.sanitized_image(report)
        self.assertNotIn(canary, json.dumps(result))
        self.assertNotIn("ImageConfig", result["Metadata"])
        self.assertEqual(gate.check(result, "image"), (1, 1))

    def test_unfixed_high_vulnerability_blocks(self):
        report = image_report()
        report["Results"][0]["Vulnerabilities"] = [{"Severity": "HIGH", "FixedVersion": ""}]
        self.assertEqual(gate.check(report, "image"), (1, 1))

    def test_missing_inventory_and_eol_do_not_pass(self):
        for mutation in ("missing_inventory", "eol", "unknown_os", "malformed_inventory", "malformed_findings"):
            report = image_report()
            if mutation == "missing_inventory":
                report["Results"][0]["Packages"] = []
            elif mutation == "eol":
                report["Metadata"]["OS"]["EOSL"] = True
            elif mutation == "unknown_os":
                report["Metadata"]["OS"]["Family"] = "unknown"
            elif mutation == "malformed_inventory":
                report["Results"][0]["Packages"] = [{}]
            else:
                report["Results"][0]["Vulnerabilities"] = {}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.check(report, "image")

    def test_medium_dockerfile_issue_blocks_and_empty_coverage_fails(self):
        report = {"SchemaVersion": 2, "Results": [{"Class": "config", "Type": "dockerfile",
                  "Misconfigurations": [{"Status": "FAIL", "Severity": "MEDIUM"}]}]}
        self.assertEqual(gate.check(report, "config"), (1, 1))
        report["Results"][0]["Misconfigurations"] = []
        with self.assertRaises(ValueError):
            gate.check(report, "config")

    def test_sbom_is_inventory_and_not_a_vulnerability_scan(self):
        self.assertEqual(gate.check({"bomFormat": "CycloneDX", "components": [{"name": "libc"}]}, "sbom"), (1, 0))
        with self.assertRaises(ValueError):
            gate.check({"bomFormat": "CycloneDX", "components": []}, "sbom")


class ImageSecretTests(unittest.TestCase):
    def test_custom_config_is_required_and_preserves_all_three_rules(self):
        config = secrets.secret_config(ROOT / ".gitleaks.toml")
        self.assertEqual({rule["id"] for rule in config["rules"]}, {"psb-" + value for value in secrets.RULE_IDS})
        self.assertNotIn("enable-builtin-rules", config)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(secrets.ScanError):
                secrets.secret_config(Path(directory) / "missing.toml")

    def test_low_secret_and_token_in_filename_are_retained_only_as_safe_metadata(self):
        canary = "PRIVATE_VALUE_" + "MUST_NOT_LEAK"
        report = {"SchemaVersion": 2, "ArtifactType": "container_image", "Results": [
            {"Class": "secret", "Target": "/app/" + canary, "Secrets": [
                {"RuleID": "synthetic-rule", "Severity": "LOW", "StartLine": 1, "EndLine": 1,
                 "Match": canary, "Code": {"Lines": [canary]}}]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report))
            values = secrets.sanitized_report(path, "container_image")
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["Severity"], "LOW")
        self.assertNotIn(canary, json.dumps(values))
        self.assertEqual(set(values[0]), {"RuleID", "Severity", "StartLine", "EndLine", "FileSHA256"})

    def test_invalid_results_cannot_become_an_empty_scan(self):
        for results in ({}, "", [{"Class": "secret", "Target": "file", "Secrets": {}}]):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "report.json"
                path.write_text(json.dumps({"SchemaVersion": 2, "ArtifactType": "container_image", "Results": results}))
                with self.assertRaises(secrets.ScanError):
                    secrets.sanitized_report(path, "container_image")

    def test_cli_cannot_inherit_secret_filters_or_remote_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run(command, **options):
                self.assertIn("--image-config-scanners", command)
                self.assertIn("--secret-config", command)
                self.assertNotIn("--severity", command)
                self.assertFalse(options["shell"])
                self.assertEqual(options["env"]["DOCKER_HOST"], "unix:///var/run/docker.sock")
                self.assertNotIn("DOCKER_CONTEXT", options["env"])
                self.assertFalse(any(key.startswith("TRIVY_") for key in options["env"]))
                path = Path(command[command.index("--output") + 1])
                path.write_text(json.dumps({"SchemaVersion": 2, "ArtifactType": "container_image"}))
                return subprocess.CompletedProcess(command, 0)

            with patch.dict(secrets.os.environ, {"TRIVY_SEVERITY": "CRITICAL", "TRIVY_SKIP_DIRS": "/app",
                                                 "DOCKER_HOST": "tcp://remote.invalid", "DOCKER_CONTEXT": "remote"}):
                with patch.object(secrets.subprocess, "run", side_effect=run):
                    self.assertEqual(secrets.invoke(root / "verified-trivy", "image", "psb-submission:ci",
                                                    root / "config.json", root / "scan"), [])


if __name__ == "__main__":
    unittest.main()
