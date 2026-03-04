# homelab-demucs

Host-run HTTP service that accepts MP3 separation jobs and runs the Demucs CLI on the same machine.

## Runtime Model

- Windows host service via NSSM
- Linux host service via systemd
- Runs directly on the host without Docker
- Ingress, DNS, ports, and exposure are managed in `homelab-infra` for service `demucs`; do not add local repo-specific ingress wiring here

The canonical host entrypoints are:

- Windows: `scripts/up.ps1`
- Linux: `scripts/up.sh`
- Stable Python process entrypoint: `python -m demucs_service.server`

## Required Dependencies

- `systemd` for Linux service supervision and journald logging
- Python 3.10+ with the packages in `requirements.txt`
- PyTorch installed with CUDA support
- CUDA-capable NVIDIA GPU and drivers
- Demucs installed and runnable via `DEMUCS_BIN`

Recommended verification commands:

```bash
systemctl --version && systemd-analyze --version
test -x /absolute/path/to/python3
command -v demucs
/absolute/path/to/python3 -c "import torch; print(torch.cuda.is_available())"
```

Startup fails fast if `torch` cannot be imported, if `torch.cuda.is_available()` is false, if `DEMUCS_DEVICE` is not `cuda`, or if the Demucs CLI cannot be resolved.

## Configuration

Application env:

- `.env.example` documents the app env vars used for manual runs
- `systemd/demucs.env.example` is the host template for `/etc/demucs/demucs.env`

Relevant variables:

- `HOST`: bind address, default `0.0.0.0`
- `PORT`: bind port; keep this aligned with `homelab-infra`
- `STORAGE_ROOT`: writable root for job inputs, artifacts, and output zips; all Demucs I/O lives under this path and it must be host-configurable
- `MAX_CONCURRENT_JOBS`: max active Demucs jobs
- `DEMUCS_DEFAULT_MODEL`
- `DEMUCS_MODELS`: comma-separated allowed models
- `DEMUCS_BIN`: Demucs executable path or command name
- `DEMUCS_DEVICE`: must stay `cuda`
- `JOB_TIMEOUT_SECONDS`
- `OUTPUT_FORMAT_VERSION`: artifact signature salt
- `DEMUCS_PYTHON_EXE`: optional interpreter override for `scripts/up.sh` and `scripts/up.ps1`

## Manual Run

Windows:

```powershell
.\scripts\up.ps1
```

Linux:

```bash
./scripts/up.sh
```

If the Python interpreter is not discoverable, set `DEMUCS_PYTHON_EXE` to an absolute path.

## Install As A Linux systemd Service

The provided unit template assumes the repo is installed at `/srv/demucs`.

1. Copy the repo to `/srv/demucs`.
2. Copy `systemd/demucs.env.example` to `/etc/demucs/demucs.env` and fill in host-specific values.
3. Copy `systemd/demucs.service` to `/etc/systemd/system/demucs.service`.
4. Create the dedicated runtime account if it does not exist:

```bash
sudo groupadd --system demucs
sudo useradd --system --gid demucs --home-dir /var/lib/demucs --create-home --shell /usr/sbin/nologin demucs
sudo install -d -o demucs -g demucs /var/lib/demucs
```

5. Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now demucs.service
```

Logs go to journald:

```bash
journalctl -u demucs.service -f
```

## Install As A Windows Service (NSSM)

```powershell
.\scripts\install-service.ps1 -Start
```

To uninstall:

```powershell
.\scripts\install-service.ps1 -Stop -Uninstall
```

## API

See `INTEGRATION.md` for the full OpenAPI spec and integration notes.
Live docs are available at `/docs`, with spec endpoint at `/openapi.json`.

Control plane:

- `GET /api/status`
- `GET /api/models`

Work plane:

- `POST /api/jobs` (multipart/form-data, fields: `mode`, `model`, optional `job_label`, exactly one `file`)
- `GET /api/jobs`
- `GET /api/jobs/{id}`
- `GET /api/jobs/{id}/result` (zip)

### curl example

```bash
curl -F "mode=4" -F "model=htdemucs" -F "job_label=my-run" -F "file=@track.mp3" https://demucs.stanley.arpa/api/jobs
```

### Output zip layout

```
all/
  vocals.wav
  drums.wav
  bass.wav
  other.wav
vocals/
  vocals.wav
  no_vocals.wav
```

## Notes

- Job metadata and artifacts are stored under `STORAGE_ROOT` and survive restarts.
- `scripts/up.ps1` creates the Windows Firewall rule for the configured port when run elevated.
- The service uses the host Demucs CLI; set `DEMUCS_BIN` to a full path if it is not on PATH.
- Startup fails fast if PyTorch CUDA is unavailable.
