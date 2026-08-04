#!/usr/bin/env python3

"""在技能 venv 内运行：用 sherpa-onnx 和 SenseVoice 识别一段 16 kHz 单声道 WAV。

由 transcribe.py 以 venv 的 python 调用，用法：
  _sherpa_decode.py <16kHz 单声道 wav> <模型目录>
stdout 输出 JSON：{"text", "lang", "emotion", "event"}。
"""

import json
import sys
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx


def read_wave(path: Path):
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())
    if width == 2:
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        samples = np.frombuffer(frames, dtype=np.float32)
    else:
        raise SystemExit(f"不支持的 WAV 位深：{width * 8} 位")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def main() -> None:
    wav_path, model_dir = Path(sys.argv[1]), Path(sys.argv[2])
    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model_dir / "model.int8.onnx"),
        tokens=str(model_dir / "tokens.txt"),
        use_itn=True,
        debug=False,
        num_threads=2,
    )
    samples, rate = read_wave(wav_path)
    if rate != 16000:
        raise SystemExit(f"采样率必须为 16000 Hz，当前 {rate} Hz")
    stream = recognizer.create_stream()
    stream.accept_waveform(rate, samples)
    recognizer.decode_stream(stream)
    result = stream.result
    print(
        json.dumps(
            {
                "text": result.text,
                "lang": result.lang,
                "emotion": result.emotion,
                "event": result.event,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
