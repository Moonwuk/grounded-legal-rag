"""Local checks for the fixture; Docker runtime assertions run in check_container.py."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
# Tests invoke the resolved interpreter and OpenSSL with fixed argv, never a shell.
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load_module("container_probe", Path(__file__).with_name("probe.py"))
harness = load_module("container_harness", ROOT / ".github/scripts/check_container.py")


class ContainerFixtureTests(unittest.TestCase):
    def test_stub_requires_real_retrieved_quote_and_exact_candidate(self):
        with self.assertRaises(ValueError):
            probe.model_reply({"evidence": [{"id": "f", "text": "Договор не содержит срока оплаты."}]})
        payload = {"evidence": [
            {"id": "context", "text": "Договор С-1/2026\n1. " + probe.QUOTE},
            {"id": "f", "text": "1. " + probe.QUOTE},
        ]}
        candidate = probe.model_reply(payload)
        self.assertEqual(candidate["claims"][0]["sources"][0]["fragment_id"], "f")
        candidate["claims"][0]["text"] = probe.VERIFIED_CLAIM
        verified = {**payload, "candidate": candidate, "rendered_answer": probe.EXPECTED_ANSWER}
        self.assertTrue(probe.model_reply(verified)["approved"])
        with self.assertRaises(ValueError):
            probe.model_reply({**verified, "rendered_answer": "Неподтвержденный ответ: 90 дней."})
        candidate["claims"][0]["text"] = "Срок оплаты — 90 дней."
        with self.assertRaises(ValueError):
            probe.model_reply(verified)

    def test_technical_fallback_and_wrong_id_do_not_pass_csv_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "submission.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["id", "answer"])
                writer.writerow(["1", "Не удалось проверить ответ из-за технической ошибки."])
            checks = probe.csv_checks(path)
            self.assertTrue(checks["answer-csv-schema"])
            self.assertFalse(checks["answer-csv-id"])
            self.assertFalse(checks["answer-csv-grounded"])

    def test_image_user_entrypoint_and_probe_contract_are_enforced(self):
        config = {"User": "0:0", "WorkingDir": "/output", "Entrypoint": ["python", "solution.py"]}
        checks = harness.image_checks({"Config": config})
        self.assertFalse(checks["image-nonroot-user"])
        self.assertFalse(checks["image-entrypoint"])
        self.assertEqual(harness.PROBE_CHECKS, probe.CHECK_NAMES)

    def test_docker_context_cannot_redirect_fixture_helpers(self):
        conflicting = {
            "DOCKER_HOST": "tcp://fixture.invalid:2375", "DOCKER_CONTEXT": "remote-fixture",
            "DOCKER_TLS": "1", "DOCKER_TLS_VERIFY": "1", "DOCKER_CERT_PATH": "/fixture/certs",
            "DOCKER_CONFIG": "/fixture/docker-auth", "HTTPS_PROXY": "http://proxy.fixture.invalid",
        }
        with mock.patch.dict(os.environ, conflicting), mock.patch.object(harness.subprocess, "run") as run:
            harness.execute(["/fixture/docker", "--host", harness.LOCAL_DOCKER_HOST, "info"])
        environment = run.call_args.kwargs["env"]
        self.assertTrue(all(name not in environment for name in conflicting if name not in {
            "DOCKER_CONFIG", "HTTPS_PROXY",
        }))
        self.assertEqual(environment["DOCKER_CONFIG"], conflicting["DOCKER_CONFIG"])
        self.assertEqual(environment["HTTPS_PROXY"], conflicting["HTTPS_PROXY"])
        with mock.patch.object(harness.shutil, "which", side_effect=lambda name: "/fixture/" + name), \
                mock.patch.object(harness, "inspected", return_value={}) as inspect:
            with self.assertRaises(harness.SmokeError):
                harness.run_checks("fixture:local", [])
        self.assertEqual(inspect.call_args.args[0], [
            "/fixture/docker", "--host", "unix:///var/run/docker.sock", "image", "inspect", "fixture:local",
        ])

    def test_real_application_uses_trusted_https_and_produces_grounded_csv(self):
        openssl = shutil.which("openssl")
        self.assertIsNotNone(openssl, "OpenSSL is required for the synthetic TLS fixture")
        with tempfile.TemporaryDirectory(prefix="psb-https-fixture-") as temporary:
            base = Path(temporary)
            data, output = base / "data", base / "output"
            data.mkdir()
            output.mkdir()
            with (data / "questions.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["id", "question"])
                writer.writerow([probe.QUESTION_ID, "Каков срок оплаты по договору С-1/2026?"])
            with zipfile.ZipFile(data / "knowledge-base.zip", "w") as archive:
                archive.writestr("contract.txt", "Договор С-1/2026\n1. " + probe.QUOTE + "\n")
            for name in ("sitecustomize.py", "psb_llm.py"):
                (output / name).write_text("raise RuntimeError('untrusted_cwd_imported')\n", encoding="utf-8")
            certificate, key = base / "server.crt", base / "server.key"
            # The private key is generated only in a temporary directory and never printed.
            generated = subprocess.run(  # nosec B603
                [openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "1",
                 "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
                 "-addext", "basicConstraints=critical,CA:TRUE",
                 "-keyout", str(key), "-out", str(certificate)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
            )
            self.assertEqual(generated.returncode, 0, "Synthetic certificate generation failed")
            synthetic = ("fixture-" + hashlib.sha256(b"local-container-fixture").hexdigest()).encode()
            environment = {
                "PATH": os.environ.get("PATH", ""), "DATA_DIR": str(data),
                "LLM_API_KEY": synthetic.decode(),
            }
            program = (
                "import runpy,sys; sys.path.insert(0,sys.argv[1]); "
                "runpy.run_path(sys.argv[1]+'/solution.py',run_name='__main__')"
            )
            checks = probe.serve_application(
                [sys.executable, "-I", "-B", "-c", program, str(ROOT / "prototype")],
                environment, output, synthetic, certificate, key,
            )
            self.assertTrue(all(checks.values()), [name for name, passed in checks.items() if not passed])


if __name__ == "__main__":
    unittest.main()
