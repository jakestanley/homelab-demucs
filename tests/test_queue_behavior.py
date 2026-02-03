import tempfile
import threading
import time
import unittest
from pathlib import Path

from demucs_service.job_store import JobStore
from demucs_service.storage import ArtifactStore
from demucs_service.worker import WorkerManager


class FakeWorkerManager(WorkerManager):
    def __init__(self, *args, run_delay: float = 0.05, **kwargs) -> None:
        self.run_delay = run_delay
        self.started: list[str] = []
        self.finished: list[str] = []
        self._activity_lock = threading.Lock()
        self._active_count = 0
        self.max_seen_concurrency = 0
        super().__init__(*args, **kwargs)

    def _process_job(self, job_id: str) -> None:
        with self._activity_lock:
            self.started.append(job_id)
            self._active_count += 1
            self.max_seen_concurrency = max(self.max_seen_concurrency, self._active_count)
        try:
            super()._process_job(job_id)
        finally:
            with self._activity_lock:
                self._active_count -= 1
                self.finished.append(job_id)

    def _run_demucs(
        self,
        job_id: str,
        input_path: Path,
        mode: str,
        model: str,
        signature: str,
        *,
        timeout_seconds: float | None = None,
    ) -> dict:
        if timeout_seconds is not None and self.run_delay > timeout_seconds:
            raise RuntimeError("Job exceeded timeout while running Demucs.")

        def builder(temp_dir: Path) -> None:
            stems_dir = temp_dir / "stems"
            stems_dir.mkdir(parents=True, exist_ok=True)
            stems = (
                ["vocals.wav", "drums.wav", "bass.wav", "other.wav"]
                if mode == "4"
                else ["vocals.wav", "no_vocals.wav"]
            )
            for stem_name in stems:
                (stems_dir / stem_name).write_bytes(b"wav")
            self.artifact_store.write_meta(
                temp_dir,
                {
                    "input_name": input_path.name,
                    "mode": mode,
                    "model": model,
                    "signature": signature,
                    "stems": stems,
                },
            )

        time.sleep(self.run_delay)
        self.artifact_store.ensure_artifact(signature, builder)
        return self._artifact_metrics(signature)


def _create_job(
    job_store: JobStore,
    artifact_store: ArtifactStore,
    mode: str,
    label: str,
    *,
    input_key: str | None = None,
) -> dict:
    job = job_store.create_job(
        input_payload={"mode": mode, "model": "htdemucs", "file": {}},
        job_label=label,
    )
    input_path = job_store.job_input_dir(job["id"]) / "input.mp3"
    key = input_key if input_key is not None else label
    input_path.write_bytes(f"ID3demo-mp3-{key}".encode("utf-8"))
    file_hash = artifact_store.compute_file_hash(input_path)

    def updater(doc: dict) -> dict:
        doc["input"]["file"] = {
            "original_filename": "track.mp3",
            "stored_name": "input.mp3",
            "size_bytes": input_path.stat().st_size,
            "sha256": file_hash,
        }
        return doc

    job_store.update_job(job["id"], updater)
    return job


def _wait_for_terminal(job_store: JobStore, job_ids: list[str], timeout_seconds: float = 8.0) -> None:
    deadline = time.time() + timeout_seconds
    remaining = set(job_ids)
    while remaining and time.time() < deadline:
        done = []
        for job_id in remaining:
            try:
                job = job_store.get_job(job_id)
            except PermissionError:
                continue
            if job and job.get("status") in {"succeeded", "failed"}:
                done.append(job_id)
        for job_id in done:
            remaining.remove(job_id)
        if remaining:
            time.sleep(0.05)
    if remaining:
        raise AssertionError(f"Jobs did not finish in time: {sorted(remaining)}")


class QueueBehaviorTests(unittest.TestCase):
    def test_queue_ordering_is_fifo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_store = JobStore(root)
            artifact_store = ArtifactStore(root, output_format_version="v1")
            worker = FakeWorkerManager(
                job_store=job_store,
                artifact_store=artifact_store,
                demucs_bin="demucs",
                demucs_device="cuda",
                max_concurrent_jobs=1,
                run_delay=0.02,
            )
            worker.resume()

            jobs = []
            for idx in range(6):
                jobs.append(_create_job(job_store, artifact_store, "4", f"label-{idx}"))
                time.sleep(0.002)

            ids = [job["id"] for job in jobs]
            _wait_for_terminal(job_store, ids)
            self.assertEqual(worker.started[: len(ids)], ids)

    def test_max_concurrency_respected_and_many_jobs_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_store = JobStore(root)
            artifact_store = ArtifactStore(root, output_format_version="v1")
            worker = FakeWorkerManager(
                job_store=job_store,
                artifact_store=artifact_store,
                demucs_bin="demucs",
                demucs_device="cuda",
                max_concurrent_jobs=3,
                run_delay=0.06,
            )
            worker.resume()

            jobs = [_create_job(job_store, artifact_store, "both", f"job-{idx}") for idx in range(20)]
            ids = [job["id"] for job in jobs]
            _wait_for_terminal(job_store, ids, timeout_seconds=20.0)

            self.assertLessEqual(worker.max_seen_concurrency, 3)
            self.assertEqual(len(set(worker.started)), len(ids))
            self.assertEqual(len(set(worker.finished)), len(ids))
            for job_id in ids:
                job = job_store.get_job(job_id)
                self.assertIsNotNone(job)
                self.assertEqual(job["status"], "succeeded")
                self.assertTrue(job["output"]["ready"])

    def test_job_label_not_used_for_output_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_store = JobStore(root)
            artifact_store = ArtifactStore(root, output_format_version="v1")
            worker = FakeWorkerManager(
                job_store=job_store,
                artifact_store=artifact_store,
                demucs_bin="demucs",
                demucs_device="cuda",
                max_concurrent_jobs=1,
                run_delay=0.01,
            )
            worker.resume()

            first = _create_job(job_store, artifact_store, "4", "alpha-label", input_key="shared")
            second = _create_job(job_store, artifact_store, "4", "beta-label", input_key="shared")
            _wait_for_terminal(job_store, [first["id"], second["id"]])

            first_doc = job_store.get_job(first["id"])
            second_doc = job_store.get_job(second["id"])
            self.assertIsNotNone(first_doc)
            self.assertIsNotNone(second_doc)
            self.assertNotEqual(first_doc["input"]["job_label"], second_doc["input"]["job_label"])
            self.assertEqual(first_doc["output"]["signature"], second_doc["output"]["signature"])

    def test_job_fails_when_runtime_exceeds_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_store = JobStore(root)
            artifact_store = ArtifactStore(root, output_format_version="v1")
            worker = FakeWorkerManager(
                job_store=job_store,
                artifact_store=artifact_store,
                demucs_bin="demucs",
                demucs_device="cuda",
                max_concurrent_jobs=1,
                run_delay=1.2,
                job_timeout_seconds=1,
            )
            worker.resume()

            job = _create_job(job_store, artifact_store, "4", "slow-job")
            _wait_for_terminal(job_store, [job["id"]], timeout_seconds=5.0)

            doc = job_store.get_job(job["id"])
            self.assertIsNotNone(doc)
            assert doc is not None
            self.assertEqual(doc["status"], "failed")
            self.assertIn("timeout", (doc.get("error") or "").lower())


if __name__ == "__main__":
    unittest.main()
