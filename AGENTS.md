# Agent Notes

- This application requires CUDA to run.
- On startup, the service must verify `torch` imports and `torch.cuda.is_available()` is true.
- If CUDA is unavailable, startup must fail fast with a clear runtime error.
- Do not relax this requirement without explicit user approval.
