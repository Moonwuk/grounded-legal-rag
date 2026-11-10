#!/usr/bin/env python3
"""Inventory runtime dependencies without importing code or invoking a resolver.

Only prototype/ is runtime scope. The intentionally small requirements grammar
accepts canonical names, exact public versions and SHA-256 hashes in the lock.
CI separately verifies lock closure with pip's wheel-only, hash-required dry run.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import sys


class PolicyError(ValueError):
    """The runtime dependency contract cannot be verified."""


# A deliberately restricted subset of PEP 440, not a replacement for packaging.
VERSION = r"[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?"
PIN = re.compile(rf"(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)==(?P<version>{VERSION})\Z")
HASH = re.compile(r"--hash=sha256:[0-9a-f]{64}\Z")


def read_pins(path: Path, *, hashed: bool) -> dict[str, str]:
    """Parse only exact pins; reject resolver directives, URLs and markers."""
    pins: dict[str, str] = {}
    pending = ""
    start_line = 0
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if raw.lstrip().startswith("#"):
            continue
        line = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
        if not line:
            continue
        if not pending:
            start_line = line_number
        continued = line.endswith("\\")
        pending += " " + (line[:-1].strip() if continued else line)
        if continued:
            continue
        fields = pending.split()
        pending = ""
        match = PIN.fullmatch(fields[0])
        location = f"{path.name}:{start_line}"
        if match is None:
            raise PolicyError(
                f"{location}: expected canonical-name==exact.version; "
                "URLs, ranges, extras, markers, includes and index options are unsupported"
            )
        if hashed:
            if len(fields) < 2 or any(HASH.fullmatch(field) is None for field in fields[1:]):
                raise PolicyError(f"{location}: lock pins require one or more --hash=sha256:<64 lowercase hex> values")
        elif len(fields) != 1:
            raise PolicyError(f"{location}: requirements.txt accepts only name==version, without options or markers")
        name, version = match.group("name", "version")
        if name in pins:
            raise PolicyError(f"{location}: duplicate requirement {name}")
        pins[name] = version
    if pending:
        raise PolicyError(f"{path.name}:{start_line}: unterminated line continuation")
    return pins


def inspect_runtime(root: Path) -> dict:
    runtime = root / "prototype"
    requirements = runtime / "requirements.txt"
    lock = runtime / "requirements.lock"
    if not requirements.is_file():
        raise PolicyError("prototype/requirements.txt is missing; runtime dependency scope is unknown")
    direct = read_pins(requirements, hashed=False)
    sources = sorted(runtime.glob("*.py"))
    if not sources:
        raise PolicyError("prototype/ contains no Python source files; cannot verify runtime imports")
    own_modules = {source.stem for source in sources}
    allowed = sys.stdlib_module_names | own_modules
    foreign: dict[str, list[str]] = {}
    for source in sources:
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except SyntaxError as exc:
            raise PolicyError(f"{source.relative_to(root)}:{exc.lineno}: invalid Python syntax") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".", 1)[0]]
            else:
                continue
            for name in names:
                if name not in allowed:
                    foreign.setdefault(name, []).append(f"{source.relative_to(root)}:{node.lineno}")
    if foreign and not direct:
        locations = "; ".join(f"{name} ({', '.join(paths)})" for name, paths in sorted(foreign.items()))
        raise PolicyError(f"Third-party imports with empty runtime requirements: {locations}")
    locked = read_pins(lock, hashed=True) if lock.is_file() else {}
    if direct:
        if not lock.is_file():
            raise PolicyError("Runtime dependencies require prototype/requirements.lock with exact pins and SHA-256 hashes")
        for name, version in direct.items():
            if locked.get(name) != version:
                raise PolicyError(f"requirements.lock must contain the direct requirement {name}=={version}")
    elif locked:
        raise PolicyError("requirements.lock contains packages while runtime requirements are empty; remove the stale lock entries")
    return {
        "schema_version": 1,
        "scope": "prototype/*.py and prototype/requirements.txt",
        "status": "pinned_dependencies" if direct else "stdlib_only",
        "has_dependencies": bool(direct),
        "python_version": sys.version.split()[0],
        "files_scanned": [str(source.relative_to(root)) for source in sources],
        "direct_dependencies": direct,
        "locked_dependencies": locked,
        "foreign_imports": dict(sorted(foreign.items())),
        "lock_closure_verified": False,
        "limitations": [
            "Static import statements only; dynamic imports are not resolved.",
            "Python interpreter, standard-library and OS vulnerabilities are not assessed.",
            "Import names are not mapped to distribution names; CI verifies dependency closure separately.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path, default=Path("reports/runtime-dependencies.json"))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    report = args.report if args.report.is_absolute() else root / args.report
    try:
        inventory = inspect_runtime(root)
    except (PolicyError, OSError, UnicodeError) as exc:
        print(f"Runtime dependency policy failed: {exc}", file=sys.stderr)
        return 1
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    has_dependencies = str(inventory["has_dependencies"]).lower()
    if output_path := os.environ.get("GITHUB_OUTPUT"):
        with Path(output_path).open("a", encoding="utf-8") as stream:
            stream.write(f"has_dependencies={has_dependencies}\n")
    print(f"Runtime dependency policy: {inventory['status']}; report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
