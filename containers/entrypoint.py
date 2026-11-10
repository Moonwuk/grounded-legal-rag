"""Container-only bootstrap; the organizer ZIP keeps its original contract."""
from __future__ import annotations

import os
from pathlib import Path
import runpy
import stat
import sys
from urllib.parse import urlsplit


APP = Path("/app")
SECRET = Path("/run/secrets/llm_api_key")
MAX_SECRET_BYTES = 8192


class ConfigurationError(ValueError):
    """Errors contain fixed identifiers, never input values or file contents."""


def read_secret(path: Path) -> str:
    """Read a bounded private regular file without following its final symlink."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError:
        raise ConfigurationError("secret_unreadable") from None
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) not in {0o400, 0o600}
                or not 0 < info.st_size <= MAX_SECRET_BYTES):
            raise ConfigurationError("secret_file_policy")
    except (OSError, ConfigurationError):
        os.close(descriptor)
        raise
    with os.fdopen(descriptor, "rb") as handle:
        raw = handle.read(MAX_SECRET_BYTES + 1)
    if len(raw) > MAX_SECRET_BYTES:
        raise ConfigurationError("secret_size_limit")
    try:
        value = raw.decode("ascii").strip()
    except UnicodeError:
        raise ConfigurationError("secret_encoding") from None
    if not value or any(not 33 <= ord(character) <= 126 for character in value):
        raise ConfigurationError("secret_value_format")
    return value


def validate_configuration(environment) -> None:
    """The standalone deployment uses TLS and a file; platform code is unchanged."""
    if environment.get("LLM_API_KEY") or environment.get("OPENAI_API_KEY"):
        raise ConfigurationError("use_mounted_secret")
    if environment.get("LLM_API_KEY_FILE", str(SECRET)) != str(SECRET):
        raise ConfigurationError("secret_mount_path")
    base = environment.get("LLM_BASE_URL", "")
    model = environment.get("LLM_MODEL", "")
    if not model.strip() or len(model) > 256 or any(ord(character) < 32 for character in model):
        raise ConfigurationError("model_configuration")
    try:
        parsed = urlsplit(base)
        valid = (0 < len(base) <= 2048 and parsed.scheme == "https" and parsed.hostname
                 and not parsed.username and not parsed.password and not parsed.query
                 and not parsed.fragment and "?" not in base and "#" not in base
                 and (parsed.port is None or 1 <= parsed.port <= 65535)
                 and base.isascii() and not any(character.isspace() for character in base))
    except ValueError:
        valid = False
    if not valid:
        raise ConfigurationError("https_endpoint_required")
    if environment.get("DATA_DIR", "/data") != "/data":
        raise ConfigurationError("data_mount_path")
    if Path.cwd() != Path("/output"):
        raise ConfigurationError("output_working_directory")


def main() -> int:
    try:
        if os.geteuid() != 10001 or os.getegid() != 10001:
            raise ConfigurationError("runtime_identity")
        validate_configuration(os.environ)
        value = read_secret(SECRET)
    except (ConfigurationError, OSError) as error:
        reason = str(error) if isinstance(error, ConfigurationError) else "configuration_io"
        print("container_configuration_error: " + reason, file=sys.stderr)
        return 2
    os.umask(0o077)
    # This value is set inside the process, never as a Docker build argument or
    # container-creation environment value. Modules still share one trust domain.
    os.environ["LLM_API_KEY"] = value
    os.environ["DATA_DIR"] = "/data"
    # Isolated Python ignores host PYTHONPATH/user site; explicitly allow only
    # these root-owned application modules in addition to its standard library.
    sys.path.insert(0, str(APP))
    runpy.run_path(str(APP / "solution.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
