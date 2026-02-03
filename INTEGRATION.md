# Integration Guide

This document describes the Demucs HTTP API for single-file job submission.

## API docs endpoints

- Interactive docs: `/docs`
- OpenAPI JSON: `/openapi.json`

## Contract Notes

- `POST /api/jobs` accepts exactly one uploaded `.mp3` per job.
- Required form fields: `mode`, `model`.
- Optional form field: `job_label` (display/log metadata only).
- If zero or multiple files are submitted, the API returns `400` with:
  - `Exactly one file is supported per job; multi-file uploads are not supported.`
- Error payloads use:
  - `error` (machine-readable snake_case code)
  - `message` (human-readable text)
  - optional `details`, `request_id`
- Job creation returns `202 Accepted`.
- `job_id` is the only job identity.
- Output zip contains deterministic top-level directories only:
  - `all/` for mode `4` (or `both`)
  - `vocals/` for mode `2` (or `both`)
- Result download endpoints:
  - `GET /api/jobs/{job_id}/output`
  - `GET /api/jobs/{job_id}/result` (alias)
- Non-ready results return `409 Conflict`.
- `GET /api/jobs` includes queue-observable fields:
  - `created_at`, `started_at`, `finished_at`, `progress`, `queue_position`
