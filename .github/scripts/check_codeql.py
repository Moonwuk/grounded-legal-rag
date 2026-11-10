"""Fail closed on incomplete CodeQL SARIF or high/critical security findings.

Exit codes: 0 = gate passed, 1 = blocking findings, 2 = invalid/incomplete scan.
This deliberately does not honour SARIF suppressions or baselineState: they do
not constitute reviewed, expiring exceptions to the repository security gate.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


class ReportError(ValueError):
    """The report cannot establish a successful, complete scan."""


def object_value(value, label):
    if not isinstance(value, dict):
        raise ReportError(f"{label} must be an object")
    return value


def array_value(value, label):
    if not isinstance(value, list):
        raise ReportError(f"{label} must be an array")
    return value


def indexed(items, index, label):
    if type(index) is not int or not 0 <= index < len(items):
        raise ReportError(f"invalid {label} index")
    return items[index]


def check_invocations(run):
    invocations = array_value(run.get("invocations"), "invocations")
    if not invocations:
        raise ReportError("report has no completed invocation")
    for invocation in invocations:
        invocation = object_value(invocation, "invocation")
        if invocation.get("executionSuccessful") is not True:
            raise ReportError("CodeQL invocation did not complete successfully")
        for field in ("toolExecutionNotifications", "toolConfigurationNotifications"):
            for notification in array_value(invocation.get(field, []), field):
                notification = object_value(notification, "notification")
                level = notification.get("level", "warning")
                if level not in ("none", "note", "warning", "error"):
                    raise ReportError("invalid notification level")
                if level == "error":
                    raise ReportError("CodeQL reported a tool/configuration error")


def components_for(run):
    tool = object_value(run.get("tool"), "tool")
    driver = object_value(tool.get("driver"), "tool.driver")
    if driver.get("name") != "CodeQL":
        raise ReportError("expected a CodeQL report")
    components = [driver] + array_value(tool.get("extensions", []), "extensions")
    rule_count = 0
    for component in components:
        component = object_value(component, "tool component")
        rules = array_value(component.get("rules", []), "component.rules")
        identifiers = set()
        for rule in rules:
            rule = object_value(rule, "rule")
            identifier = rule.get("id")
            if not isinstance(identifier, str) or not identifier or identifier in identifiers:
                raise ReportError("missing or duplicate rule identifier")
            identifiers.add(identifier)
        rule_count += len(rules)
    if not rule_count:
        raise ReportError("report contains no rule metadata")
    return components


def result_rule(result, components):
    reference = object_value(result.get("rule", {}), "result.rule")
    component_ref = object_value(reference.get("toolComponent", {}), "toolComponent")
    if "index" in component_ref:
        component = indexed(components[1:], component_ref["index"], "tool component")
    elif "guid" in component_ref:
        matches = [c for c in components if c.get("guid") == component_ref["guid"]]
        if len(matches) != 1:
            raise ReportError("unknown or ambiguous tool component")
        component = matches[0]
    else:
        component = components[0]
    for field in ("guid", "name"):
        if field in component_ref and component_ref[field] != component.get(field):
            raise ReportError("inconsistent tool component reference")

    rules = component.get("rules", [])
    indices = []
    identifiers = []
    for owner, field in ((result, "ruleIndex"), (reference, "index")):
        if field in owner:
            indices.append(owner[field])
    for owner, field in ((result, "ruleId"), (reference, "id")):
        if field in owner:
            identifiers.append(owner[field])
    if any(not isinstance(value, str) or not value for value in identifiers):
        raise ReportError("invalid result rule identifier")
    if indices:
        resolved = [indexed(rules, index, "rule") for index in indices]
        rule = resolved[0]
        if any(other is not rule for other in resolved):
            raise ReportError("inconsistent result rule indices")
    elif identifiers:
        matches = [rule for rule in rules if rule["id"] == identifiers[0]]
        if len(matches) != 1:
            raise ReportError("result references an unknown rule")
        rule = matches[0]
    else:
        raise ReportError("result has no rule reference")
    if any(identifier != rule["id"] for identifier in identifiers):
        raise ReportError("inconsistent result rule identifier")
    return rule


def is_blocking(result, rule):
    properties = object_value(rule.get("properties", {}), "rule.properties")
    tags = array_value(properties.get("tags", []), "rule tags")
    if any(not isinstance(tag, str) for tag in tags):
        raise ReportError("invalid rule tags")
    configuration = object_value(rule.get("defaultConfiguration", {}), "defaultConfiguration")
    level = result.get("level", configuration.get("level", "warning"))
    if level not in ("none", "note", "warning", "error"):
        raise ReportError("invalid finding level")
    if "security-severity" not in properties:
        if "security" in tags:
            raise ReportError("security rule has no security-severity")
        return level == "error"
    raw_score = properties["security-severity"]
    if isinstance(raw_score, bool) or not isinstance(raw_score, (str, int, float)):
        raise ReportError("invalid security-severity")
    try:
        score = float(raw_score)
    except ValueError as exc:
        raise ReportError("invalid security-severity") from exc
    if not math.isfinite(score) or not 0 <= score <= 10:
        raise ReportError("security-severity must be between 0 and 10")
    return score >= 7.0


def check_directory(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ReportError("SARIF output directory is missing")
    paths = sorted(directory.rglob("*.sarif"))
    if not paths:
        raise ReportError("no SARIF files were produced")
    total = blocked = 0
    for path in paths:
        if path.is_symlink():
            raise ReportError("SARIF reports must be regular files")
        with path.open(encoding="utf-8") as handle:
            report = object_value(json.load(handle), "report")
        if report.get("version") != "2.1.0":
            raise ReportError("unsupported SARIF version")
        runs = array_value(report.get("runs"), "runs")
        if not runs:
            raise ReportError("report has no analysis runs")
        for run in runs:
            run = object_value(run, "run")
            check_invocations(run)
            components = components_for(run)
            for result in array_value(run.get("results"), "results"):
                result = object_value(result, "result")
                total += 1
                blocked += is_blocking(result, result_rule(result, components))
    return len(paths), total, blocked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="directory containing CodeQL .sarif output")
    args = parser.parse_args(argv)
    try:
        files, total, blocked = check_directory(args.directory)
    except (ReportError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        # Do not echo report messages, source snippets or arbitrary JSON values.
        reason = str(exc) if isinstance(exc, ReportError) else type(exc).__name__
        print(f"CodeQL gate ERROR: {reason}")
        return 2
    print(f"CodeQL gate: {files} report(s), {total} finding(s), "
          f"{blocked} blocking, {total - blocked} below threshold.")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
