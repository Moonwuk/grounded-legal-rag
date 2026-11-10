"""Check the resolved Compose model and the project's Ansible trust boundaries."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit


REPOSITORY = "Moonwuk/grounded-legal-rag"
# A Docker mount specification, not a host path opened by this checker.
TMPFS_MOUNT = "/tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777"  # nosec B108
VERIFY_IMAGE = ["gh", "attestation", "verify", "oci://{{ psb_image }}", "--repo", REPOSITORY,
                "--signer-workflow", REPOSITORY + "/.github/workflows/security.yml",
                "--source-ref", "refs/heads/main", "--source-digest", "{{ psb_source_commit }}",
                "--deny-self-hosted-runners"]


def bounded_number(value, minimum, maximum):
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
        return math.isfinite(number) and minimum <= number <= maximum
    except (TypeError, ValueError):
        return False


def memory_bytes(value):
    if type(value) is int:
        return value
    if isinstance(value, str):
        match = re.fullmatch(r"([0-9]+)([kmgt]?)(?:b)?", value.lower())
        if match:
            return int(match.group(1)) * 1024 ** {"": 0, "k": 1, "m": 2, "g": 3, "t": 4}[match.group(2)]
    return -1


def validate_compose(document):
    errors = []

    def require(condition, code):
        if not condition:
            errors.append(code)

    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        return ["compose_model_missing"]
    require(set(document["services"]) == {"psb"}, "compose_service_scope")
    service = document["services"].get("psb")
    if not isinstance(service, dict):
        return errors + ["compose_service_missing"]
    allowed_service = {"image", "user", "working_dir", "read_only", "init", "restart", "cap_drop", "security_opt",
                       "command", "entrypoint",
                       "cpus", "mem_limit", "pids_limit", "networks", "tmpfs", "logging", "volumes", "environment"}
    require(not (set(service) - allowed_service), "compose_unknown_service_field")
    image = service.get("image", "")
    require(isinstance(image, str) and re.fullmatch(
        r"ghcr\.io/moonwuk/grounded-legal-rag@sha256:[a-f0-9]{64}", image) is not None
        and not image.endswith("0" * 64), "compose_immutable_image")
    require(service.get("user") == "10001:10001", "compose_nonroot_user")
    require(service.get("working_dir") == "/output", "compose_working_directory")
    require(service.get("read_only") is True, "compose_readonly_root")
    require(service.get("init") is True, "compose_process_reaping")
    require(service.get("restart") == "no", "compose_batch_restart_policy")
    require(service.get("cap_drop") == ["ALL"], "compose_drop_capabilities")
    require(service.get("security_opt") == ["no-new-privileges:true"], "compose_no_new_privileges")
    # Canonical Compose JSON includes null for inherited image commands. An
    # empty string/list instead clears the image default and is not equivalent.
    for field in ("command", "entrypoint"):
        require(service.get(field) is None, "compose_forbidden_" + field)
    for field in ("privileged", "cap_add", "devices", "device_cgroup_rules", "ports", "expose",
                  "network_mode", "pid", "ipc", "userns_mode", "volumes_from",
                  "build", "extra_hosts", "env_file", "oom_kill_disable", "use_api_socket"):
        require(not service.get(field), "compose_forbidden_" + field)
    require(bounded_number(service.get("cpus"), 0.1, 8), "compose_cpu_limit")
    require(128 * 1024**2 <= memory_bytes(service.get("mem_limit")) <= 16 * 1024**3,
            "compose_memory_limit")
    require(type(service.get("pids_limit")) is int and 1 <= service["pids_limit"] <= 256,
            "compose_process_limit")
    require(service.get("networks") == {"egress": None} or service.get("networks") == {"egress": {}},
            "compose_bridge_scope")
    networks = document.get("networks", {})
    network = networks.get("egress", {}) if isinstance(networks, dict) else {}
    require(set(networks) == {"egress"} and isinstance(network, dict)
            and network.get("driver") == "bridge" and not network.get("external")
            and not network.get("driver_opts"), "compose_bridge_definition")
    require(service.get("tmpfs") == [TMPFS_MOUNT], "compose_bounded_tmpfs")
    require(service.get("logging") == {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
            "compose_bounded_logs")

    volumes = service.get("volumes", [])
    expected = {"/data": True, "/output": False, "/run/secrets/llm_api_key": True}
    sources = {}
    if not isinstance(volumes, list) or len(volumes) != 3:
        errors.append("compose_mount_scope")
    else:
        for volume in volumes:
            if not isinstance(volume, dict):
                errors.append("compose_invalid_mount")
                continue
            target = volume.get("target")
            source = volume.get("source")
            require(target in expected and target not in sources, "compose_mount_scope")
            require(volume.get("type") == "bind" and isinstance(source, str), "compose_bind_mount")
            require(volume.get("read_only", False) is expected.get(target), "compose_mount_write_scope")
            # Compose 2.38 omits the false bool in canonical long-syntax bind
            # options; short syntax and explicit creation serialize true.
            bind = volume.get("bind", {})
            require(isinstance(bind, dict) and bind.get("create_host_path", False) is False,
                    "compose_existing_mount")
            if isinstance(source, str):
                path = PurePosixPath(source)
                require(path.is_absolute() and ".." not in path.parts and len(path.parts) >= 3
                        and not source.startswith(("/proc/", "/sys/", "/dev/", "/run/", "/var/run/"))
                        and not source.endswith(("docker.sock", "containerd.sock")), "compose_host_path_scope")
                sources[target] = path
        require(set(sources) == set(expected), "compose_mount_scope")
        if set(sources) == set(expected):
            data, output, key = sources["/data"], sources["/output"], sources["/run/secrets/llm_api_key"]
            require(data != output and data not in output.parents and output not in data.parents,
                    "compose_data_output_overlap")
            require(key != data and key != output and data not in key.parents and output not in key.parents,
                    "compose_credential_mount_overlap")

    environment = service.get("environment", {})
    allowed = {"DATA_DIR", "LLM_API_KEY_FILE", "LLM_BASE_URL", "LLM_MODEL", "MAX_WORKERS", "TOP_K",
               "MAX_TOKENS", "TEMPERATURE", "PSB_RUN_SECONDS"}
    if not isinstance(environment, dict):
        return errors + ["compose_environment_missing"]
    require(set(environment) == allowed, "compose_environment_scope")
    require(environment.get("DATA_DIR") == "/data"
            and environment.get("LLM_API_KEY_FILE") == "/run/secrets/llm_api_key", "compose_runtime_paths")
    try:
        endpoint = urlsplit(environment.get("LLM_BASE_URL", ""))
        valid_endpoint = (endpoint.scheme == "https" and endpoint.hostname and not endpoint.username
                          and not endpoint.password and not endpoint.query and not endpoint.fragment
                          and (endpoint.port is None or 1 <= endpoint.port <= 65535))
    except (TypeError, ValueError):
        valid_endpoint = False
    require(bool(valid_endpoint), "compose_https_proxy")
    model = environment.get("LLM_MODEL")
    require(isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", model) is not None,
            "compose_model_identifier")
    for field, low, high in (("MAX_WORKERS", 1, 8), ("TOP_K", 1, 40), ("MAX_TOKENS", 256, 8192),
                             ("PSB_RUN_SECONDS", 1, 1150), ("TEMPERATURE", 0, 2)):
        value = environment.get(field)
        require(bounded_number(value, low, high)
                and (field == "TEMPERATURE" or str(value).isdigit()), "compose_limit_" + field.lower())
    return sorted(set(errors))


def validate_ansible(playbook, tasks):
    errors = []
    if not isinstance(playbook, list) or len(playbook) != 1 or not isinstance(playbook[0], dict):
        return ["ansible_playbook_scope"]
    play = playbook[0]
    if set(play) - {"name", "hosts", "gather_facts", "become", "any_errors_fatal", "roles"}:
        errors.append("ansible_unreviewed_playbook_field")
    if play.get("hosts") != "psb" or play.get("become") is not True or play.get("any_errors_fatal") is not True:
        errors.append("ansible_target_scope")
    if play.get("roles") != [{"role": "psb"}]:
        errors.append("ansible_role_scope")
    if not isinstance(tasks, list) or not tasks:
        return errors + ["ansible_tasks_missing"]
    verified = False
    for task in tasks:
        if not isinstance(task, dict):
            errors.append("ansible_invalid_task")
            continue
        serialized = json.dumps(task)
        if re.search(r"(?:lookup|query)\s*\(", serialized):
            errors.append("ansible_controller_lookup")
        allowed_modules = {"assert", "command", "copy", "debug", "file", "set_fact", "setup", "stat", "template"}
        module_keys = {"ansible.builtin." + name for name in allowed_modules}
        metadata_keys = {"name", "register", "when", "loop", "loop_control", "changed_when", "check_mode", "no_log",
                         "diff", "delegate_to", "become", "failed_when", "ignore_errors"}
        if len(set(task) & module_keys) != 1 or set(task) - module_keys - metadata_keys:
            errors.append("ansible_unreviewed_module")
        if any(key.rsplit(".", 1)[-1] in {"shell", "raw", "script", "include_tasks", "import_tasks",
                                           "include_role", "import_role", "action", "local_action"} for key in task):
            errors.append("ansible_unreviewed_execution")
        if task.get("ignore_errors") or task.get("failed_when") is False:
            errors.append("ansible_ignored_failure")
        if any(field in task for field in ("block", "rescue", "always")):
            errors.append("ansible_unreviewed_nested_execution")
        command = task.get("ansible.builtin.command")
        if command is not None:
            argv = command.get("argv") if isinstance(command, dict) else None
            if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv):
                errors.append("ansible_command_requires_argv")
                continue
            if argv == VERIFY_IMAGE:
                no_bypass = not any(field in task for field in ("when", "loop", "until", "retries", "tags",
                                                                "ignore_errors", "failed_when"))
                if (task.get("delegate_to") == "localhost" and task.get("become") is False
                        and task.get("no_log") is True and task.get("check_mode") is False and no_bypass):
                    verified = True
                else:
                    errors.append("ansible_controller_verification_scope")
            elif argv == ["gh", "attestation", "verify", "--help"]:
                if task.get("delegate_to") != "localhost" or task.get("become") is not False:
                    errors.append("ansible_controller_verification_scope")
            elif argv[:3] == ["docker", "--host", "unix:///var/run/docker.sock"]:
                argv = ["docker"] + argv[3:]
                if len(argv) < 2 or argv[1] not in {"version", "info", "compose", "pull"}:
                    errors.append("ansible_unreviewed_command")
                    continue
                if "pull" in argv and not verified:
                    errors.append("ansible_pull_before_verification")
                if argv[1] == "pull" and argv != ["docker", "pull", "{{ psb_image }}"]:
                    errors.append("ansible_unreviewed_image_pull")
                if any(arg in argv for arg in ("run", "up", "start", "exec", "build", "create", "stop", "down", "rm", "kill", "restart")):
                    errors.append("ansible_unrequested_workload_start")
            else:
                errors.append("ansible_unreviewed_command")
        for module in ("ansible.builtin.copy", "ansible.builtin.template"):
            settings = task.get(module)
            if isinstance(settings, dict) and ("content" in settings or ".env" in str(settings.get("dest", ""))):
                if settings.get("mode") != "0600" or task.get("no_log") is not True or task.get("diff") is not False:
                    errors.append("ansible_sensitive_write_logging")
    if not verified:
        errors.append("ansible_verified_provenance_required")
    return sorted(set(errors))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-json", required=True, type=Path)
    parser.add_argument("--ansible-dir", type=Path, default=Path("infra/ansible"))
    parser.add_argument("--report", type=Path, default=Path("reports/deployment-policy.json"))
    args = parser.parse_args(argv)
    try:
        # PyYAML is supplied by the isolated, hash-locked IaC tool environment.
        import yaml

        compose = json.loads(args.compose_json.read_text(encoding="utf-8"))
        playbook = yaml.safe_load((args.ansible_dir / "playbook.yml").read_text(encoding="utf-8"))
        tasks = yaml.safe_load((args.ansible_dir / "roles/psb/tasks/main.yml").read_text(encoding="utf-8"))
        errors = validate_compose(compose) + validate_ansible(playbook, tasks)
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        errors = ["invalid_or_unavailable_policy_input"]
    except yaml.YAMLError:
        errors = ["invalid_ansible_yaml"]
    report = {"status": "failed" if errors else "passed", "errors": sorted(set(errors)),
              "scope": "resolved Compose configuration and project Ansible trust boundaries; no deployment"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Deployment policy: {report['status']}; {len(errors)} violation(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
