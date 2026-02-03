# homelab-demucs

Windows-first HTTP service that accepts MP3 separation jobs and runs the Demucs CLI on the same machine.

## Runtime

- Windows service via NSSM (preferred)
- Runs on the host without Docker
- Ingress, DNS, and ports are defined in `homelab-infra/registry.yaml` (service: `demucs`)

## Requirements

- CUDA-capable NVIDIA GPU and drivers
- PyTorch installed with CUDA support (`torch.cuda.is_available()` must be true)
- Demucs installed and runnable (`demucs` on PATH unless overridden)
- Python 3.10+ recommended

## Environment

Copy `.env.example` to `.env` and adjust if needed:

- `HOST` (default `0.0.0.0`)
- `PORT` (default `20033`)
- `STORAGE_ROOT` (default `D:\demucs`)
- `MAX_CONCURRENT_JOBS` (default `1`)
- `DEMUCS_DEFAULT_MODEL`
- `DEMUCS_MODELS` (comma-separated list)
- `DEMUCS_BIN` (path or command for demucs CLI)
- `DEMUCS_DEVICE` (must be `cuda`; service fails startup otherwise)
- `JOB_TIMEOUT_SECONDS` (default `180`; job fails if it exceeds this runtime)
- `OUTPUT_FORMAT_VERSION` (artifact signature salt)

## Run manually

```powershell
.\scripts\up.ps1
```

If Python is not on PATH, pass `-PythonExe` or set `DEMUCS_PYTHON_EXE`.

## Install as a Windows service (NSSM)

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
- `POST /api/start`
- `POST /api/stop`
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
