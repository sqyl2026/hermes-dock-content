import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPOSITORY_ROOT / "skills" / "speech-to-text" / "scripts" / "transcribe.py"
SPEC = importlib.util.spec_from_file_location("speech_to_text", WRAPPER_PATH)
STT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STT)


def write_model(model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.int8.onnx").write_bytes(b"\x00" * 16)
    (model_dir / "tokens.txt").write_text("<blk>\n中\n", encoding="utf-8")
    STT.write_model_hashes(model_dir)


class SpeechToTextTests(unittest.TestCase):
    def test_validate_audio_enforces_root_type_and_size(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            valid = root / "valid.wav"
            valid.write_bytes(b"RIFF")
            self.assertEqual(STT.validate_audio(str(valid), root), valid)

            maximum = root / "maximum.mp3"
            with maximum.open("wb") as audio_file:
                audio_file.truncate(STT.MAX_FILE_SIZE)
            self.assertEqual(STT.validate_audio(str(maximum), root), maximum)

            too_large = root / "too-large.ogg"
            with too_large.open("wb") as audio_file:
                audio_file.truncate(STT.MAX_FILE_SIZE + 1)
            with self.assertRaisesRegex(STT.InputError, "25 MiB"):
                STT.validate_audio(str(too_large), root)

            unsupported = root / "document.pdf"
            unsupported.write_bytes(b"pdf")
            with self.assertRaisesRegex(STT.InputError, "不支持的音频格式"):
                STT.validate_audio(str(unsupported), root)

            with self.assertRaisesRegex(STT.InputError, "只支持本地音频路径"):
                STT.validate_audio("https://example.com/a.wav", root)

            with tempfile.TemporaryDirectory() as outside_directory:
                outside = Path(outside_directory) / "outside.amr"
                outside.write_bytes(b"amr")
                with self.assertRaisesRegex(STT.InputError, "必须位于"):
                    STT.validate_audio(str(outside), root)

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
                    runtime_parent = dock / STT.RUNTIME_NAME
                    if case == "runtime-parent":
                        runtime_parent.symlink_to(outside, target_is_directory=True)
                    else:
                        runtime_parent.mkdir()
                        (runtime_parent / STT.RUNTIME_VERSION).symlink_to(outside, target_is_directory=True)

                with self.assertRaisesRegex(RuntimeError, "符号链接"):
                    STT.install_runtime(root, "/usr/bin/python3")
                self.assertEqual(list(outside.iterdir()), [])

    def test_model_files_match_detects_corruption(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_dir = Path(temporary_directory)
            write_model(model_dir)
            self.assertTrue(STT.model_files_match(model_dir))

            (model_dir / "model.int8.onnx").write_bytes(b"\xff" * 16)
            self.assertFalse(STT.model_files_match(model_dir))

    def test_runtime_ready_requires_marker_and_installed_dist(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            runtime = root / STT.RUNTIME_VERSION
            write_model(runtime / "model")

            self.assertFalse(STT.runtime_ready(runtime, root))

            (runtime / ".installed").write_text(STT.RUNTIME_VERSION + "\n", encoding="utf-8")
            with mock.patch.object(STT, "sherpa_onnx_dist_installed", return_value=False):
                self.assertFalse(STT.runtime_ready(runtime, root))
            with mock.patch.object(STT, "sherpa_onnx_dist_installed", return_value=True):
                self.assertTrue(STT.runtime_ready(runtime, root))

            (runtime / ".installed").write_text("0.0.0-1970-01-01\n", encoding="utf-8")
            with mock.patch.object(STT, "sherpa_onnx_dist_installed", return_value=True):
                self.assertFalse(STT.runtime_ready(runtime, root))

    def test_model_sources_respects_env_overrides(self):
        with mock.patch.dict(
            os.environ,
            {
                "HERMES_ASR_MODEL_URL": "https://example.com/model.tar.bz2",
                "HERMES_ASR_MODEL_MIRROR": "https://mirror.example.com/models",
            },
        ):
            sources = STT.model_sources()
        self.assertEqual(
            sources,
            [
                ("tarball", "https://example.com/model.tar.bz2"),
                ("files", "https://mirror.example.com/models"),
                ("tarball", STT.GITHUB_TARBALL_URL),
                ("files", STT.HF_MIRROR_BASE),
                ("files", STT.MODELSCOPE_BASE),
            ],
        )

    def test_download_model_falls_back_to_next_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_dir = Path(temporary_directory)
            calls = []

            def fail_tarball(model_dir, url):
                calls.append(("tarball", url))
                raise RuntimeError("connection failed")

            def succeed_files(model_dir, base):
                calls.append(("files", base))
                (model_dir / "model.int8.onnx").write_bytes(b"\x00" * 16)
                (model_dir / "tokens.txt").write_text("<blk>\n", encoding="utf-8")

            with (
                mock.patch.object(STT, "download_tarball", side_effect=fail_tarball),
                mock.patch.object(STT, "download_files", side_effect=succeed_files),
                mock.patch.object(
                    STT,
                    "model_sources",
                    return_value=[
                        ("tarball", "https://github.example"),
                        ("files", "https://mirror.example"),
                    ],
                ),
            ):
                STT.download_model(model_dir)

            self.assertEqual(
                calls,
                [("tarball", "https://github.example"), ("files", "https://mirror.example")],
            )
            self.assertTrue((model_dir / "model.int8.onnx").is_file())
            self.assertTrue((model_dir / "tokens.txt").is_file())

    def test_download_model_raises_when_all_sources_fail(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_dir = Path(temporary_directory)
            with (
                mock.patch.object(STT, "model_sources", return_value=[("tarball", "https://a"), ("files", "https://b")]),
                mock.patch.object(STT, "download_tarball", side_effect=RuntimeError("down")),
                mock.patch.object(STT, "download_files", side_effect=RuntimeError("down")),
            ):
                with self.assertRaisesRegex(RuntimeError, "所有模型下载源均失败"):
                    STT.download_model(model_dir)

    def test_main_uses_venv_decode_contract(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            audio = root / "voice.wav"
            audio.write_bytes(b"RIFF")
            wav_path = root / "tmp" / "out.wav"
            runtime = root / "runtime"
            runtime.mkdir()
            argv = ["transcribe.py", str(audio)]

            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.dict(os.environ, {"HERMES_WRITE_SAFE_ROOT": str(root)}),
                mock.patch.object(STT, "require_command", return_value="/usr/bin/ffmpeg"),
                mock.patch.object(STT, "install_runtime", return_value=runtime),
                mock.patch.object(STT, "convert_to_wav", return_value=wav_path),
                mock.patch.object(
                    STT,
                    "run_decode",
                    return_value={"text": "你好", "lang": "zh", "emotion": "neutral", "event": "Speech"},
                ) as decode,
            ):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(STT.main(), 0)

            decode.assert_called_once_with(runtime, wav_path)

    def test_main_plain_prints_text_only(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            audio = root / "voice.wav"
            audio.write_bytes(b"RIFF")
            wav_path = root / "tmp" / "out.wav"
            runtime = root / "runtime"
            runtime.mkdir()
            argv = ["transcribe.py", str(audio), "--plain"]

            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.dict(os.environ, {"HERMES_WRITE_SAFE_ROOT": str(root)}),
                mock.patch.object(STT, "require_command", return_value="/usr/bin/ffmpeg"),
                mock.patch.object(STT, "install_runtime", return_value=runtime),
                mock.patch.object(STT, "convert_to_wav", return_value=wav_path),
                mock.patch.object(
                    STT,
                    "run_decode",
                    return_value={"text": "你好", "lang": "zh", "emotion": "neutral", "event": "Speech"},
                ),
            ):
                captured = io.StringIO()
                with redirect_stdout(captured):
                    self.assertEqual(STT.main(), 0)

            self.assertEqual(captured.getvalue().strip(), "你好")


if __name__ == "__main__":
    unittest.main()
