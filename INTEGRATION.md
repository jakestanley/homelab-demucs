# Integration Guide

This document describes the Demucs HTTP API for single-file job submission.

## API docs endpoints

- Interactive docs: `/docs`
- OpenAPI JSON: `/openapi.json`

## Contract Notes

- The OpenAPI document is the source of truth for request/response schemas, status codes, examples, and endpoint semantics.
- The service uses a single-file async contract:
  - `POST /api/jobs` accepts exactly one `.mp3` and returns `202 Accepted`.
  - `GET /api/jobs/{job_id}` returns job status/progress.
  - `GET /api/jobs/{job_id}/result` returns the zip artifact when ready.
- Error responses follow the shared shape: `error`, `message`, optional `details`, optional `request_id`.
- Queue visibility is exposed via `GET /api/jobs`, including `queue_position` (FIFO semantics for queued jobs).
