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
    return {"SchemaVersion": 2, "ArtifactType": "container_image",
            "Metadata": {"OS": {"Family": "alpine", "Name": "3.24.4"}},
            "Results": [{"Class": "os-pkgs", "Type": "alpine",
                         "Packages": [{"Name": "musl", "Version": "1.2.5-r0"},
                                      {"Name": "zlib", "Version": "1.4-r0"}]}]}


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
        self.assertEqual(gate.check(result, "image"), (2, 1))

    def test_unfixed_high_vulnerability_blocks(self):
        report = image_report()
        report["Results"][0]["Vulnerabilities"] = [{"Severity": "HIGH", "FixedVersion": ""}]
        self.assertEqual(gate.check(report, "image"), (2, 1))

    def test_alpine_branch_and_os_inventory_must_match(self):
        for mutation in ("debian", "old_branch", "edge", "mismatched_result", "duplicate_result"):
            report = image_report()
            if mutation == "debian":
                report["Metadata"]["OS"]["Family"] = "debian"
            elif mutation == "old_branch":
                report["Metadata"]["OS"]["Name"] = "3.23.1"
            elif mutation == "edge":
                report["Metadata"]["OS"]["Name"] = "3.24_alpha20260101"
            elif mutation == "mismatched_result":
                report["Results"][0]["Type"] = "debian"
            else:
                report["Results"].append(report["Results"][0].copy())
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.check(report, "image")

    def test_removed_alpine_runtime_packages_cannot_return(self):
        for name in ("sqlite-libs", "libuuid", "libncursesw", "libpanelw", "ncurses-terminfo-base", "readline"):
            report = image_report()
            report["Results"][0]["Packages"].append({"Name": name, "Version": "1"})
            with self.subTest(package=name), self.assertRaises(ValueError):
                gate.check(report, "image")

    def test_required_runtime_packages_and_reviewed_zlib_fix(self):
        self.assertEqual(gate.check(image_report(), "image"), (2, 0))
        for mutation in ("missing_musl", "missing_zlib", "old_zlib", "unreviewed_zlib", "duplicate_zlib"):
            report = image_report()
            packages = report["Results"][0]["Packages"]
            if mutation == "missing_musl":
                del packages[0]
            elif mutation == "missing_zlib":
                del packages[1]
            elif mutation in {"old_zlib", "unreviewed_zlib"}:
                packages[1]["Version"] = "1.3.2-r0" if mutation == "old_zlib" else "1.4-r1"
            else:
                packages.append({"Name": "zlib", "Version": "1.3.2-r0"})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.check(report, "image")

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
    def test_unexpected_scanner_warning_still_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run(command, **options):
                path = Path(command[command.index("--output") + 1])
                path.write_text(json.dumps({"SchemaVersion": 2, "ArtifactType": "container_image"}))
                options["stderr"].write(b"2026-11-10T00:00:00Z\tWARN\tSynthetic incomplete scan\n")
                return subprocess.CompletedProcess(command, 0)

            with patch.object(secrets.subprocess, "run", side_effect=run):
                with self.assertRaisesRegex(secrets.ScanError, "^unexpected_secret_diagnostics$"):
                    secrets.invoke(root / "verified-trivy", "image", "synthetic-image", root / "config.json", root / "scan")

    def test_custom_config_is_required_and_preserves_all_three_rules(self):
        config = secrets.build_detector_config(ROOT / ".gitleaks.toml")
        self.assertEqual({rule["id"] for rule in config["rules"]}, {"psb-" + value for value in secrets.RULE_IDS})
        self.assertNotIn("enable-builtin-rules", config)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(secrets.ScanError):
                secrets.build_detector_config(Path(directory) / "missing.toml")

    def test_image_inventory_scaffolding_does_not_hide_a_secret_finding(self):
        # Observed with the pinned Trivy binary, both filesystem and image-
        # configuration secret findings follow this inventory scaffolding.
        results = [
            {"Class": "os-pkgs", "Type": "none", "Target": "OS Packages",
             "Packages": [{"Name": "libc", "Version": "1"}]},
            {"Class": "lang-pkgs", "Type": "python-pkg", "Target": "Python",
             "Packages": [{"Name": "pip", "Version": "1"}]},
        ]
        report = {"SchemaVersion": 2, "ArtifactType": "container_image", "Results": results}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            for os_type in ("none", "alpine"):
                results[0]["Type"] = os_type
                path.write_text(json.dumps(report))
                self.assertEqual(secrets.sanitized_report(path, "container_image"), [])
            results.append({"Class": "secret", "Target": "image-config", "Secrets": [
                {"RuleID": "synthetic-rule", "Severity": "UNKNOWN", "StartLine": 1, "EndLine": 1}]})
            path.write_text(json.dumps(report))
            records = secrets.sanitized_report(path, "container_image")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["Severity"], "UNKNOWN")

    def test_inventory_cannot_hide_findings_or_an_unknown_schema(self):
        inventory = {"Class": "os-pkgs", "Type": "none", "Target": "OS Packages",
                     "Packages": [{"Name": "libc", "Version": "1"}]}
        for mutation in ({"Class": "unknown"}, {"Type": "unknown"}, {"Packages": {}},
                         {"Packages": [{}]}, {"Secrets": [{"Severity": "HIGH"}]},
                         {"Vulnerabilities": [{"Severity": "HIGH"}]}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "report.json"
                path.write_text(json.dumps({"SchemaVersion": 2, "ArtifactType": "container_image",
                                            "Results": [{**inventory, **mutation}]}))
                with self.assertRaises(secrets.ScanError):
                    secrets.sanitized_report(path, "container_image")

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

