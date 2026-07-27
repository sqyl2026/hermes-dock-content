import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = (
    REPOSITORY_ROOT
    / "skills"
    / "productivity"
    / "image-text-ocr"
    / "scripts"
    / "run_ocr.py"
)
SPEC = importlib.util.spec_from_file_location("image_text_ocr", WRAPPER_PATH)
OCR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OCR)


class ImageTextOCRTests(unittest.TestCase):
    def test_validate_image_enforces_root_type_and_size(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            valid = root / "valid.png"
            valid.write_bytes(b"\x89PNG")
            self.assertEqual(OCR.validate_image(str(valid), root), valid)

            maximum = root / "maximum.jpg"
            with maximum.open("wb") as image_file:
                image_file.truncate(OCR.MAX_FILE_SIZE)
            self.assertEqual(OCR.validate_image(str(maximum), root), maximum)

            too_large = root / "too-large.jpeg"
            with too_large.open("wb") as image_file:
                image_file.truncate(OCR.MAX_FILE_SIZE + 1)
            with self.assertRaisesRegex(OCR.InputError, "25 MiB"):
                OCR.validate_image(str(too_large), root)

            unsupported = root / "document.pdf"
            unsupported.write_bytes(b"pdf")
            with self.assertRaisesRegex(OCR.InputError, "PNG"):
                OCR.validate_image(str(unsupported), root)

            with tempfile.TemporaryDirectory() as outside_directory:
                outside = Path(outside_directory) / "outside.png"
                outside.write_bytes(b"\x89PNG")
                with self.assertRaisesRegex(OCR.InputError, "必须位于"):
                    OCR.validate_image(str(outside), root)

    def test_install_rejects_symlinked_managed_directories(self):
        cases = ("dock", "runtime-parent", "version")
        for case in cases:
            with (
                self.subTest(case=case),
                tempfile.TemporaryDirectory() as temporary_directory,
                tempfile.TemporaryDirectory() as outside_directory,
            ):
                root = Path(temporary_directory).resolve()
                outside = Path(outside_directory).resolve()
                if case == "dock":
                    (root / ".dock").symlink_to(outside, target_is_directory=True)
                else:
                    dock = root / ".dock"
                    dock.mkdir()
                    runtime_parent = dock / "image-text-ocr-runtime"
                    if case == "runtime-parent":
                        runtime_parent.symlink_to(outside, target_is_directory=True)
                    else:
                        runtime_parent.mkdir()
                        (runtime_parent / "0.5.5").symlink_to(outside, target_is_directory=True)

                with self.assertRaisesRegex(RuntimeError, "符号链接"):
                    OCR.install_runtime(root, "node", "npm", "0.5.5")
                self.assertEqual(list(outside.iterdir()), [])

    def test_runtime_ready_loads_model_and_native_runtime(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime = Path(temporary_directory)
            package_path = runtime / "node_modules" / "@arcships" / "light-ocr" / "package.json"
            package_path.parent.mkdir(parents=True)
            package_path.write_text('{"version":"0.5.5"}', encoding="utf-8")
            cli = runtime / "node_modules" / ".bin" / "light-ocr"
            cli.parent.mkdir(parents=True)
            cli.touch()

            with mock.patch.object(
                OCR.subprocess,
                "run",
                side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=70)],
            ) as run:
                self.assertFalse(OCR.runtime_ready(runtime, "node", "0.5.5"))

            self.assertEqual(run.call_args_list[1].args[0], [str(cli), "info", "--model-info"])

    def test_failed_install_removes_staging(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            failure = subprocess.CalledProcessError(1, ["npm", "ci"])
            with mock.patch.object(OCR.subprocess, "run", side_effect=failure):
                with self.assertRaises(subprocess.CalledProcessError):
                    OCR.install_runtime(root, "node", "npm", "0.5.5")

            runtime_parent = root / ".dock" / "image-text-ocr-runtime"
            self.assertEqual(list(runtime_parent.iterdir()), [])

    def test_concurrent_install_runs_npm_once_and_reuses_runtime(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            npm_calls = []
            calls_lock = threading.Lock()

            def ready(runtime, _node, _version):
                return (runtime / "ready").is_file()

            def run(command, **_kwargs):
                prefix = Path(command[command.index("--prefix") + 1])
                with calls_lock:
                    npm_calls.append(command)
                (prefix / "ready").touch()
                return SimpleNamespace(returncode=0)

            with (
                mock.patch.object(OCR, "runtime_ready", side_effect=ready),
                mock.patch.object(OCR.subprocess, "run", side_effect=run),
                ThreadPoolExecutor(max_workers=2) as executor,
            ):
                futures = [
                    executor.submit(OCR.install_runtime, root, "node", "npm", "0.5.5")
                    for _ in range(2)
                ]
                runtimes = [future.result(timeout=5) for future in futures]

            self.assertEqual(runtimes[0], runtimes[1])
            self.assertTrue((runtimes[0] / "ready").is_file())
            self.assertEqual(len(npm_calls), 1)

    def test_main_uses_locked_cli_contract(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            image = root / "image.png"
            image.write_bytes(b"\x89PNG")
            runtime = root / "runtime"
            cli = runtime / "node_modules" / ".bin" / "light-ocr"
            argv = ["run_ocr.py", str(image)]

            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.dict(os.environ, {"HERMES_WRITE_SAFE_ROOT": str(root)}),
                mock.patch.object(OCR, "require_command", side_effect=["node", "npm"]),
                mock.patch.object(OCR, "require_supported_node"),
                mock.patch.object(OCR, "install_runtime", return_value=runtime),
                mock.patch.object(OCR.subprocess, "call", return_value=0) as call,
            ):
                self.assertEqual(OCR.main(), 0)

            call.assert_called_once_with(
                [str(cli), "recognize", str(image), "--format", "json", "--schema-version", "1"]
            )


if __name__ == "__main__":
    unittest.main()
