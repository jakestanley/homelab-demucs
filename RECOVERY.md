# Recovery Notes

## Prerequisites

- CUDA-capable GPU and drivers
- Demucs installed and callable via `DEMUCS_BIN`
- Python environment (local `.venv` created by `scripts/up.ps1`)

## Recovery Order

1. Verify CUDA availability and that `demucs` runs manually on the host.
2. Ensure `homelab-infra` and `homelab-standards` are clean and at default branch HEAD.
3. Run `scripts/up.ps1` to recreate `.venv` and reinstall dependencies.
4. Confirm firewall rule exists for the configured port (Private profile).
5. Reinstall the NSSM service with `scripts/install-service.ps1 -Start`.

## Avoid

- Changing ports locally; use the registry in `homelab-infra`.
- Clearing `storage/` without confirming active jobs and artifact references.
