"""Reject realistic privilege, credential, network and release-trust regressions."""
import copy
import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location("deployment_policy", Path(__file__).resolve().parents[1]
                                            / ".github/scripts/check_deployment.py")
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def compose():
    return {"services": {"psb": {
        "image": "ghcr.io/moonwuk/grounded-legal-rag@sha256:" + "a" * 64,
        "user": "10001:10001", "working_dir": "/output", "read_only": True, "init": True,
        "restart": "no", "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "cpus": 2, "mem_limit": 2 * 1024**3, "pids_limit": 128, "networks": {"egress": None},
        "tmpfs": ["/tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777"],
        "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
        "environment": {"DATA_DIR": "/data", "LLM_API_KEY_FILE": "/run/secrets/llm_api_key",
                        "LLM_BASE_URL": "https://proxy.example.invalid/v1", "LLM_MODEL": "ci-model",
                        "MAX_WORKERS": "2", "TOP_K": "6", "MAX_TOKENS": "8192",
                        "TEMPERATURE": "0", "PSB_RUN_SECONDS": "1100"},
        "volumes": [{"type": "bind", "source": source, "target": target, "read_only": readonly,
                     "bind": {"create_host_path": False}}
                    for source, target, readonly in (("/var/lib/psb/data", "/data", True),
                                                     ("/var/lib/psb/output", "/output", False),
                                                     ("/etc/psb/llm_api_key", "/run/secrets/llm_api_key", True))],
    }}, "networks": {"egress": {"driver": "bridge"}}}


def ansible():
    return ([{"hosts": "psb", "become": True, "any_errors_fatal": True, "roles": [{"role": "psb"}]}],
            [{"ansible.builtin.command": {"argv": list(policy.VERIFY_IMAGE)}, "delegate_to": "localhost",
              "become": False, "no_log": True, "check_mode": False},
             {"ansible.builtin.command": {"argv": ["docker", "--host", "unix:///var/run/docker.sock", "pull", "{{ psb_image }}"]}}])


class DeploymentPolicyTests(unittest.TestCase):
    def test_bounded_batch_deployment_is_accepted(self):
        self.assertEqual(policy.validate_compose(compose()), [])
        self.assertEqual(policy.validate_ansible(*ansible()), [])

    def test_canonical_compose_defaults_preserve_runtime_boundaries(self):
        document = compose()
        service = document["services"]["psb"]
        service.update(command=None, entrypoint=None)
        for volume in service["volumes"]:
            volume["bind"] = {}
        self.assertEqual(policy.validate_compose(document), [])
        service["volumes"][0]["bind"]["create_host_path"] = True
        self.assertIn("compose_existing_mount", policy.validate_compose(document))

    def test_empty_command_overrides_are_not_inherited_defaults(self):
        for field in ("command", "entrypoint"):
            for value in ([], "", ["sh"]):
                with self.subTest(field=field, value=value):
                    document = compose()
                    document["services"]["psb"][field] = value
                    self.assertIn("compose_forbidden_" + field, policy.validate_compose(document))

    def test_host_privilege_and_entrypoint_bypasses_are_rejected(self):
        for field, value in (("privileged", True), ("cap_add", ["SYS_ADMIN"]), ("user", "0:0"),
                             ("read_only", False), ("network_mode", "host"), ("pid", "host"),
                             ("entrypoint", ["sh"]), ("ports", [{"published": "8000", "target": 8000}]),
                             ("use_api_socket", True), ("post_start", [{"command": "sh", "user": "root"}]),
                             ("sysctls", {"net.ipv4.ip_forward": "1"}), ("provider", {"type": "unreviewed"})):
            with self.subTest(field=field):
                document = compose()
                document["services"]["psb"][field] = value
                self.assertTrue(policy.validate_compose(document))

    def test_inline_credentials_and_http_are_rejected(self):
        for name, value in (("LLM_API_KEY", "synthetic-value"), ("PYTHONPATH", "/data"),
                            ("LLM_BASE_URL", "http://proxy.example.invalid/v1"),
                            ("LLM_BASE_URL", "https://user:pass@proxy.example.invalid/v1")):
            document = compose()
            document["services"]["psb"]["environment"][name] = value
            self.assertTrue(policy.validate_compose(document))

    def test_mutable_or_placeholder_images_are_rejected(self):
        for image in ("ghcr.io/moonwuk/grounded-legal-rag:latest", "untrusted/image@sha256:" + "a" * 64,
                      "ghcr.io/moonwuk/grounded-legal-rag@sha256:" + "0" * 64):
            document = compose()
            document["services"]["psb"]["image"] = image
            self.assertTrue(policy.validate_compose(document))

    def test_socket_mounts_and_writable_input_are_rejected(self):
        for source, readonly in (("/var/run/docker.sock", True), ("/", True), ("/var/lib/psb/data", False)):
            document = compose()
            document["services"]["psb"]["volumes"][0].update(source=source, read_only=readonly)
            self.assertTrue(policy.validate_compose(document))

    def test_credential_under_writable_output_is_rejected(self):
        document = compose()
        document["services"]["psb"]["volumes"][2]["source"] = "/var/lib/psb/output/key"
        self.assertIn("compose_credential_mount_overlap", policy.validate_compose(document))

    def test_unbounded_resources_are_rejected(self):
        for field, value in (("cpus", "nan"), ("cpus", 0), ("mem_limit", 0),
                             ("mem_limit", 64 * 1024**3), ("pids_limit", -1)):
            document = compose()
            document["services"]["psb"][field] = value
            self.assertTrue(policy.validate_compose(document))

    def test_unverified_pull_and_weakened_signer_policy_are_rejected(self):
        playbook, tasks = ansible()
        self.assertTrue(policy.validate_ansible(playbook, tasks[::-1]))
        for field in ("--source-ref", "--source-digest", "--deny-self-hosted-runners"):
            modified = copy.deepcopy(tasks)
            modified[0]["ansible.builtin.command"]["argv"].remove(field)
            self.assertTrue(policy.validate_ansible(playbook, modified))

    def test_unrequested_execution_and_hidden_failures_are_rejected(self):
        for task in ({"ansible.builtin.shell": "download | sh"},
                     {"command": "docker compose up"},
                     {"action": "unreviewed_action"},
                     {"ansible.builtin.get_url": {"url": "https://example.invalid/unreviewed"}},
                     {"ansible.builtin.command": "docker compose up"},
                     {"ansible.builtin.command": {"argv": ["docker", "compose", "up"]}},
                     {"ansible.builtin.assert": {}, "ignore_errors": True},
                     {"block": [{"ansible.builtin.shell": "ignored command"}]}):
            playbook, tasks = ansible()
            self.assertTrue(policy.validate_ansible(playbook, tasks + [task]))

    def test_required_attestation_cannot_be_conditionally_skipped(self):
        for field, value in (("when", False), ("loop", []), ("until", False), ("ignore_errors", True),
                             ("failed_when", False), ("tags", ["optional"]), ("check_mode", True)):
            playbook, tasks = ansible()
            tasks[0][field] = value
            self.assertTrue(policy.validate_ansible(playbook, tasks))

    def test_env_template_cannot_show_configuration_in_diffs(self):
        playbook, tasks = ansible()
        task = {"ansible.builtin.template": {"src": "runtime.env.j2", "dest": "/release/.env", "mode": "0600"},
                "no_log": True, "diff": False}
        self.assertEqual(policy.validate_ansible(playbook, tasks + [task]), [])
        del task["diff"]
        self.assertIn("ansible_sensitive_write_logging", policy.validate_ansible(playbook, tasks + [task]))


if __name__ == "__main__":
    unittest.main()
