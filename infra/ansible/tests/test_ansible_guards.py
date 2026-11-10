"""Exercise the actual role expressions without contacting or mutating a host."""
from pathlib import Path
import unittest

from ansible.errors import AnsibleError
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.loader import init_plugin_loader
from ansible.template import Templar


ROOT = Path(__file__).resolve().parents[1]


class AnsibleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_plugin_loader()
        cls.loader = DataLoader()
        cls.tasks = cls.loader.load_from_file(
            str(ROOT / "roles/psb/tasks/main.yml"), trusted_as_template=True
        )
        cls.by_name = {task["name"]: task for task in cls.tasks}
        cls.defaults = dict(cls.loader.load_from_file(
            str(ROOT / "group_vars/psb.yml"), trusted_as_template=True
        ))

    def setUp(self):
        self.variables = dict(
            self.defaults,
            ansible_host="host.example.org",
            inventory_hostname="host.example.org",
            psb_image="ghcr.io/moonwuk/grounded-legal-rag@sha256:" + "a" * 64,
            psb_source_commit="b" * 40,
            psb_llm_base_url="https://proxy.example.org:443/v1",
            psb_llm_model="fixture-model",
        )

    def accepts(self, task_name, **variables):
        conditions = self.by_name[task_name]["ansible.builtin.assert"]["that"]
        templar = Templar(loader=self.loader, variables=dict(self.variables, **variables))
        try:
            return all(templar.evaluate_conditional(condition) for condition in conditions)
        except AnsibleError:
            # Invalid URL ports can be rejected by urlsplit itself. A template
            # error also stops the real assert task before deployment writes.
            return False

    def test_ancestor_enumeration_includes_all_prefixes_before_uid_leaves(self):
        for name in (
            "Compute the immutable release directory before inspecting write paths",
            "Enumerate every trusted ancestor before any filesystem mutation",
        ):
            facts = self.by_name[name]["ansible.builtin.set_fact"]
            self.variables.update(Templar(loader=self.loader, variables=self.variables).template(facts))
        self.assertEqual(self.variables["psb_parent_directories"], [
            "/", "/etc", "/etc/psb", "/srv", "/srv/psb", "/srv/psb/releases",
            "/var", "/var/lib", "/var/lib/psb",
        ])
        self.assertNotIn(self.variables["psb_data_dir"], self.variables["psb_parent_directories"])
        self.assertNotIn(self.variables["psb_output_dir"], self.variables["psb_parent_directories"])

    def test_existing_root_ancestors_and_missing_planned_nodes_are_allowed(self):
        guard = "Refuse untrusted or linked ancestors before any root writes"
        for metadata in (
            {"exists": False},
            {"exists": True, "isdir": True, "islnk": False, "uid": 0, "mode": "0755"},
            {"exists": True, "isdir": True, "islnk": False, "uid": 0, "mode": "0700"},
        ):
            with self.subTest(metadata=metadata):
                self.assertTrue(self.accepts(guard, item={"stat": metadata}))

    def test_link_nonroot_and_writable_ancestors_are_rejected(self):
        guard = "Refuse untrusted or linked ancestors before any root writes"
        safe = {"exists": True, "isdir": True, "islnk": False, "uid": 0, "mode": "0755"}
        for changes in (
            {"isdir": False, "islnk": True}, {"uid": 10001},
            {"mode": "0775"}, {"mode": "0757"}, {"mode": "1777"}, {"isdir": False},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(self.accepts(guard, item={"stat": dict(safe, **changes)}))

    def test_filesystem_mutations_do_not_follow_destination_symlinks(self):
        checked = 0
        for task in self.tasks:
            for action in ("ansible.builtin.file", "ansible.builtin.copy", "ansible.builtin.template"):
                if action in task:
                    with self.subTest(task=task["name"]):
                        self.assertIs(task[action].get("follow"), False)
                    checked += 1
        self.assertGreater(checked, 0)

    def test_release_identity_rejects_placeholders_and_invalid_ports(self):
        guard = "Refuse placeholder hosts, mutable images, and incomplete release identity"
        self.assertTrue(self.accepts(guard))
        for changes in (
            {"ansible_host": "psb.example.invalid"},
            {"psb_image": "ghcr.io/moonwuk/grounded-legal-rag:latest"},
            {"psb_source_commit": "0" * 40},
            {"psb_llm_base_url": "https://proxy.example.org:99999/v1"},
            {"psb_llm_base_url": "https://proxy.example.org:0/v1"},
            {"psb_llm_base_url": "http://proxy.example.org/v1"},
            {"psb_llm_model": "CHANGE_ME"},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(self.accepts(guard, **changes))

    def test_existing_config_destinations_must_be_trusted_regular_files(self):
        guard = "Refuse linked or untrusted configuration destinations"
        safe = {"exists": True, "isreg": True, "islnk": False, "uid": 0, "mode": "0600"}
        self.assertTrue(self.accepts(guard, item={"stat": safe}))
        self.assertTrue(self.accepts(guard, item={"stat": {"exists": False}}))
        for changes in ({"isreg": False, "islnk": True}, {"uid": 10001}, {"mode": "0660"}):
            with self.subTest(changes=changes):
                self.assertFalse(self.accepts(guard, item={"stat": dict(safe, **changes)}))

    def test_current_selector_must_stay_in_the_prepared_release_tree(self):
        guard = "Require an absent or root-owned prepared-release selector"
        safe = {"exists": True, "islnk": True, "uid": 0,
                "lnk_source": "/srv/psb/releases/" + "a" * 64}
        self.assertTrue(self.accepts(guard, psb_current_stat={"stat": {"exists": False}}))
        self.assertTrue(self.accepts(guard, psb_current_stat={"stat": safe}))
        for changes in ({"islnk": False}, {"uid": 10001}, {"lnk_source": "/etc"}):
            with self.subTest(changes=changes):
                self.assertFalse(self.accepts(guard, psb_current_stat={"stat": dict(safe, **changes)}))


if __name__ == "__main__":
    unittest.main()
