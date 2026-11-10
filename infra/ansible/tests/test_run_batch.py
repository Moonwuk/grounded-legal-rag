"""Regression checks for manual-run locking, trust guards and result freshness."""
import copy
import errno
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "roles/psb/files/run_batch.py"
SPEC = importlib.util.spec_from_file_location("psb_manual_runner", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
IMAGE = runner.IMAGE_PREFIX + "a" * 64


def safe_compose():
    return {"services": {"psb": {
        "image": IMAGE, "user": "10001:10001", "read_only": True,
        "working_dir": "/output", "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "environment": {name: "fixture" for name in runner.ENV_NAMES} | {
            "DATA_DIR": "/data", "LLM_API_KEY_FILE": "/run/secrets/llm_api_key"},
        "volumes": [
            {"type": "bind", "source": "/var/lib/psb/data", "target": "/data", "read_only": True},
            {"type": "bind", "source": "/var/lib/psb/output", "target": "/output"},
            {"type": "bind", "source": "/etc/psb/llm_api_key", "target": "/run/secrets/llm_api_key", "read_only": True},
        ],
    }}}


class ManualRunnerTests(unittest.TestCase):
    def test_lock_rejects_concurrent_run_and_releases_after_close(self):
        with tempfile.TemporaryDirectory() as directory:
            first = runner.acquire_lock(directory)
            try:
                with self.assertRaises(BlockingIOError):
                    runner.acquire_lock(directory)
            finally:
                os.close(first)
            second = runner.acquire_lock(directory)
            os.close(second)

    def test_lock_does_not_follow_a_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "unrelated").write_text("untouched")
            (path / ".batch.lock").symlink_to(path / "unrelated")
            with self.assertRaises(OSError):
                runner.acquire_lock(path)
            self.assertEqual((path / "unrelated").read_text(), "untouched")

    def test_prior_output_is_archived_before_new_result_can_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            output.mkdir()
            history = root / "history"
            history.mkdir()
            for name in runner.RESULT_NAMES:
                (output / name).write_text("previous " + name)
            (output / "unrelated.txt").write_text("keep")
            archive = runner.archive_previous(output, history)
            self.assertEqual(set(p.name for p in archive.iterdir()), set(runner.RESULT_NAMES))
            for name in runner.RESULT_NAMES:
                self.assertFalse((output / name).exists())
                self.assertEqual((archive / name).read_text(), "previous " + name)
            self.assertEqual((output / "unrelated.txt").read_text(), "keep")
            self.assertIsNone(runner.archive_previous(output, history))

    def test_archival_supports_a_different_filesystem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            history = root / "history"
            output.mkdir()
            history.mkdir()
            (output / "submission.csv").write_text("previous result")
            with patch.object(runner.os, "replace", side_effect=OSError(errno.EXDEV, "different filesystem")):
                archive = runner.archive_previous(output, history)
            self.assertEqual((archive / "submission.csv").read_text(), "previous result")
            self.assertFalse((output / "submission.csv").exists())

    def test_previous_output_symlink_is_rejected_without_reading_or_moving_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            history = root / "history"
            output.mkdir()
            history.mkdir()
            (root / "unrelated").write_text("untouched")
            (output / "submission.csv").symlink_to(root / "unrelated")
            with self.assertRaises(runner.RunError):
                runner.archive_previous(output, history)
            self.assertEqual((root / "unrelated").read_text(), "untouched")
            self.assertEqual(list(history.iterdir()), [])

    def test_host_must_enforce_each_resource_and_seccomp_boundary(self):
        info = {"OSType": "linux", "Architecture": "x86_64", "MemoryLimit": True,
                "PidsLimit": True, "CpuCfsPeriod": True, "CpuCfsQuota": True,
                "SecurityOptions": ["name=seccomp,profile=builtin"]}
        runner.validate_host(info)
        for field in info:
            broken = copy.deepcopy(info)
            del broken[field]
            with self.subTest(field=field), self.assertRaises(runner.RunError):
                runner.validate_host(broken)
        for unsupported in ("name=userns", "name=rootless"):
            broken = copy.deepcopy(info)
            broken["SecurityOptions"].append(unsupported)
            with self.subTest(option=unsupported), self.assertRaises(runner.RunError):
                runner.validate_host(broken)

    def test_compose_digest_and_security_boundaries_cannot_be_overridden(self):
        self.assertEqual(set(runner.validate_compose(safe_compose(), IMAGE)),
                         {"/data", "/output", "/run/secrets/llm_api_key"})
        for field, value in (("image", "example:latest"), ("user", "0:0"),
                             ("read_only", False), ("command", ["sh"]),
                             ("ports", ["8000:8000"]), ("cap_add", ["SYS_ADMIN"]),
                             ("network_mode", "host")):
            data = safe_compose()
            data["services"]["psb"][field] = value
            with self.subTest(field=field), self.assertRaises(runner.RunError):
                runner.validate_compose(data, IMAGE)

    def test_extra_environment_and_writable_input_are_rejected(self):
        data = safe_compose()
        data["services"]["psb"]["environment"]["UNEXPECTED"] = "fixture"
        with self.assertRaises(runner.RunError):
            runner.validate_compose(data, IMAGE)
        data = safe_compose()
        data["services"]["psb"]["volumes"][0]["read_only"] = False
        with self.assertRaises(runner.RunError):
            runner.validate_compose(data, IMAGE)


if __name__ == "__main__":
    unittest.main()
