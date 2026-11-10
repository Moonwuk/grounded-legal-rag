# Prepare an existing Docker host

This playbook prepares a batch release on an existing Debian/Ubuntu host with
Docker Engine, Docker Compose, Python, SSH access and privilege escalation already
configured. It does not create cloud resources, install Docker, change SSH or
firewall rules, or start a model-consuming batch.

The host must provide a system Docker daemon at `/var/run/docker.sock`, Linux
amd64, functional memory/PID/CPU quota limits, and the default seccomp profile.
Rootless Docker and user-namespace remapping are rejected: these bind mounts
require container UID `10001` to correspond to host UID `10001`. The role does not
reconfigure the daemon to satisfy this requirement.
The playbook checks these actual daemon capabilities privately rather than
printing `docker info`, which may include proxy or registry configuration.

## Trust and inputs

The controller needs a recent authenticated GitHub CLI with `gh attestation
verify` and registry access. The role refuses a mutable image reference and
verifies the image digest against GitHub OIDC provenance from
`Moonwuk/grounded-legal-rag/.github/workflows/security.yml`, `refs/heads/main`,
and the operator's expected 40-character source commit. Self-hosted builder
attestations are rejected. Verification failure or an older CLI stops deployment
before `docker pull`; the role does not substitute a weaker verification method.

See the [GitHub CLI verification options](https://cli.github.com/manual/gh_attestation_verify).
The source commit must come from the reviewed CI run, rather than from arbitrary
image labels. The controller's registry credentials and the host's pull access
are configured separately; no registry credential is accepted in inventory.

Create a private inventory from `inventory.example.yml`, replacing its
`example.invalid` host. Supply nonsecret overrides through a private YAML file:

- `psb_image`: `ghcr.io/moonwuk/grounded-legal-rag@sha256:<64 lowercase hex>`.
- `psb_source_commit`: the exact reviewed source commit for that image.
- `psb_llm_base_url`: the trusted HTTPS proxy URL, without credentials/query/fragment.
- `psb_llm_model`: the configured model identifier.
- `psb_data_dir`: absolute dedicated directory containing `questions.csv` and
  `knowledge-base.zip`; files must already exist. The role makes these two files
  owner-readable `0400` and owned by UID/GID `10001` without changing their contents.
- `psb_output_dir`: a separate absolute directory; prepared as UID/GID `10001`, mode `0700`.
- `psb_llm_key_file`: an existing, nonempty regular file of at most 8192 bytes,
  provisioned out of band, owned by UID `10001`, mode `0400`. The role reads
  metadata only, never its contents.

Defaults and the bounded CPU, RAM, worker, retrieval and inference settings are
listed in `group_vars/psb.yml`. The image/source defaults are intentionally empty;
the example endpoint and model cannot deploy. Do not put the credential value in
inventory, extra-vars, `.env`, command arguments, or this repository.

Every existing ancestor of the install, data, output and credential paths must
be a real root-owned directory without group/world write access. The role checks
the complete chains and every release/configuration destination before writing,
creates missing parents explicitly as root, and never follows destination
symlinks. Existing data/output directories and the two input files must belong
to root or UID `10001`; arbitrary user-owned trees are refused. Only the runtime
data/output leaves and input files receive UID `10001`. Use that UID solely for
this workload. The runner repeats the ancestor checks before each batch.

## Validation and preparation

From this directory:

```bash
ansible-playbook --syntax-check --inventory inventory.example.yml playbook.yml
ansible-lint --offline --profile safety --strict playbook.yml
ansible-playbook --inventory /absolute/private/inventory.yml \
  --extra-vars @/absolute/private/deployment.yml playbook.yml
```

The last command contacts the controller's GitHub/registry services and the
specified existing host. It prepares `/srv/psb/releases/<image-digest>/` and
switches `/srv/psb/current` only after successful configuration validation and
image pull. The install path can be changed with `psb_install_dir`.

The batch is always explicit:

```bash
sudo /srv/psb/run-batch
```

The root-owned runner accepts no Docker arguments. It takes an exclusive `flock`
on `.batch.lock`, validates the root-owned release/configuration and image digest,
checks the host capabilities again, and uses only the local Docker socket and
project `psb`. Caller environment variables cannot override the prepared Compose
parameters. An already existing `psb-batch` container also prevents another run.

Before starting, the runner archives only the previous `submission.csv` and
`submission.csv.tmp` into a private timestamped directory under
`/srv/psb/results-history/`. It rejects symlinks and supports output/history on
different filesystems. Unrelated output files are left alone. A failed new run
therefore cannot be confused with the previous run's CSV. Failed or interrupted
runs may create a new partial/technical CSV; the helper reports failure and tries
to stop its fixed container. History is retained until the operator removes it;
provide disk space for that retained data.

Inspect the fresh CSV and execution status; a completed container does not
establish the legal accuracy of every answer. Use the installed runner for every
batch so the lock is shared. A host administrator can bypass this convention
with direct Docker access; the helper is not an authorization boundary against
the host administrator. Rollback consists of rerunning the playbook with a
previously approved image digest and its matching source commit; it does not
erase input/output/history data or automatically invoke the old image.

## Network boundary

The service publishes no ports. Its Compose bridge permits outbound traffic to
reach the configured LLM proxy; it is **not an egress allowlist**. Configure and
verify the destination/port restrictions separately in the host, network or
proxy policy. The playbook does not infer those rules or edit the host firewall.
The API credential is accessible to the application process that makes requests;
container hardening does not isolate Python modules from one another.
