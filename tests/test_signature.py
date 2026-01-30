import tempfile
import unittest
from pathlib import Path

from demucs_service.storage import ArtifactStore


class SignatureTests(unittest.TestCase):
    def test_signature_stability(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            store = ArtifactStore(storage_root, output_format_version="v1")
            file_path = storage_root / "sample.mp3"
            file_path.write_bytes(b"demo-data")
            file_hash = store.compute_file_hash(file_path)
            sig_a = store.compute_signature(file_hash=file_hash, mode="4", model="htdemucs")
            sig_b = store.compute_signature(file_hash=file_hash, mode="4", model="htdemucs")
            self.assertEqual(sig_a, sig_b)

    def test_signature_variation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir)
            store = ArtifactStore(storage_root, output_format_version="v1")
            file_path = storage_root / "sample.mp3"
            file_path.write_bytes(b"demo-data")
            file_hash = store.compute_file_hash(file_path)
            sig_a = store.compute_signature(file_hash=file_hash, mode="4", model="htdemucs")
            sig_b = store.compute_signature(file_hash=file_hash, mode="2", model="htdemucs")
            sig_c = store.compute_signature(file_hash=file_hash, mode="4", model="mdx")
            self.assertNotEqual(sig_a, sig_b)
            self.assertNotEqual(sig_a, sig_c)


if __name__ == "__main__":
    unittest.main()
