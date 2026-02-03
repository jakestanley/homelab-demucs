import tempfile
import unittest
import zipfile
from pathlib import Path

from demucs_service.job_store import JobStore
from demucs_service.storage import ArtifactStore
from demucs_service.worker import WorkerManager


class ZipLayoutTests(unittest.TestCase):
    def _write_artifact(self, store: ArtifactStore, signature: str, stems: list[str], rate: float) -> None:
        artifact_dir = store.artifact_dir(signature)
        stems_dir = artifact_dir / "stems"
        stems_dir.mkdir(parents=True, exist_ok=True)
        for stem in stems:
            (stems_dir / stem).write_bytes(b"wav")
        store.write_meta(
            artifact_dir,
            {
                "signature": signature,
                "stems": stems,
                "rate_seconds_per_second": rate,
            },
        )

    def _job(self, store: JobStore, mode: str) -> dict:
        return store.create_job(
            input_payload={"mode": mode, "model": "htdemucs", "file": {}},
            job_label=None,
        )

    def test_single_file_zip_mode_4_contains_all_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            job_store = JobStore(storage_root)
            artifact_store = ArtifactStore(storage_root, output_format_version="v1")
            worker = WorkerManager(
                job_store=job_store,
                artifact_store=artifact_store,
                demucs_bin="demucs",
                demucs_device="cuda",
                max_concurrent_jobs=1,
                run_loop_enabled=False,
            )
            job = self._job(job_store, "4")
            self._write_artifact(
                artifact_store,
                "sig4",
                ["vocals.wav", "drums.wav", "bass.wav", "other.wav"],
                47.53,
            )

            zip_path = worker._build_output_zip(
                job["id"],
                [{"mode": "4", "signature": "sig4", "cache_hit": True}],
            )

            with zipfile.ZipFile(zip_path, "r") as zip_handle:
                names = set(zip_handle.namelist())
                self.assertIn("all/vocals.wav", names)
                self.assertIn("all/drums.wav", names)
                self.assertNotIn("vocals/vocals.wav", names)
                self.assertNotIn("manifest.json", names)

    def test_single_file_zip_mode_2_contains_vocals_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            job_store = JobStore(storage_root)
            artifact_store = ArtifactStore(storage_root, output_format_version="v1")
            worker = WorkerManager(
                job_store=job_store,
                artifact_store=artifact_store,
                demucs_bin="demucs",
                demucs_device="cuda",
                max_concurrent_jobs=1,
                run_loop_enabled=False,
            )
            job = self._job(job_store, "2")
            self._write_artifact(artifact_store, "sig2", ["vocals.wav", "no_vocals.wav"], 51.11)

            zip_path = worker._build_output_zip(
                job["id"],
                [{"mode": "2", "signature": "sig2", "cache_hit": True}],
            )

            with zipfile.ZipFile(zip_path, "r") as zip_handle:
                names = set(zip_handle.namelist())
                self.assertIn("vocals/vocals.wav", names)
                self.assertIn("vocals/no_vocals.wav", names)
                self.assertNotIn("all/vocals.wav", names)

    def test_single_file_zip_mode_both_contains_both_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            job_store = JobStore(storage_root)
            artifact_store = ArtifactStore(storage_root, output_format_version="v1")
            worker = WorkerManager(
                job_store=job_store,
                artifact_store=artifact_store,
                demucs_bin="demucs",
                demucs_device="cuda",
                max_concurrent_jobs=1,
                run_loop_enabled=False,
            )
            job = self._job(job_store, "both")
            self._write_artifact(
                artifact_store,
                "sig4",
                ["vocals.wav", "drums.wav", "bass.wav", "other.wav"],
                47.53,
            )
            self._write_artifact(artifact_store, "sig2", ["vocals.wav", "no_vocals.wav"], 51.11)

            zip_path = worker._build_output_zip(
                job["id"],
                [
                    {"mode": "4", "signature": "sig4", "cache_hit": True},
                    {"mode": "2", "signature": "sig2", "cache_hit": True},
                ],
            )

            with zipfile.ZipFile(zip_path, "r") as zip_handle:
                names = set(zip_handle.namelist())
                self.assertIn("all/vocals.wav", names)
                self.assertIn("vocals/vocals.wav", names)
                self.assertIn("vocals/no_vocals.wav", names)
                self.assertNotIn("manifest.json", names)


if __name__ == "__main__":
    unittest.main()
