import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.download_wikipedia_dump import fetch


class WikipediaDownloadTest(unittest.TestCase):
    def test_receive_failure_restarts_curl_from_saved_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dump.part"
            target.write_bytes(b"existing")
            observed = []

            def transfer(command, check):
                observed.append(target.stat().st_size)
                self.assertEqual(
                    ["--continue-at", "-"],
                    command[
                        command.index("--continue-at") : command.index("--continue-at")
                        + 2
                    ],
                )
                if len(observed) == 1:
                    with target.open("ab") as handle:
                        handle.write(b"partial")
                    raise subprocess.CalledProcessError(56, command)
                with target.open("ab") as handle:
                    handle.write(b"finished")

            with (
                patch(
                    "scripts.download_wikipedia_dump.subprocess.run",
                    side_effect=transfer,
                ),
                patch("scripts.download_wikipedia_dump.time.sleep"),
            ):
                fetch("https://example.test/dump", target, resume=True)
            self.assertEqual([8, 15], observed)
            self.assertEqual(b"existingpartialfinished", target.read_bytes())

    def test_http_failure_does_not_retry_missing_release(self):
        with (
            patch(
                "scripts.download_wikipedia_dump.subprocess.run",
                side_effect=subprocess.CalledProcessError(22, ["curl"]),
            ) as run,
            patch("scripts.download_wikipedia_dump.time.sleep") as sleep,
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                fetch("https://example.test/missing", Path("unused"))
            self.assertEqual(1, run.call_count)
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
