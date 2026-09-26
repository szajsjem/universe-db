import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import normalize_commit_message as ncm


SCRIPT = Path(__file__).parents[1] / "scripts" / "normalize_commit_message.py"


class NormalizeCommitMessageTests(unittest.TestCase):
    def test_subject_cleanup_and_line_endings(self):
        self.assertEqual(ncm.normalize("  add   useful thing. \r\n"), "Add useful thing\n")

    def test_blank_lines_and_body_whitespace(self):
        message = "Add thing\nbody one  \n\n\nbody two\t\n"
        self.assertEqual(ncm.normalize(message), "Add thing\n\nbody one\n\nbody two\n")

    def test_preserves_trailer_block(self):
        message = "Add thing\n\nBody.\n\nNightshift-Task: task\n Signed-off-by: A Person\n"
        self.assertEqual(ncm.normalize(message), message)

    def test_rejects_trailer_attached_to_body(self):
        message = "Add thing\n\nBody text.\nNightshift-Task: task\n"
        self.assertEqual(ncm.normalize(message), message)
        self.assertIn(
            "trailers must be in a final paragraph separated from the body",
            ncm.check_message(message),
        )

    def test_idempotent(self):
        once = ncm.normalize(" fix   it!\nbody\n\nToken: value\n")
        self.assertEqual(ncm.normalize(once), once)

    def test_malformed_messages(self):
        self.assertIn("subject must not be empty", ncm.validation_errors(""))
        long_message = "A" * 73 + "\n"
        self.assertIn("subject must be at most 72 characters", ncm.validation_errors(long_message))

    def test_check_mode_exit_codes(self):
        good = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"], input="Add thing\n", text=True
        )
        bad = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"], input="add thing.\n", text=True
        )
        self.assertEqual(good.returncode, 0)
        self.assertEqual(bad.returncode, 1)

    def test_file_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "message"
            path.write_text("add  thing.\n")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)], text=True, capture_output=True
            )
            unchanged = path.read_text()
        self.assertEqual(result.stdout, "Add thing\n")
        self.assertEqual(unchanged, "add  thing.\n")

    def test_revision_range(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q", directory], check=True)
            common = {"cwd": directory, "check": True}
            subprocess.run(["git", "config", "user.name", "Test"], **common)
            subprocess.run(["git", "config", "user.email", "test@example.com"], **common)
            subprocess.run(["git", "commit", "--allow-empty", "-qm", "Base commit"], **common)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=directory, text=True).strip()
            subprocess.run(["git", "commit", "--allow-empty", "-qm", "good commit."], **common)
            first = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=directory, text=True).strip()
            subprocess.run(["git", "commit", "--allow-empty", "-qm", "another bad commit!"], **common)
            second = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=directory, text=True).strip()
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--check", "--rev-range", f"{base}..HEAD"],
                cwd=directory, text=True, capture_output=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn(first, result.stderr)
        self.assertIn(second, result.stderr)

    def test_revision_range_accepts_normalized_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q", directory], check=True)
            common = {"cwd": directory, "check": True}
            subprocess.run(["git", "config", "user.name", "Test"], **common)
            subprocess.run(["git", "config", "user.email", "test@example.com"], **common)
            subprocess.run(["git", "commit", "--allow-empty", "-qm", "Base commit"], **common)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=directory, text=True).strip()
            subprocess.run(["git", "commit", "--allow-empty", "-qm", "Add good commit"], **common)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--check", "--rev-range", f"{base}..HEAD"],
                cwd=directory,
            )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
