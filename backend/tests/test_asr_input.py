import wave
from pathlib import Path

from app.services import asr_input


def _write_wav(path: Path, seconds: float = 0.1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    framerate = 16000
    frames = b"\x00\x00" * int(framerate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(framerate)
        wav.writeframes(frames)


def test_merged_mode_combines_all_segments_across_timestamp_dirs(tmp_path, monkeypatch):
    recordings_root = tmp_path / "recordings"
    monkeypatch.setattr(asr_input.settings, "RECORDINGS_DIR", str(recordings_root))

    seg1 = recordings_root / "20260623" / "A018187" / "1782173185384" / "audio" / "seg-0001.wav"
    seg2 = recordings_root / "20260623" / "A018187" / "1782173185384" / "audio" / "seg-0002.wav"
    seg3 = recordings_root / "20260623" / "A018187" / "1782173278831" / "audio" / "seg-0003.wav"
    _write_wav(seg1)
    _write_wav(seg2)
    _write_wav(seg3)

    # 模拟旧逻辑已存在的“第一个时间戳目录 full.wav”。
    # 修复后不能只取这个文件，否则会漏掉第二个时间戳目录的 seg-0003。
    legacy_full = tmp_path / "recordings_merged" / "20260623" / "A018187" / "1782173185384" / "audio" / "full.wav"
    _write_wav(legacy_full)

    inputs = asr_input.build_asr_audio_inputs(
        [
            {"seg_index": 1, "file_path": str(seg1), "duration": 0},
            {"seg_index": 2, "file_path": str(seg2), "duration": 0},
            {"seg_index": 3, "file_path": str(seg3), "duration": 0},
        ],
        {"audio_input_mode": "merged", "max_base64_mb": 9.8},
    )

    assert len(inputs) == 1
    assert inputs[0]["input_mode"] == "merged"
    assert "recordings_merged_by_record" in inputs[0]["file_path"]
    assert Path(inputs[0]["file_path"]).is_file()
    assert inputs[0]["source_seg_count"] == 3
    assert inputs[0]["duration"] == 0.3

