---
name: speech-to-text
description: Transcribe local audio files (voice messages, recordings, and shared audio) into text entirely offline with an on-demand local SenseVoice runtime. Use when a messaging channel delivers a voice or audio file that cannot be read as text, when the user asks to transcribe an audio file, or when the audio's content is needed to reply. The transcript supports claims about recognized speech only, not speaker identity, tone, background sound, or other audio meaning.
---

# Speech to Text

Transcribe audio locally with sherpa-onnx and SenseVoice-Small, without sending the audio to an external service. The first run installs the version-locked Python runtime and model under `/opt/data/.dock/speech-to-text-runtime/<version>`; later runs work offline with the persistent local installation.

## Transcribe Audio

Pass one local audio file under the current profile directory:

```bash
/opt/hermes/.venv/bin/python \
  skills/speech-to-text/scripts/transcribe.py \
  /opt/data/path/to/audio.wav
```

For a non-default profile, run the same relative `skills/...` script from that profile's working directory and pass an audio path inside that profile directory.

Always use `transcribe.py`; do not invoke `sherpa-onnx` or install packages with an ad hoc command. If the managed runtime is missing or invalid, the wrapper installs the locked `sherpa-onnx` runtime and downloads the SenseVoice model, verifies them, and then transcribes. Preserve stderr so installation and transcription failures remain visible. Conversion requires `ffmpeg`; if it is missing, return the real error instead of guessing.

The model download tries sources in order and falls back automatically: GitHub Releases (official), then the HuggingFace China mirror `hf-mirror.com`, then a ModelScope community mirror. All sources provide the same `model.int8.onnx` and `tokens.txt` for the locked `2024-07-17` model. If all sources fail, set `HERMES_ASR_MODEL_URL` to a single tar.bz2 URL or `HERMES_ASR_MODEL_MIRROR` to a directory serving `model.int8.onnx` and `tokens.txt`, then retry. The pip install of `sherpa-onnx` follows the container's `PIP_INDEX_URL`; the Hermes Dock compose already points it at a mainland PyPI mirror (Tencent Cloud), so no extra pip configuration is needed.

## Output

Check the exit code before parsing stdout. Exit code `0` prints one JSON object:

```json
{"text": "开放时间早上9点至下午5点。", "lang": "zh", "emotion": "neutral", "event": "Speech"}
```

- `text` is the recognized transcript. An empty `text` is a valid audio with no recognized speech.
- `lang`, `emotion`, and `event` are model outputs; use `text` for claims and do not over-interpret the others.
- Use `--plain` (e.g. `transcribe.py /path/to/audio.wav --plain`) to print only the transcript text. This form is suitable for wiring the script into a command-style STT provider such as `HERMES_LOCAL_STT_COMMAND`.

On a non-zero exit, read stderr and do not invent results. Transcription supports claims about recognized speech only. Do not infer who is speaking, tone, background sound, musical content, or other audio meaning from the transcript; if the request still needs that information, return the transcript if useful and explain which parts remain unavailable.

## Voice Message Handling

When a messaging channel (WeChat, WeCom, Feishu, DingTalk, or another channel) delivers a voice or audio file, do not refuse it. Transcribe the local audio path with this skill, then answer from the transcript. If the file cannot be decoded (for example some raw SILK recordings that `ffmpeg` cannot read), return the real error and state that the audio could not be transcribed, instead of fabricating content.

## Input Limits

- Accept one local audio file: WAV, MP3, OGG, OPUS, M4A, AAC, FLAC, AMR, SILK, WMA, or WebM.
- Reject URLs, directories, files outside `HERMES_WRITE_SAFE_ROOT`, and files larger than 25 MiB.
- Require `ffmpeg` for decoding and resampling to 16 kHz mono; do not silently skip conversion.
- Allow network access only when `transcribe.py` needs to install or repair its managed runtime or download the model. Recognition itself must remain offline.

The managed runtime uses `sherpa-onnx` 1.13.4 (Apache License 2.0) and the SenseVoice-Small `2024-07-17` int8 model (~230 MiB, redistributed under the license in its release archive). Do not add model files or virtual environments to this skill.
