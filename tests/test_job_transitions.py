import unittest

from demucs_service.job_store import validate_transition


class TransitionTests(unittest.TestCase):
    def test_valid_transitions(self) -> None:
        self.assertTrue(validate_transition("queued", "queued"))
        self.assertTrue(validate_transition("queued", "running"))
        self.assertTrue(validate_transition("queued", "failed"))
        self.assertTrue(validate_transition("running", "succeeded"))
        self.assertTrue(validate_transition("running", "failed"))

    def test_invalid_transitions(self) -> None:
        self.assertFalse(validate_transition("succeeded", "running"))
        self.assertFalse(validate_transition("failed", "running"))
        self.assertFalse(validate_transition("succeeded", "failed"))


if __name__ == "__main__":
    unittest.main()
