# Integration Guide

This document describes the Demucs HTTP API and includes an OpenAPI spec
so you can integrate a consuming application quickly.

## Overview

- Base URL (nginx proxy): `https://demucs.stanley.arpa`
- Auth: none
- Content types:
  - JSON for all control/status endpoints
  - `multipart/form-data` for job submission
  - `application/zip` for output downloads

## Notes for integrators

- This service invokes the host Demucs CLI. CUDA availability depends on how
  Demucs is installed on the host. The API does not attempt to detect CUDA
  support from the executable.
- The service defaults to `DEMUCS_DEVICE=cuda`; set it to `cpu` if you need to
  force CPU execution.
- Only `.mp3` uploads are accepted.
- `mode` values:
  - `4` = 4 stems (vocals, drums, bass, other)
  - `2` = 2 stems (vocals, no_vocals)
  - `both` = run both modes and include both in the output zip

## OpenAPI 3.0 spec (YAML)

```yaml
openapi: 3.0.3
info:
  title: Demucs Local Service API
  version: 1.0.0
servers:
  - url: https://demucs.stanley.arpa
paths:
  /api/status:
    get:
      summary: Get service status
      responses:
        "200":
          description: Service status
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/StatusResponse"
  /api/start:
    post:
      summary: Resume job processing
      responses:
        "200":
          description: Worker resumed
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/PauseResponse"
  /api/stop:
    post:
      summary: Pause job processing
      responses:
        "200":
          description: Worker paused
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/PauseResponse"
  /api/models:
    get:
      summary: List available models
      responses:
        "200":
          description: Models list
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ModelsResponse"
  /api/jobs:
    get:
      summary: List jobs
      parameters:
        - in: query
          name: status
          schema:
            type: string
            enum: [queued, running, succeeded, failed]
          description: Filter by job status
        - in: query
          name: limit
          schema:
            type: integer
            minimum: 1
          description: Max jobs to return
      responses:
        "200":
          description: Jobs list
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/JobsResponse"
    post:
      summary: Create a separation job
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required: [mode, model, files]
              properties:
                mode:
                  type: string
                  enum: ["4", "2", "both"]
                model:
                  type: string
                  description: Demucs model name
                job_name:
                  type: string
                  description: Optional display name
                files:
                  type: array
                  items:
                    type: string
                    format: binary
                  description: MP3 files (field name `files`)
                files[]:
                  type: array
                  items:
                    type: string
                    format: binary
                  description: MP3 files (field name `files[]`)
      responses:
        "200":
          description: Job created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/CreateJobResponse"
        "400":
          description: Invalid request
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
  /api/jobs/{job_id}:
    get:
      summary: Get job details
      parameters:
        - in: path
          name: job_id
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Job details
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Job"
        "404":
          description: Job not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
  /api/jobs/{job_id}/output:
    get:
      summary: Download job output zip
      parameters:
        - in: path
          name: job_id
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Output zip
          content:
            application/zip:
              schema:
                type: string
                format: binary
        "400":
          description: Output not ready
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "404":
          description: Job or output missing
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
components:
  schemas:
    StatusResponse:
      type: object
      properties:
        service:
          type: string
          example: demucs
        paused:
          type: boolean
        running_jobs:
          type: array
          items:
            type: string
        max_concurrent_jobs:
          type: integer
      required: [service, paused, running_jobs, max_concurrent_jobs]
    PauseResponse:
      type: object
      properties:
        ok:
          type: boolean
        paused:
          type: boolean
      required: [ok, paused]
    ModelsResponse:
      type: object
      properties:
        default:
          type: string
        models:
          type: array
          items:
            type: string
      required: [default, models]
    JobsResponse:
      type: object
      properties:
        jobs:
          type: array
          items:
            $ref: "#/components/schemas/Job"
      required: [jobs]
    CreateJobResponse:
      type: object
      properties:
        id:
          type: string
      required: [id]
    ErrorResponse:
      type: object
      properties:
        error:
          type: string
      required: [error]
    Job:
      type: object
      properties:
        id:
          type: string
        status:
          type: string
          enum: [queued, running, succeeded, failed]
        message:
          type: string
        created_at:
          type: string
          format: date-time
        started_at:
          type: string
          format: date-time
          nullable: true
        finished_at:
          type: string
          format: date-time
          nullable: true
        progress:
          $ref: "#/components/schemas/JobProgress"
        input:
          $ref: "#/components/schemas/JobInput"
        output:
          $ref: "#/components/schemas/JobOutput"
        error:
          type: string
          nullable: true
      required:
        [id, status, message, created_at, progress, input, output, error]
    JobProgress:
      type: object
      properties:
        total:
          type: integer
        processed:
          type: integer
        errors:
          type: integer
        step:
          type: string
      required: [total, processed, errors, step]
    JobInput:
      type: object
      properties:
        mode:
          type: string
          enum: ["4", "2", "both"]
        model:
          type: string
        job_name:
          type: string
          nullable: true
        files:
          type: array
          items:
            $ref: "#/components/schemas/JobInputFile"
      required: [mode, model, job_name, files]
    JobInputFile:
      type: object
      properties:
        name:
          type: string
        stored_name:
          type: string
        size_bytes:
          type: integer
        sha256:
          type: string
        results:
          type: array
          items:
            $ref: "#/components/schemas/JobFileResult"
      required: [name, stored_name, size_bytes, sha256]
    JobFileResult:
      type: object
      properties:
        mode:
          type: string
          enum: ["4", "2"]
        signature:
          type: string
        cache_hit:
          type: boolean
        error:
          type: string
    JobOutput:
      type: object
      properties:
        ready:
          type: boolean
        artifact_name:
          type: string
          nullable: true
        content_type:
          type: string
          nullable: true
        size_bytes:
          type: integer
          nullable: true
        signature:
          type: string
          nullable: true
      required: [ready]
```
