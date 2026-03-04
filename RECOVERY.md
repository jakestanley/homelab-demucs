# Recovery Notes

## Prerequisites

- CUDA-capable NVIDIA GPU and drivers
- PyTorch installed with CUDA support, with `torch.cuda.is_available()` returning `True`
- Demucs installed and callable via `DEMUCS_BIN`
- Python interpreter available for the chosen host runtime
- Linux hosts: `systemd`, `systemctl`, `systemd-analyze`, and `journalctl`
- Windows hosts: NSSM available on PATH

Recommended verification commands:

```bash
command -v demucs
/absolute/path/to/python3 -c "import torch; print(torch.cuda.is_available())"
systemctl --version
systemd-analyze --version
journalctl --version
```

## Service User And Group

- Linux systemd runtime: `demucs:demucs`
- Windows NSSM runtime: use the host service account configured in NSSM

## Recovery Order

1. Restore the repo contents to the host path used by the runtime.
   Linux unit template expects `/srv/demucs`.
2. Restore the host env/config.
   Linux: `/etc/demucs/demucs.env` from `systemd/demucs.env.example`.
   Manual app env: repo-local `.env` from `.env.example` when used.
3. Restore writable state under `STORAGE_ROOT`.
   This path contains job inputs, cached artifacts, and output zips for Demucs work.
4. Restore the service definition.
   Linux: `/etc/systemd/system/demucs.service` from `systemd/demucs.service`.
   Windows: reinstall/update via `scripts/install-service.ps1`.
5. Ensure the runtime account owns the writable storage path.
   Linux example: `chown -R demucs:demucs /var/lib/demucs`.
6. Start and re-enable the service.

Linux:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now demucs.service
sudo systemctl status demucs.service
journalctl -u demucs.service -n 100
```

Windows:

```powershell
.\scripts\install-service.ps1 -Start
```

## Avoid

- Changing ports locally; keep bind-port configuration aligned with `homelab-infra`.
- Clearing `STORAGE_ROOT` casually; it contains persisted job metadata and cached Demucs artifacts.
