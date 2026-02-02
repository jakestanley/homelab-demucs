from __future__ import annotations

import threading
import uuid
from pathlib import Path

from .utils import atomic_write_json, utc_now_iso


VALID_STATUSES = {"queued", "running", "succeeded", "failed"}
VALID_TRANSITIONS = {
    "queued": {"running", "failed"},
    "running": {"succeeded", "failed"},
    "succeeded": set(),
    "failed": set(),
}


def validate_transition(current: str, new: str) -> bool:
    if current == new:
        return True
    return new in VALID_TRANSITIONS.get(current, set())


class JobStore:
    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root
        self.jobs_root = storage_root / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._rehydrate_running_jobs()

    def _rehydrate_running_jobs(self) -> None:
        for job_path in self.jobs_root.glob("*/job.json"):
            job = self._read_job(job_path)
            if job.get("status") == "running":
                job["status"] = "failed"
                job["message"] = "Service restarted while job was running."
                job["error"] = "Service restarted while job was running."
                job["finished_at"] = utc_now_iso()
                self._write_job(job_path, job)

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_root / job_id / "job.json"

    def _read_job(self, path: Path) -> dict:
        import json

        return json.loads(path.read_text(encoding="utf-8"))

    def _write_job(self, path: Path, job: dict) -> None:
        atomic_write_json(path, job)

    def create_job(
        self, input_payload: dict, total_files: int, job_name: str | None
    ) -> dict:
        job_id = uuid.uuid4().hex
        now = utc_now_iso()
        job = {
            "id": job_id,
            "status": "queued",
            "message": "Queued",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "progress": {
                "total": total_files,
                "processed": 0,
                "errors": 0,
                "step": "queued",
            },
            "input": {
                "mode": input_payload.get("mode"),
                "model": input_payload.get("model"),
                "job_name": job_name,
                "files": input_payload.get("files", []),
            },
            "output": {
                "ready": False,
            },
            "error": None,
        }
        path = self._job_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_job(path, job)
        return job

    def list_jobs(self, status: str | None = None, limit: int | None = None) -> list[dict]:
        jobs = []
        for job_path in self.jobs_root.glob("*/job.json"):
            job = self._read_job(job_path)
            if status and job.get("status") != status:
                continue
            jobs.append(job)
        jobs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        if limit:
            return jobs[:limit]
        return jobs

    def get_job(self, job_id: str) -> dict | None:
        path = self._job_path(job_id)
        if not path.exists():
            return None
        return self._read_job(path)

    def update_job(self, job_id: str, updater) -> dict:
        path = self._job_path(job_id)
        with self._lock:
            job = self._read_job(path)
            updated = updater(job)
            self._validate_job_update(job, updated)
            self._write_job(path, updated)
        return updated

    def _validate_job_update(self, current: dict, updated: dict) -> None:
        current_status = current.get("status")
        new_status = updated.get("status")
        if current_status not in VALID_STATUSES or new_status not in VALID_STATUSES:
            raise ValueError("Invalid job status.")
        if not validate_transition(current_status, new_status):
            raise ValueError(f"Invalid transition {current_status} -> {new_status}")
        current_progress = current.get("progress", {})
        new_progress = updated.get("progress", {})
        for key in ("total", "processed", "errors"):
            if new_progress.get(key, 0) < current_progress.get(key, 0):
                raise ValueError("Progress counters cannot decrease.")
        if new_progress.get("processed", 0) + new_progress.get("errors", 0) > new_progress.get(
            "total", 0
        ):
            raise ValueError("Progress counters exceed total.")

    def update_progress(
        self,
        job_id: str,
        *,
        processed_inc: int = 0,
        errors_inc: int = 0,
        step: str | None = None,
        message: str | None = None,
    ) -> dict:
        def updater(job: dict) -> dict:
            progress = job.setdefault("progress", {})
            progress["processed"] = progress.get("processed", 0) + processed_inc
            progress["errors"] = progress.get("errors", 0) + errors_inc
            if step:
                progress["step"] = step
            if message:
                job["message"] = message
            return job

        return self.update_job(job_id, updater)

    def set_status(
        self, job_id: str, status: str, *, message: str | None = None, error: str | None = None
    ) -> dict:
        def updater(job: dict) -> dict:
            job["status"] = status
            if message:
                job["message"] = message
            if status == "running" and job.get("started_at") is None:
                job["started_at"] = utc_now_iso()
            if status in {"succeeded", "failed"}:
                job["finished_at"] = utc_now_iso()
            if error:
                job["error"] = error
            return job

        return self.update_job(job_id, updater)

    def set_output(
        self,
        job_id: str,
        *,
        artifact_name: str,
        content_type: str,
        size_bytes: int,
        signature: str,
        manifest: dict | None = None,
    ) -> dict:
        def updater(job: dict) -> dict:
            job["output"] = {
                "ready": True,
                "artifact_name": artifact_name,
                "content_type": content_type,
                "size_bytes": size_bytes,
                "signature": signature,
            }
            if manifest:
                job["output"]["manifest"] = manifest
            return job

        return self.update_job(job_id, updater)

    def job_input_dir(self, job_id: str) -> Path:
        path = self.jobs_root / job_id / "inputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_output_zip_path(self, job_id: str) -> Path:
        return self.jobs_root / job_id / "output.zip"
