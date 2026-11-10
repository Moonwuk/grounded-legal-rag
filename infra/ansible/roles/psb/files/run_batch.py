#!/usr/bin/python3 -I
"""Run only the prepared PSB release, serially, without accepting Docker args."""
from __future__ import annotations

from datetime import datetime, timezone
import errno
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import stat
# Every invocation below uses a validated root-owned executable, fixed argument
# structure and no shell. No caller-controlled Docker options are accepted.
import subprocess  # nosec B404
import sys


IMAGE_PREFIX = "ghcr.io/moonwuk/grounded-legal-rag@sha256:"
SOCKET = "unix:///var/run/docker.sock"
PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
RESULT_NAMES = ("submission.csv", "submission.csv.tmp")
ENV_NAMES = {
    "DATA_DIR", "LLM_API_KEY_FILE", "LLM_BASE_URL", "LLM_MODEL",
    "MAX_WORKERS", "TOP_K", "MAX_TOKENS", "TEMPERATURE", "PSB_RUN_SECONDS",
}


class RunError(RuntimeError):
    """A fixed, nonsecret diagnostic suitable for operator logs."""


def require_root_owned(path, *, directory=False, mode=None):
    info = Path(path).lstat()
    valid_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid_type or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        raise RunError("release paths must be root-owned and not group/world-writable")
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise RunError("release configuration permissions changed")


def acquire_lock(install):
    fd = os.open(Path(install) / ".batch.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise RunError("invalid batch lock file")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


def validate_host(info):
    if not isinstance(info, dict):
        raise RunError("Docker host metadata is invalid")
    if info.get("OSType") != "linux" or info.get("Architecture") not in {"amd64", "x86_64"}:
        raise RunError("the prepared runtime requires a Linux amd64 Docker host")
    if any(info.get(field) is not True for field in ("MemoryLimit", "PidsLimit", "CpuCfsPeriod", "CpuCfsQuota")):
        raise RunError("Docker memory, PID or CPU quota enforcement is unavailable")
    options = info.get("SecurityOptions", [])
    if not isinstance(options, list) or not any(
        isinstance(option, str) and re.match(r"^name=seccomp(?:,|$)", option) for option in options
    ):
        raise RunError("Docker default seccomp is unavailable")
    if any(isinstance(option, str) and re.match(r"^name=(?:userns|rootless)(?:,|$)", option) for option in options):
        raise RunError("rootless Docker and user-namespace remapping are unsupported by these UID bind mounts")


def validate_compose(configuration, expected_image):
    if not isinstance(configuration, dict):
        raise RunError("rendered Compose configuration is invalid")
    services = configuration.get("services", {})
    if set(services) != {"psb"}:
        raise RunError("prepared Compose service scope changed")
    service = services["psb"]
    if service.get("image") != expected_image or service.get("user") != "10001:10001":
        raise RunError("prepared image digest or runtime user changed")
    if service.get("read_only") is not True or service.get("working_dir") != "/output":
        raise RunError("prepared filesystem boundaries changed")
    if set(service.get("cap_drop", [])) != {"ALL"} or service.get("cap_add"):
        raise RunError("prepared capability boundary changed")
    if service.get("security_opt") != ["no-new-privileges:true"]:
        raise RunError("prepared privilege boundary changed")
    if any(service.get(field) for field in ("ports", "privileged", "devices", "build", "command", "entrypoint")):
        raise RunError("prepared Compose enables an unexpected runtime override")
    if any(service.get(field) == "host" for field in ("network_mode", "pid", "ipc")):
        raise RunError("host namespaces are forbidden")
    environment = service.get("environment", {})
    if set(environment) != ENV_NAMES or environment.get("LLM_API_KEY_FILE") != "/run/secrets/llm_api_key":
        raise RunError("prepared environment scope changed")
    if environment.get("DATA_DIR") != "/data":
        raise RunError("prepared input directory changed")
    mounts = service.get("volumes", [])
    expected = {"/data": True, "/output": False, "/run/secrets/llm_api_key": True}
    if len(mounts) != len(expected):
        raise RunError("prepared bind mount count changed")
    paths = {}
    for mount in mounts:
        target = mount.get("target")
        if target not in expected or target in paths or mount.get("type") != "bind":
            raise RunError("unexpected bind mount")
        source = mount.get("source")
        if not isinstance(source, str) or not Path(source).is_absolute() or ".." in Path(source).parts:
            raise RunError("bind sources must be absolute dedicated paths")
        if bool(mount.get("read_only", False)) != expected[target]:
            raise RunError("prepared bind mount access changed")
        if mount.get("bind", {}).get("create_host_path", False) is not False:
            raise RunError("automatic creation of bind sources is forbidden")
        paths[target] = Path(source)
    if len(set(paths.values())) != 3:
        raise RunError("bind source scopes overlap")
    return paths


def check_runtime_paths(paths):
    for path in paths.values():
        for parent in path.parents:
            require_root_owned(parent, directory=True)
    output = paths["/output"].lstat()
    data = paths["/data"].lstat()
    key = paths["/run/secrets/llm_api_key"].lstat()
    if not stat.S_ISDIR(output.st_mode) or output.st_uid != 10001 or stat.S_IMODE(output.st_mode) != 0o700:
        raise RunError("output must be a private real directory owned by UID 10001")
    if not stat.S_ISDIR(data.st_mode) or data.st_uid != 10001 or stat.S_IMODE(data.st_mode) & 0o022:
        raise RunError("input must be a protected real directory owned by UID 10001")
    if not stat.S_ISREG(key.st_mode) or key.st_uid != 10001 or stat.S_IMODE(key.st_mode) != 0o400:
        raise RunError("credential must be a regular UID 10001 file with mode 0400")
    if not 0 < key.st_size <= 8192:
        raise RunError("credential file size is invalid")
    for name in ("questions.csv", "knowledge-base.zip"):
        info = (paths["/data"] / name).lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 10001 or stat.S_IMODE(info.st_mode) != 0o400:
            raise RunError("required inputs must be regular UID 10001 files with mode 0400")


def _copy_across_filesystems(source, destination, original):
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(source_fd)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (original.st_dev, original.st_ino):
            raise RunError("previous result changed during archival")
        destination_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(destination_fd, "wb") as output, os.fdopen(os.dup(source_fd), "rb") as incoming:
            shutil.copyfileobj(incoming, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        current = source.lstat()
        if (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
            raise RunError("previous result changed before archival completed")
        source.unlink()
    finally:
        os.close(source_fd)


def archive_previous(output, history):
    previous = []
    for name in RESULT_NAMES:
        source = Path(output) / name
        try:
            info = source.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode):
            raise RunError("previous result paths must be regular files, not links or directories")
        previous.append((source, info))
    if not previous:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    archive = Path(history) / f"{stamp}-{os.getpid()}"
    archive.mkdir(mode=0o700)
    for source, info in previous:
        destination = archive / source.name
        try:
            os.replace(source, destination)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            _copy_across_filesystems(source, destination, info)
    return archive


def _run(argv, environment, *, capture=True, timeout=60):
    # Docker executable was checked as root-owned; all argv construction is
    # internal, and values from Compose are validated. No shell is involved.
    return subprocess.run(argv, env=environment, capture_output=capture, text=True,  # nosec B603
                          check=True, timeout=timeout)


def main():
    if len(sys.argv) != 1:
        print("Usage: sudo /srv/psb/run-batch (no arguments)", file=sys.stderr)
        return 64
    if os.geteuid() != 0:
        print("Run the installed helper with sudo.", file=sys.stderr)
        return 77
    os.umask(0o077)
    install = Path(__file__).resolve().parent
    lock_fd = None
    docker = None
    environment = {"PATH": PATH, "HOME": pwd.getpwuid(0).pw_dir}
    running = False
    try:
        for directory in (install, *install.parents):
            require_root_owned(directory, directory=True)
        lock_fd = acquire_lock(install)
        releases = install / "releases"
        require_root_owned(releases, directory=True)
        current_link = install / "current"
        link_info = current_link.lstat()
        if not stat.S_ISLNK(link_info.st_mode) or link_info.st_uid != 0:
            raise RunError("current must be the root-owned prepared-release link")
        release = current_link.resolve(strict=True)
        if release.parent != releases or re.fullmatch(r"[0-9a-f]{64}", release.name) is None:
            raise RunError("current does not select a digest-named prepared release")
        require_root_owned(release, directory=True)
        require_root_owned(release / "compose.yml", mode=0o644)
        require_root_owned(release / ".env", mode=0o600)
        history = install / "results-history"
        require_root_owned(history, directory=True, mode=0o700)
        executable = shutil.which("docker", path=PATH)
        if not executable:
            raise RunError("Docker CLI is unavailable")
        executable = str(Path(executable).resolve(strict=True))
        require_root_owned(executable)
        docker = [executable, "--host", SOCKET]
        info = json.loads(_run(docker + ["info", "--format", "{{json .}}"], environment).stdout)
        validate_host(info)
        compose = docker + ["compose", "--project-name", "psb", "--env-file", str(release / ".env"),
                            "--file", str(release / "compose.yml")]
        configuration = json.loads(_run(compose + ["config", "--format", "json"], environment).stdout)
        image = IMAGE_PREFIX + release.name
        paths = validate_compose(configuration, image)
        check_runtime_paths(paths)
        _run(docker + ["image", "inspect", image, "--format", "{{.Id}}"], environment)
        existing = _run(docker + ["container", "ls", "--all", "--filter", "name=^/psb-batch$",
                                  "--format", "{{.ID}}"], environment).stdout.strip()
        if existing:
            raise RunError("the fixed psb-batch container already exists; inspect it before another run")
        archive = archive_previous(paths["/output"], history)
        if archive:
            print(f"Previous result archived at {archive}", flush=True)

        def interrupted(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, interrupted)
        running = True
        _run(compose + ["run", "--rm", "--no-deps", "--pull", "never", "--name", "psb-batch", "psb"],
             environment, capture=False, timeout=1200)
        running = False
        result = (paths["/output"] / "submission.csv").lstat()
        if not stat.S_ISREG(result.st_mode) or result.st_uid != 10001 or result.st_size == 0:
            raise RunError("batch did not create a fresh regular nonempty submission.csv")
        print("Batch finished with a fresh submission.csv. Review row statuses and answer quality.")
        return 0
    except BlockingIOError:
        print("Another batch holds the deployment lock; no new batch was started.", file=sys.stderr)
        return 75
    except KeyboardInterrupt:
        print("Batch interrupted; any current CSV belongs to the interrupted run.", file=sys.stderr)
        return 130
    except RunError as exc:
        print(f"Batch refused: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as exc:
        # Do not reflect daemon info, rendered config, response bodies or secrets.
        print(f"Batch failed: {type(exc).__name__}; a previous CSV is not this run's result.", file=sys.stderr)
        return 1
    finally:
        if running and docker:
            try:
                _run(docker + ["stop", "--time", "10", "psb-batch"], environment, timeout=30)
            except (OSError, subprocess.SubprocessError):
                print("Check the psb-batch container state before another attempt.", file=sys.stderr)
        if lock_fd is not None:
            os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
