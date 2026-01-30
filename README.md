# homelab-demucs

Windows-first HTTP service that accepts MP3 separation jobs and runs the Demucs CLI on the same machine.

## Runtime

- Windows service via NSSM (preferred)
- Runs on the host without Docker
- Ingress, DNS, and ports are defined in `homelab-infra/registry.yaml` (service: `demucs`)

## Requirements

- Demucs installed and runnable (`demucs` on PATH unless overridden)
- Python 3.10+ recommended

Recommended:

- A CUDA-enabled Demucs build on a host with an NVIDIA GPU for faster processing

## Environment

Copy `.env.example` to `.env` and adjust if needed:

- `HOST` (default `0.0.0.0`)
- `PORT` (default `20033`)
- `STORAGE_ROOT` (default `storage`)
- `MAX_CONCURRENT_JOBS` (default `1`)
- `DEMUCS_DEFAULT_MODEL`
- `DEMUCS_MODELS` (comma-separated list)
- `DEMUCS_BIN` (path or command for demucs CLI)
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

Control plane:

- `GET /api/status`
- `POST /api/start`
- `POST /api/stop`
- `GET /api/models`

Work plane:

- `POST /api/jobs` (multipart/form-data, fields: `mode`, `model`, `job_name`, files: `files[]`)
- `GET /api/jobs`
- `GET /api/jobs/{id}`
- `GET /api/jobs/{id}/output` (zip)

### curl example

```bash
curl -F "mode=4" -F "model=htdemucs" -F "files[]=@track.mp3" https://demucs.stanley.arpa/api/jobs
```

### Output zip layout

```
{job_id}/
  {track_name}/
    4/
      vocals.wav
      drums.wav
      bass.wav
      other.wav
    2/
      vocals.wav
      no_vocals.wav
```

## Notes

- Job metadata and artifacts are stored under `STORAGE_ROOT` and survive restarts.
- `scripts/up.ps1` creates the Windows Firewall rule for the configured port when run elevated.
- The service uses the host Demucs CLI; set `DEMUCS_BIN` to a full path if it is not on PATH.
