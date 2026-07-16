"""按日期生成整段合并录音。

输出目录:
  backend/data/recordings_merged/<date>/<record_id>/<timestamp>/audio/full.wav

不会修改原始 recordings，也不会写数据库。
"""
from __future__ import annotations

import argparse
import wave
from pathlib import Path


def _write_wav(out_path: Path, params, frame_chunks: list[bytes]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        for data in frame_chunks:
            out.writeframes(data)


def merge_one(
    audio_dir: Path,
    recordings_root: Path,
    merged_root: Path,
    max_base64_mb: float,
    group_size: int = 0,
) -> tuple[bool, str]:
    wavs = sorted(audio_dir.glob("seg-*.wav"))
    if not wavs:
        return False, f"无 wav: {audio_dir}"

    params = None
    frames: list[tuple[Path, bytes]] = []
    for wav_path in wavs:
        with wave.open(str(wav_path), "rb") as wav:
            current_params = wav.getparams()
            comparable = current_params[:3] + current_params[4:]
            if params is None:
                params = current_params
                base_comparable = comparable
            elif comparable != base_comparable:
                return False, f"音频参数不一致，跳过: {audio_dir}"
            frames.append((wav_path, wav.readframes(wav.getnframes())))

    rel_audio_dir = audio_dir.relative_to(recordings_root)
    out_path = merged_root / rel_audio_dir / "full.wav"
    _write_wav(out_path, params, [data for _, data in frames])

    # 按固定原始分段数量生成连续合并分组文件；适合 MiMo 这类长音频可能截断的模型。
    raw_limit = int(max_base64_mb * 1024 * 1024 * 3 / 4)
    group_paths: list[Path] = []
    if group_size > 0:
        for offset in range(0, len(frames), group_size):
            group_path = out_path.parent / f"group-{len(group_paths) + 1:04d}.wav"
            _write_wav(group_path, params, [data for _, data in frames[offset:offset + group_size]])
            group_paths.append(group_path)
    elif out_path.stat().st_size > raw_limit:
        current: list[bytes] = []
        current_size = 44
        group_index = 1
        for wav_path, data in frames:
            # 单个原始分段通常远小于限制；若加入后超限，则先落当前组。
            if current and current_size + len(data) > raw_limit:
                group_path = out_path.parent / f"group-{group_index:04d}.wav"
                _write_wav(group_path, params, current)
                group_paths.append(group_path)
                group_index += 1
                current = []
                current_size = 44
            current.append(data)
            current_size += len(data)
        if current:
            group_path = out_path.parent / f"group-{group_index:04d}.wav"
            _write_wav(group_path, params, current)
            group_paths.append(group_path)

    suffix = f" groups={len(group_paths)}" if group_paths else ""
    return True, f"{out_path}{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="日期目录，如 20260622")
    parser.add_argument("--recordings-root", default=str(Path(__file__).resolve().parents[1] / "data" / "recordings"))
    parser.add_argument("--merged-root", default=str(Path(__file__).resolve().parents[1] / "data" / "recordings_merged"))
    parser.add_argument("--max-base64-mb", type=float, default=9.8)
    parser.add_argument("--group-size", type=int, default=0, help="固定每 N 个原始分段合并成一个 group-*.wav；0 表示仅超限时分组")
    args = parser.parse_args()

    recordings_root = Path(args.recordings_root).resolve()
    merged_root = Path(args.merged_root).resolve()
    date_dir = recordings_root / args.date
    if not date_dir.is_dir():
        raise SystemExit(f"日期目录不存在: {date_dir}")

    ok = 0
    failed = 0
    for audio_dir in sorted(date_dir.glob("*/*/audio")):
        success, message = merge_one(audio_dir, recordings_root, merged_root, args.max_base64_mb, args.group_size)
        if success:
            ok += 1
            print(f"OK {message}")
        else:
            failed += 1
            print(f"SKIP {message}")

    print(f"done date={args.date} ok={ok} failed={failed} output={merged_root / args.date}")


if __name__ == "__main__":
    main()
