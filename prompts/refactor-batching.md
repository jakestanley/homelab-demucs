# 3rd February 2026

Please refactor the Demucs API to remove batch uploads and switch to single-file jobs only.

Objective
- Simplify identity and output mapping to the point where filename normalization is unnecessary.
- Client will submit many single-file jobs; server must queue/process them reliably.
- Batch submission support is no longer required and must be removed.

New Contract (single-file jobs)

1) Job creation
- Endpoint: `POST /api/jobs`
- Request: multipart/form-data with exactly one audio file + required params (`mode`, `model`), optional `job_label`.
- `job_label` is display/log metadata only; it must never be used for identity, cache keys, output paths, or matching.
- If zero or more than one file is provided, return 400 Bad Request with explicit error:
    - "Exactly one file is supported per job; multi-file uploads are not supported."
    - Do not process partial multi-file payloads.
    - Remove files[] semantics from API docs/spec.

2) Identity
- Server assigns and returns `job_id` (existing behavior).
- Filenames are metadata only.

3) Output ZIP structure (for single-file job)
- Zip contains only:
  - `all/` (if mode 4 or both)
  - `vocals/` (if mode 2 or both)
- No filename-derived directories.
- No ambiguity: one job corresponds to one input file.

4) Job status/details
- Keep status lifecycle (`queued`, `running`, `succeeded`, `failed`).
- Include queue-relevant fields (created, started, finished, progress).
- Include basic input metadata (original filename, size, sha256 if available).

5) Queueing behavior
- Server must support many queued single-file jobs.
- Preserve stable FIFO semantics unless priority is explicitly introduced.
- Enforce max concurrency via worker pool; queued jobs remain durable/visible.
- `GET /api/jobs` should make queue state observable.

6) Backward compatibility / cleanup
- Batch upload (`files[]` / multiple files per job) no longer needs to be supported.
- Remove/deprecate batch-specific manifest mapping structures.

7) API simplification
- Eliminate filename normalization concerns from API contracts.
- Prefer minimal schema and behavior focused on one input -> one job -> one output zip.

Acceptance criteria
- Client can submit N files as N independent jobs with no filename-based logic.
- Repeated runs can dedupe by local hash + mode/model and job success state.
- Output extraction is deterministic and trivial (`all/`, `vocals/` only).
- Queueing works under load (many pending jobs) and is observable.
- Multi-file submission is rejected or clearly deprecated as intended.
- Tests cover:
  - single-file job success for mode 2/4/both
  - queue ordering and concurrency limits
  - many-job enqueue/dequeue stability
  - `job_label` used only for display/logging
  - rejection path for multi-file submission
