"""Negative boundary checks for the container-only secret/TLS bootstrap."""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("container_entrypoint", ROOT / "containers" / "entrypoint.py")
BOOTSTRAP = module_from_spec(SPEC)
SPEC.loader.exec_module(BOOTSTRAP)


class ContainerBootstrapTests(unittest.TestCase):
    def test_private_secret_file_is_read_without_echo(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credential"
            path.write_text("synthetic-container-test-value\n")
            path.chmod(0o400)
            self.assertEqual(BOOTSTRAP.read_secret(path), "synthetic-container-test-value")

    def test_group_or_world_readable_secret_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credential"
            path.write_text("synthetic-container-test-value")
            for mode in (0o440, 0o404, 0o644, 0o700, 0o4400):
                with self.subTest(mode=mode):
                    path.chmod(mode)
                    with self.assertRaisesRegex(BOOTSTRAP.ConfigurationError, "^secret_file_policy$"):
                        BOOTSTRAP.read_secret(path)

    def test_symlink_and_fifo_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credential"
            path.write_text("synthetic-container-test-value")
            path.chmod(0o400)
            linked = Path(temporary) / "link"
            linked.symlink_to(path)
            fifo = Path(temporary) / "fifo"
            os.mkfifo(fifo, 0o600)
            for invalid in (linked, fifo, Path(temporary)):
                with self.subTest(kind=invalid.name):
                    with self.assertRaises(BOOTSTRAP.ConfigurationError):
                        BOOTSTRAP.read_secret(invalid)

    def test_empty_oversize_and_header_injection_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credential"
            for value in (b"", b" " * 10, b"x" * 8193, b"test\r\nHeader: bad", b"bad\x00token", b"\xff"):
                with self.subTest(size=len(value)):
                    path.write_bytes(value)
                    path.chmod(0o600)
                    with self.assertRaises(BOOTSTRAP.ConfigurationError):
                        BOOTSTRAP.read_secret(path)

    def test_other_owner_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credential"
            path.write_text("synthetic-container-test-value")
            path.chmod(0o400)
            with patch.object(BOOTSTRAP.os, "geteuid", return_value=os.geteuid() + 1):
                with self.assertRaisesRegex(BOOTSTRAP.ConfigurationError, "^secret_file_policy$"):
                    BOOTSTRAP.read_secret(path)

    def test_https_configuration_and_fixed_mounts(self):
        environment = {"LLM_BASE_URL": "https://llm.example.invalid/v1", "LLM_MODEL": "configured-model"}
        with patch.object(BOOTSTRAP.Path, "cwd", return_value=Path("/output")):
            BOOTSTRAP.validate_configuration(environment)
            for updates in (
                {"LLM_BASE_URL": "http://llm.example.invalid/v1"},
                {"LLM_BASE_URL": "https://user:password@llm.example.invalid"},
                {"LLM_BASE_URL": "https://llm.example.invalid?credential=bad"},
                {"LLM_BASE_URL": "https://llm.example.invalid/?"},
                {"LLM_BASE_URL": "https://llm.example.invalid/#fragment"},
                {"LLM_BASE_URL": "https://llm.example.invalid:99999"},
                {"LLM_BASE_URL": "https://llm.example.invalid/\nheader"},
                {"LLM_MODEL": ""}, {"LLM_MODEL": "model\nvalue"},
                {"LLM_API_KEY": "synthetic-value"}, {"OPENAI_API_KEY": "synthetic-value"},
                {"LLM_API_KEY_FILE": "/data/questions.csv"}, {"DATA_DIR": "/etc"},
            ):
                with self.subTest(fields=list(updates)):
                    with self.assertRaises(BOOTSTRAP.ConfigurationError):
                        BOOTSTRAP.validate_configuration({**environment, **updates})
        with patch.object(BOOTSTRAP.Path, "cwd", return_value=Path("/app")):
            with self.assertRaisesRegex(BOOTSTRAP.ConfigurationError, "^output_working_directory$"):
                BOOTSTRAP.validate_configuration(environment)


if __name__ == "__main__":
    unittest.main()
