"""Fail-closed Trivy image-secret scan with an engine preflight and private raw output."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
# CI checks the binary checksum; every command uses explicit arguments and no shell.
import subprocess  # nosec B404
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parents[2]
RULE_IDS = {"ai-sk32-key-candidate", "openrouter-api-key", "groq-api-key"}
LEVELS = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}


class ScanError(RuntimeError):
    """Only fixed reason codes, never scanner output or source text."""


def build_detector_config(path):
    """Build public detector rules from committed regexes, never credential values."""
    if not path.is_file():
        raise ScanError("missing_custom_rules")
    with path.open("rb") as handle:
        source = tomllib.load(handle)
    rules = source.get("rules")
    if not isinstance(rules, list) or {rule.get("id") for rule in rules} != RULE_IDS or len(rules) != 3:
        raise ScanError("unexpected_custom_rules")
    converted = []
    for rule in rules:
        capture_number = rule.get("secretGroup")
        if capture_number != 1 or not isinstance(rule.get("regex"), str):
            raise ScanError("invalid_custom_rule")
        pattern = re.sub(r"(?<!\\)\((?!\?)", "(?P<secret>", rule["regex"], count=1)
        compiled = re.compile(pattern)
        if compiled.groups != 1 or set(compiled.groupindex) != {"secret"}:
            raise ScanError("invalid_custom_capture")
        keywords = rule.get("keywords")
        if not isinstance(keywords, list) or not keywords or any(not isinstance(key, str) for key in keywords):
            raise ScanError("invalid_custom_keywords")
        # Distinct IDs prove the custom configuration loaded even if built-ins
        # later learn the same providers. Omitting enable-builtin-rules retains all defaults.
        converted.append({"id": "psb-" + rule["id"], "category": "AI API token candidate",
                          "title": "Potential credential; validity is not checked", "severity": "HIGH",
                          "regex": pattern, "secret-group-name": "secret", "keywords": keywords})
    return {"rules": converted}


def sanitized_report(path, artifact_type):
    with path.open(encoding="utf-8") as handle:
        report = json.load(handle)
    if not isinstance(report, dict) or report.get("SchemaVersion") != 2 or report.get("ArtifactType") != artifact_type:
        raise ScanError("invalid_secret_report")
    results = report.get("Results", [])
    if results is None:
        results = []
    if not isinstance(results, list):
        raise ScanError("invalid_secret_results")
    records = []
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("Target"), str):
            raise ScanError("invalid_secret_result")
        if result.get("Class") != "secret":
            # Trivy 0.76 JSON includes package inventory even for secret-only
            # image scans. Accept only the observed inventory schema: a
            # Secrets/other finding field here must fail, never be skipped.
            inventory_types = {"os-pkgs": {"none", "alpine"}, "lang-pkgs": {"python-pkg"}}
            packages = result.get("Packages")
            if (artifact_type != "container_image" or result.get("Class") not in inventory_types
                    or result.get("Type") not in inventory_types[result["Class"]]
                    or set(result) != {"Class", "Type", "Target", "Packages"}
                    or not isinstance(packages, list)
                    or any(not isinstance(package, dict)
                           or not isinstance(package.get("Name"), str) or not package["Name"]
                           or not isinstance(package.get("Version"), str) or not package["Version"]
                           for package in packages)):
                raise ScanError("invalid_secret_inventory")
            continue
        findings = result.get("Secrets", [])
        if findings is None:
            findings = []
        if not isinstance(findings, list):
            raise ScanError("invalid_secret_findings")
        for finding in findings:
            if not isinstance(finding, dict):
                raise ScanError("invalid_secret_finding")
            rule = finding.get("RuleID")
            severity = finding.get("Severity")
            first, last = finding.get("StartLine"), finding.get("EndLine")
            if (not isinstance(rule, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", rule) is None
                    or severity not in LEVELS or type(first) is not int or type(last) is not int
                    or not 0 <= first <= last):
                raise ScanError("invalid_secret_metadata")
            records.append({"RuleID": rule, "Severity": severity, "StartLine": first, "EndLine": last,
                            "FileSHA256": hashlib.sha256(result["Target"].encode()).hexdigest()})
    return records


def invoke(binary, mode, target, config, directory):
    directory.mkdir()
    report = directory / "raw.json"
    stdout_path, stderr_path = directory / "stdout.log", directory / "stderr.log"
    command = [str(binary), mode, "--config", "", "--ignorefile", "", "--secret-config", str(config),
               "--scanners", "secret", "--exit-code", "1", "--timeout", "5m", "--no-progress",
               # SBOM package interpretation is unrelated to a secret-only scan.
               # Keep raw file scanning, including SBOM JSON, enabled. The
               # separate vulnerability and SBOM jobs retain this analyzer.
               "--disabled-analyzers", "sbom",
               "--skip-version-check", "--offline-scan", "--skip-db-update", "--skip-java-db-update",
               "--cache-dir", str(directory / "cache"), "--format", "json", "--output", str(report)]
    if mode == "image":
        command += ["--image-src", "docker", "--image-config-scanners", "secret"]
    command.append(str(target))
    environment = {key: value for key, value in os.environ.items() if not key.startswith("TRIVY_")}
    for key in ("DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        environment.pop(key, None)
    environment["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            # Executable verified by CI; no command interpolation or shell evaluation.
            process = subprocess.run(  # nosec B603
                command, stdout=stdout, stderr=stderr, env=environment, shell=False, check=False, timeout=330,
            )
        except subprocess.TimeoutExpired as exc:
            raise ScanError("secret_scan_timeout") from exc
        except OSError as exc:
            raise ScanError("secret_scanner_unavailable") from exc
    if process.returncode not in (0, 1):
        raise ScanError("secret_scanner_failed")
    records = sanitized_report(report, "container_image" if mode == "image" else "filesystem")
    if (process.returncode == 0 and records) or (process.returncode == 1 and not records):
        raise ScanError("inconsistent_secret_scan")
    # Trivy INFO lines are expected. Warnings, errors, unknown diagnostics and
    # unsolicited stdout must not be mistaken for a completed clean scan.
    if stdout_path.stat().st_size:
        raise ScanError("unexpected_secret_diagnostics")
    diagnostics = stderr_path.read_bytes().splitlines()
    if any(line and not re.fullmatch(rb"[0-9TZ:.+\-]+[ \t]+INFO[ \t]+[^\r\n]*", line) for line in diagnostics):
        raise ScanError("unexpected_secret_diagnostics")
    return records


def preflight(binary, config, directory):
    fixtures = directory / "probes"
    fixtures.mkdir()
    digest = lambda label: hashlib.sha256(("synthetic-probe-" + label).encode()).hexdigest()
    values = {
        "ai-sk32-key-candidate": "sk" + "-" + digest("sk32")[:32],
        "openrouter-api-key": "sk" + "-or-v1-" + digest("router"),
        "groq-api-key": "gsk" + "_" + digest("groq")[:52],
    }
    for index, token in enumerate(values.values()):
        (fixtures / f"probe-{index}.txt").write_text(token, encoding="utf-8")
    sbom_token = "sk" + "-" + digest("sbom")[:32]
    sbom_path = fixtures / "probe.cdx.json"
    sbom_path.write_text(json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "components": [{"type": "library", "name": "synthetic-library", "version": "1",
                        "properties": [{"name": "synthetic-credential", "value": sbom_token}]}]}), encoding="utf-8")
    records = invoke(binary, "fs", fixtures, config, directory / "preflight")
    found = {record["RuleID"] for record in records}
    if not {"psb-" + rule for rule in RULE_IDS}.issubset(found):
        raise ScanError("custom_secret_rules_not_exercised")
    sbom_hash = hashlib.sha256(str(sbom_path).encode()).hexdigest()
    # Trivy filesystem targets may be absolute or relative to the scan root.
    sbom_hashes = {sbom_hash, hashlib.sha256(sbom_path.name.encode()).hexdigest()}
    if not any(record["RuleID"] == "psb-ai-sk32-key-candidate" and record["FileSHA256"] in sbom_hashes
               for record in records):
        raise ScanError("sbom_file_secret_not_exercised")
    return 4


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--config", default=ROOT / ".gitleaks.toml", type=Path)
    args = parser.parse_args(argv)
    records, checks, reason = [], 0, None
    try:
        configuration = build_detector_config(args.config)
        with tempfile.TemporaryDirectory(prefix="psb-image-secrets-") as temporary:
            base = Path(temporary).resolve()
            if base == ROOT or ROOT in base.parents:
                raise ScanError("unsafe_secret_temporary_directory")
            config = base / "trivy-secrets.json"
            config.write_text(json.dumps(configuration), encoding="utf-8")
            checks = preflight(args.binary.resolve(), config, base)
            records = invoke(args.binary.resolve(), "image", args.image, config, base / "image")
    except ScanError as exc:
        reason = str(exc)
    except (OSError, ValueError, TypeError, AttributeError):
        reason = "invalid_or_unavailable_secret_scan"
    status = "error" if reason else ("findings" if records else "clean")
    count = None if reason else len(records)
    result = {"status": status, "reason": reason or "scan_completed", "preflight_checks": checks,
              "finding_count": count, "findings": records,
              "scope": "Trivy application image files and image configuration; built-in exclusions apply"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Image secrets: {status}; preflight={checks}; findings={count}; reason={result['reason']}")
    return 2 if reason else (1 if records else 0)


if __name__ == "__main__":
    raise SystemExit(main())

