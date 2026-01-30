# Prompt: Demucs ML Workload API (local Windows CUDA service)

## Goal
- Build a Windows-first local HTTP service that accepts MP3 separation jobs and runs Demucs locally on the same machine using CUDA.
- Expose an async job API (polling + artifact download) and a minimal single-page dashboard UI (no framework).
- No offloading, no remote execution, and no “prompt” field in requests.

## Patterns to follow (non-negotiable)
- PATTERNS/api-async-job-service.md
- PATTERNS/job-document.md
- PATTERNS/artifact-storage.md
- If installed as a Windows service, also apply PATTERNS/windows-nssm-service.md.

## Assumptions (unless explicitly overridden)
- OS: Windows
- CUDA GPU available and required
- Demucs and torch with CUDA are installed and working
- Environment configuration via .env and python-dotenv
- MAX_CONCURRENT_JOBS defaults to 1

## Hard rules
- Service MUST fail fast at startup if CUDA is not available (no silent CPU fallback).
- Job state MUST be durable across restarts.
- Outputs MUST be downloadable via /api/jobs/{id}/output as a zip artifact.
- API MUST use polling (no websockets).
- Do not introduce a frontend framework.

## API endpoints (match the existing pattern)

### Control plane
- GET /api/status
- POST /api/start
- POST /api/stop
- GET /api/models

### Work plane
- POST /api/jobs
  - multipart/form-data
  - fields: mode (4|2|both), model (optional), job_name (optional)
  - files: files[] (one or more mp3)
  - returns: { id }
- GET /api/jobs (list; support limit/status filters if easy)
- GET /api/jobs/{id} (job document)
- GET /api/jobs/{id}/output (download zip)

## Job document
- Must conform to PATTERNS/job-document.md
- Progress counters should be file-based:
  - total_files, processed_files, error_files mapped into progress.{total,processed,errors}
- Include progress.step and message for UI rendering.

## Artifact storage
- Must conform to PATTERNS/artifact-storage.md
- STORAGE_ROOT defines base storage.
- Use deterministic signature for per-file work:
  - sha256(file) + mode + model + output-format-version
- Dedup allowed:
  - if signature exists, skip processing and mark job as cache hit.

## UI (single-page, vanilla)
- One HTML page served by the API (or a static folder), no framework.
- Shows:
  - status card (from /api/status) including CUDA readiness
  - Start/Stop/Refresh buttons
  - job submit form (model dropdown from /api/models, mode dropdown, multi file picker)
  - running jobs list (from /api/jobs)
  - job monitor view using polling of /api/jobs/{id}
  - download link appears when output.ready is true

## Implementation notes
- Prefer Demucs execution via subprocess invocation in the worker, not in-request.
- Enforce MAX_CONCURRENT_JOBS.
- Ensure atomic writes for job metadata and artifacts (temp then rename/move).
- README must include:
  - required env vars
  - run instructions
  - curl examples
  - output zip layout

## Validation
- Python syntax check on modified files (python -m py_compile).
- Minimal tests for:
  - hashing/signature generation stability
  - job state transition rules

## What not to build
- No remote execution/offload.
- No auth layer unless already present in the base pattern.
- No fancy real-time updates.
- No feature creep beyond MP3 batch separation + download.

## If required vendored standards/patterns are missing
- STOP and report what is missing; do not proceed.
