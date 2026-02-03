import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.datastructures import MultiDict

from demucs_service.app import create_app
from demucs_service.config import Settings


def _settings(storage_root: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=20033,
        storage_root=storage_root,
        max_concurrent_jobs=1,
        demucs_default_model="htdemucs",
        demucs_models=["htdemucs", "mdx"],
        demucs_bin="demucs",
        demucs_device="cuda",
        output_format_version="v1",
    )


class ApiSingleFileTests(unittest.TestCase):
    @patch("demucs_service.app._resolve_demucs_bin", return_value="demucs")
    @patch(
        "demucs_service.app.check_cuda_or_raise",
        return_value={
            "cuda_available": True,
            "cuda_device_count": 1,
            "cuda_device_name": "Fake CUDA",
            "torch_cuda_version": "12.1",
        },
    )
    def test_rejects_multi_file_payload_with_explicit_error(self, *_mocks) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(_settings(Path(temp_dir)))
            app.testing = True
            client = app.test_client()
            payload = MultiDict(
                [
                    ("mode", "4"),
                    ("model", "htdemucs"),
                    ("file", (io.BytesIO(b"ID3a"), "a.mp3")),
                    ("file", (io.BytesIO(b"ID3b"), "b.mp3")),
                ]
            )
            response = client.post("/api/jobs", data=payload, content_type="multipart/form-data")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.get_json(),
                {
                    "error": "invalid_request",
                    "message": "Exactly one file is supported per job; multi-file uploads are not supported.",
                },
            )

    @patch("demucs_service.app._resolve_demucs_bin", return_value="demucs")
    @patch(
        "demucs_service.app.check_cuda_or_raise",
        return_value={
            "cuda_available": True,
            "cuda_device_count": 1,
            "cuda_device_name": "Fake CUDA",
            "torch_cuda_version": "12.1",
        },
    )
    def test_creates_single_file_job_with_label_and_metadata(self, *_mocks) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(_settings(Path(temp_dir)))
            app.testing = True
            client = app.test_client()
            response = client.post(
                "/api/jobs",
                data={
                    "mode": "both",
                    "model": "htdemucs",
                    "job_label": "display-only-label",
                    "file": (io.BytesIO(b"ID3demo"), "track.mp3"),
                },
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 202)
            body = response.get_json()
            self.assertIn("id", body)

            detail = client.get(f"/api/jobs/{body['id']}")
            self.assertEqual(detail.status_code, 200)
            job = detail.get_json()
            self.assertEqual(job["input"]["job_label"], "display-only-label")
            self.assertEqual(job["input"]["file"]["original_filename"], "track.mp3")
            self.assertEqual(job["input"]["file"]["stored_name"], "input.mp3")
            self.assertIsInstance(job["input"]["file"]["size_bytes"], int)
            self.assertIsInstance(job["input"]["file"]["sha256"], str)

    @patch("demucs_service.app._resolve_demucs_bin", return_value="demucs")
    @patch(
        "demucs_service.app.check_cuda_or_raise",
        return_value={
            "cuda_available": True,
            "cuda_device_count": 1,
            "cuda_device_name": "Fake CUDA",
            "torch_cuda_version": "12.1",
        },
    )
    def test_openapi_and_docs_endpoints(self, *_mocks) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(_settings(Path(temp_dir)))
            app.testing = True
            client = app.test_client()

            openapi_json = client.get("/openapi.json")
            self.assertEqual(openapi_json.status_code, 200)
            self.assertIn("application/json", openapi_json.content_type)
            self.assertIn("\"openapi\": \"3.0.3\"", openapi_json.get_data(as_text=True))

            docs = client.get("/docs")
            self.assertEqual(docs.status_code, 200)
            self.assertIn("swagger-ui", docs.get_data(as_text=True).lower())

            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.get_json(), {"ok": True})

    @patch("demucs_service.app._resolve_demucs_bin", return_value="demucs")
    @patch(
        "demucs_service.app.check_cuda_or_raise",
        return_value={
            "cuda_available": True,
            "cuda_device_count": 1,
            "cuda_device_name": "Fake CUDA",
            "torch_cuda_version": "12.1",
        },
    )
    def test_output_not_ready_is_conflict(self, *_mocks) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(_settings(Path(temp_dir)))
            app.testing = True
            client = app.test_client()
            created = client.post(
                "/api/jobs",
                data={
                    "mode": "4",
                    "model": "htdemucs",
                    "file": (io.BytesIO(b"ID3demo"), "track.mp3"),
                },
                content_type="multipart/form-data",
            )
            job_id = created.get_json()["id"]
            output = client.get(f"/api/jobs/{job_id}/result")
            self.assertEqual(output.status_code, 409)
            self.assertEqual(
                output.get_json(),
                {
                    "error": "job_not_succeeded",
                    "message": "Output not ready",
                },
            )


if __name__ == "__main__":
    unittest.main()
