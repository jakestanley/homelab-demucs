import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from demucs_service.job_store import JobStore
from demucs_service.storage import ArtifactStore
from demucs_service.utils import canonical_output_dir_name
from demucs_service.worker import WorkerManager


class OutputNamingTests(unittest.TestCase):
    def test_canonical_output_dir_name(self) -> None:
        self.assertEqual(canonical_output_dir_name("Track.mp3"), "Track")
        self.assertEqual(canonical_output_dir_name("Track....mp3"), "Track")
        self.assertEqual(canonical_output_dir_name(" Track Name .mp3 "), "Track_Name")
        self.assertEqual(canonical_output_dir_name("a<b>:c|d?e*.mp3"), "a_b_c_d_e_")
        self.assertEqual(canonical_output_dir_name(" .mp3 "), "file")


class ManifestTests(unittest.TestCase):
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

    def test_manifest_and_zip_layout_for_both_modes(self) -> None:
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
            )
            worker.pause()

            job = job_store.create_job(
                input_payload={"mode": "both", "model": "htdemucs", "files": []},
                total_files=1,
                job_name=None,
            )

            self._write_artifact(
                artifact_store,
                "sig4",
                ["vocals.wav", "drums.wav", "bass.wav", "other.wav"],
                47.53,
            )
            self._write_artifact(artifact_store, "sig2", ["vocals.wav", "no_vocals.wav"], 51.11)

            entries = [
                {
                    "file": "My Track.mp3",
                    "stored_name": "001-My_Track.mp3",
                    "input_index": 1,
                    "output_dir_name": canonical_output_dir_name("My Track.mp3"),
                    "mode": "4",
                    "signature": "sig4",
                    "cache_hit": False,
                    "rate_seconds_per_second": 47.53,
                },
                {
                    "file": "My Track.mp3",
                    "stored_name": "001-My_Track.mp3",
                    "input_index": 1,
                    "output_dir_name": canonical_output_dir_name("My Track.mp3"),
                    "mode": "2",
                    "signature": "sig2",
                    "cache_hit": False,
                    "rate_seconds_per_second": 51.11,
                },
            ]

            zip_path, manifest = worker._build_output_zip(job["id"], entries)
            self.assertEqual(manifest["version"], "v1")
            self.assertEqual(manifest["files"][0]["input_original_name"], "My Track.mp3")
            self.assertEqual(manifest["files"][0]["output_dir_name"], "My_Track")
            self.assertEqual(manifest["files"][0]["output_dir_path"], f"{job['id']}/My_Track")
            self.assertEqual(
                [item["mode"] for item in manifest["files"][0]["modes"]],
                ["2", "4"],
            )

            with zipfile.ZipFile(zip_path, "r") as zip_handle:
                names = set(zip_handle.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn(f"{job['id']}/My_Track/4/vocals.wav", names)
                self.assertIn(f"{job['id']}/My_Track/2/no_vocals.wav", names)
                self.assertNotIn(f"{job['id']}/My_Track.mp3/4/vocals.wav", names)
                manifest_from_zip = json.loads(zip_handle.read("manifest.json").decode("utf-8"))
            self.assertEqual(manifest_from_zip, manifest)

    def test_manifest_deterministic_with_shuffled_entries(self) -> None:
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
            )
            worker.pause()

            job_id = "job123"
            self._write_artifact(artifact_store, "sig4", ["vocals.wav", "drums.wav"], 47.53)
            self._write_artifact(artifact_store, "sig2", ["vocals.wav", "no_vocals.wav"], 51.11)
            first = [
                {
                    "file": "Song.mp3",
                    "stored_name": "001-Song.mp3",
                    "input_index": 1,
                    "output_dir_name": "Song",
                    "mode": "4",
                    "signature": "sig4",
                    "cache_hit": False,
                },
                {
                    "file": "Song.mp3",
                    "stored_name": "001-Song.mp3",
                    "input_index": 1,
                    "output_dir_name": "Song",
                    "mode": "2",
                    "signature": "sig2",
                    "cache_hit": True,
                },
            ]
            second = list(reversed(first))
            self.assertEqual(worker._build_manifest(job_id, first), worker._build_manifest(job_id, second))


if __name__ == "__main__":
    unittest.main()
