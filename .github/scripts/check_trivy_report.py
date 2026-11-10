"""Reject empty coverage and high/critical findings independently of scanner exit flags."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def check(report, kind):
    if not isinstance(report, dict):
        raise ValueError("report_not_an_object")
    if kind == "sbom":
        components = report.get("components")
        if report.get("bomFormat") != "CycloneDX" or not isinstance(components, list) or not components:
            raise ValueError("empty_or_invalid_cyclonedx")
        if any(not isinstance(component, dict) or not isinstance(component.get("name"), str) or not component["name"]
               for component in components):
            raise ValueError("invalid_cyclonedx_component")
        return len(components), 0
    if report.get("SchemaVersion") != 2 or not isinstance(report.get("Results"), list):
        raise ValueError("invalid_trivy_report")
    results = report["Results"]
    if kind == "config":
        selected = [result for result in results if result.get("Class") == "config" and result.get("Type") == "dockerfile"]
        if len(selected) != 1:
            raise ValueError("dockerfile_coverage_missing")
        checks = selected[0].get("Misconfigurations")
        if not isinstance(checks, list) or not checks:
            raise ValueError("dockerfile_checks_missing")
        if any(not isinstance(item, dict) or item.get("Status") not in {"PASS", "FAIL", "EXCEPTION"}
               or item.get("Severity") not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"} for item in checks):
            raise ValueError("invalid_dockerfile_check")
        return len(checks), sum(item.get("Status") == "FAIL" and item.get("Severity") in {"MEDIUM", "HIGH", "CRITICAL"}
                                for item in checks)
    if report.get("ArtifactType") != "container_image" or report.get("Metadata", {}).get("OS", {}).get("Family") != "debian":
        raise ValueError("supported_image_os_missing")
    if type(report["Metadata"]["OS"].get("EOSL", False)) is not bool or report["Metadata"]["OS"].get("EOSL") is True:
        raise ValueError("end_of_life_image_os")
    os_results = [result for result in results if result.get("Class") == "os-pkgs"]
    packages = 0
    for result in os_results:
        inventory = result.get("Packages")
        if not isinstance(inventory, list) or any(not isinstance(item, dict) or not item.get("Name") or not item.get("Version")
                                                for item in inventory):
            raise ValueError("invalid_os_inventory")
        packages += len(inventory)
    if not os_results or not packages:
        raise ValueError("os_package_inventory_missing")
    blocked = 0
    for result in results:
        findings = result.get("Vulnerabilities", [])
        if findings is None:
            findings = []
        if not isinstance(findings, list):
            raise ValueError("invalid_vulnerability_list")
        for item in findings:
            if not isinstance(item, dict) or item.get("Severity") not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                raise ValueError("invalid_vulnerability")
            blocked += item["Severity"] in {"HIGH", "CRITICAL"}
    return packages, blocked


def sanitized_image(report):
    """Do not publish image Env/history, source snippets or raw file paths."""
    os_metadata = report["Metadata"]["OS"]
    safe = {"SchemaVersion": 2, "ArtifactType": "container_image", "Metadata": {
        "OS": {key: os_metadata[key] for key in ("Family", "Name", "EOSL") if key in os_metadata}}, "Results": []}
    for result in report["Results"]:
        item = {key: result[key] for key in ("Class", "Type") if key in result}
        target = result.get("Target", "")
        if not isinstance(target, str):
            raise ValueError("invalid_result_target")
        item["TargetSHA256"] = hashlib.sha256(target.encode()).hexdigest()
        item["Packages"] = [{key: package[key] for key in ("Name", "Version") if key in package}
                            for package in (result.get("Packages") or [])]
        item["Vulnerabilities"] = [{key: finding[key] for key in
                                    ("VulnerabilityID", "PkgName", "InstalledVersion", "FixedVersion", "Severity", "Status")
                                    if key in finding} for finding in (result.get("Vulnerabilities") or [])]
        safe["Results"].append(item)
    return safe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("config", "image", "sbom"))
    parser.add_argument("report", type=Path)
    parser.add_argument("--sanitized-output", type=Path, help="metadata-only image vulnerability report to publish")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        count, blocked = check(report, args.kind)
        if args.sanitized_output:
            if args.kind != "image":
                raise ValueError("sanitization_requires_image_report")
            args.sanitized_output.parent.mkdir(parents=True, exist_ok=True)
            args.sanitized_output.write_text(json.dumps(sanitized_image(report), indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, AttributeError):
        print("Trivy gate ERROR: invalid report or missing scan coverage")
        return 2
    print(f"Trivy {args.kind} gate: {count} checked item(s); {blocked} blocking finding(s)")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
