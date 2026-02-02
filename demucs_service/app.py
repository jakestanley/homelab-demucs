from __future__ import annotations

import os
import shutil
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

from .config import Settings
from .job_store import JobStore
from .storage import ArtifactStore
from .utils import sanitize_filename
from .worker import WorkerManager


def check_cuda_or_raise() -> dict:
    try:
        import torch
    except Exception as exc:
        raise RuntimeError(f"CUDA check failed: unable to import torch ({exc})") from exc

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available; refusing to start.")

    return {
        "cuda_available": True,
        "cuda_device_count": torch.cuda.device_count(),
        "cuda_device_name": torch.cuda.get_device_name(0),
        "torch_cuda_version": getattr(torch.version, "cuda", None),
    }


def _sniff_mp3(file_storage) -> bool:
    stream = file_storage.stream
    try:
        head = stream.read(4096)
    except Exception:
        return False
    finally:
        try:
            stream.seek(0)
        except Exception:
            pass
    if not head:
        return False
    if head.startswith(b"ID3"):
        return True
    for idx in range(len(head) - 1):
        if head[idx] == 0xFF and (head[idx + 1] & 0xE0) == 0xE0:
            return True
    return False


def create_app(settings: Settings) -> Flask:
    if settings.demucs_device.lower() != "cuda":
        raise RuntimeError("DEMUCS_DEVICE must be 'cuda'; refusing to start.")
    cuda_info = check_cuda_or_raise()
    demucs_path = _resolve_demucs_bin(settings.demucs_bin)
    if not demucs_path:
        raise RuntimeError(
            "Demucs CLI not found. Install Demucs on the host or set DEMUCS_BIN to a full path."
        )
    app = Flask(__name__, static_folder="static")

    job_store = JobStore(settings.storage_root)
    artifact_store = ArtifactStore(settings.storage_root, settings.output_format_version)
    worker = WorkerManager(
        job_store=job_store,
        artifact_store=artifact_store,
        demucs_bin=demucs_path,
        demucs_device=settings.demucs_device,
        max_concurrent_jobs=settings.max_concurrent_jobs,
    )

    @app.get("/")
    def index() -> object:
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/status")
    def status() -> object:
        worker_status = worker.status()
        return jsonify(
            {
                "service": "demucs",
                "paused": worker_status["paused"],
                "running_jobs": worker_status["running_jobs"],
                "max_concurrent_jobs": settings.max_concurrent_jobs,
                "storage_volume": _storage_volume_status(settings.storage_root),
                "cuda": cuda_info,
            }
        )

    @app.post("/api/start")
    def start_worker() -> object:
        worker.resume()
        return jsonify({"ok": True, "paused": False})

    @app.post("/api/stop")
    def stop_worker() -> object:
        worker.pause()
        return jsonify({"ok": True, "paused": True})

    @app.post("/api/admin/clear-caches")
    def clear_caches() -> object:
        worker_status = worker.status()
        if worker_status["running_jobs"]:
            return (
                jsonify(
                    {
                        "error": "Cannot clear caches while jobs are running.",
                        "running_jobs": worker_status["running_jobs"],
                    }
                ),
                409,
            )
        worker.pause()
        shutil.rmtree(artifact_store.artifacts_root, ignore_errors=True)
        shutil.rmtree(job_store.jobs_root, ignore_errors=True)
        artifact_store.artifacts_root.mkdir(parents=True, exist_ok=True)
        job_store.jobs_root.mkdir(parents=True, exist_ok=True)
        return jsonify(
            {
                "ok": True,
                "paused": True,
                "cleared": {
                    "artifacts_root": str(artifact_store.artifacts_root),
                    "jobs_root": str(job_store.jobs_root),
                },
            }
        )

    @app.get("/api/models")
    def models() -> object:
        return jsonify(
            {
                "default": settings.demucs_default_model,
                "models": settings.demucs_models,
            }
        )

    @app.post("/api/jobs")
    def create_job() -> object:
        mode = request.form.get("mode", "4")
        model = request.form.get("model", settings.demucs_default_model)
        job_name = request.form.get("job_name")
        if mode not in {"4", "2", "both"}:
            return jsonify({"error": "Invalid mode."}), 400
        if model not in settings.demucs_models:
            return jsonify({"error": "Unknown model."}), 400

        files = request.files.getlist("files[]") or request.files.getlist("files")
        if not files:
            return jsonify({"error": "No files uploaded."}), 400

        input_entries = []
        for file_storage in files:
            if not file_storage.filename:
                continue
            name = file_storage.filename
            if not name.lower().endswith(".mp3"):
                return jsonify({"error": f"Only mp3 files supported: {name}"}), 400
            if not _sniff_mp3(file_storage):
                return jsonify({"error": f"Invalid mp3 data: {name}"}), 400
            input_entries.append(file_storage)

        if not input_entries:
            return jsonify({"error": "No valid mp3 files uploaded."}), 400

        job = job_store.create_job(
            input_payload={"mode": mode, "model": model, "files": []},
            total_files=len(input_entries),
            job_name=job_name,
        )

        input_dir = job_store.job_input_dir(job["id"])
        stored_entries = []
        for idx, file_storage in enumerate(input_entries, start=1):
            safe_name = sanitize_filename(file_storage.filename)
            stored_name = f"{idx:03d}-{safe_name}"
            target_path = input_dir / stored_name
            file_storage.save(target_path)
            file_hash = artifact_store.compute_file_hash(target_path)
            stored_entries.append(
                {
                    "input_index": idx,
                    "name": file_storage.filename,
                    "stored_name": stored_name,
                    "size_bytes": target_path.stat().st_size,
                    "sha256": file_hash,
                }
            )

        def updater(job_doc: dict) -> dict:
            job_doc["input"]["files"] = stored_entries
            return job_doc

        job_store.update_job(job["id"], updater)
        return jsonify({"id": job["id"]})

    @app.get("/api/jobs")
    def list_jobs() -> object:
        status = request.args.get("status")
        limit = request.args.get("limit")
        limit_value = int(limit) if limit and limit.isdigit() else None
        jobs = job_store.list_jobs(status=status, limit=limit_value)
        return jsonify({"jobs": jobs})

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id: str) -> object:
        job = job_store.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(job)

    @app.get("/api/jobs/<job_id>/output")
    def download_output(job_id: str) -> object:
        job = job_store.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        output = job.get("output", {})
        if not output.get("ready"):
            return jsonify({"error": "Output not ready"}), 400
        zip_path = job_store.job_output_zip_path(job_id)
        if not zip_path.exists():
            return jsonify({"error": "Output missing"}), 404
        return send_file(zip_path, mimetype="application/zip", as_attachment=True)

    @app.get("/static/<path:path>")
    def static_files(path: str) -> object:
        return send_from_directory(app.static_folder, path)

    return app


def _resolve_demucs_bin(demucs_bin: str) -> str | None:
    if not demucs_bin:
        return None
    if os.path.isabs(demucs_bin) or demucs_bin.lower().endswith(".exe"):
        return demucs_bin if Path(demucs_bin).exists() else None
    resolved = shutil.which(demucs_bin)
    return resolved or None


def _storage_volume_status(storage_root: Path) -> dict:
    resolved_root = storage_root
    try:
        resolved_root = storage_root.resolve()
    except OSError:
        pass
    volume_root = Path(resolved_root.anchor) if resolved_root.anchor else resolved_root
    usage = shutil.disk_usage(volume_root)
    return {
        "path": str(volume_root),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
    }

