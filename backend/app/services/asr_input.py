"""ASR 音频输入策略。

支持按模型配置选择:
- segments: 使用原始 25 秒分段
- grouped: 使用连续分组合并音频
- merged: 优先使用预生成的整段合并音频，找不到时回退分段
"""
from __future__ import annotations

import hashlib
import os
import wave
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import settings


def audio_input_mode(params: dict | None) -> str:
    """读取模型配置中的音频输入模式。"""
    mode = (params or {}).get("audio_input_mode") or (params or {}).get("recognition_mode")
    if str(mode).lower() in {"grouped", "merged_group", "chunked", "chunked_merged"}:
        return "grouped"
    if str(mode).lower() in {"merged", "full", "whole"}:
        return "merged"
    return "segments"


def build_asr_audio_inputs(segs: list[dict[str, Any]], params: dict | None = None) -> list[dict[str, Any]]:
    """根据模型参数构建实际送入 ASR 的音频列表。"""
    if not segs:
        return []

    ordered = sorted(segs, key=lambda item: item.get("seg_index") or 0)
    mode = audio_input_mode(params)
    if mode == "segments":
        return ordered

    record_level = build_record_level_merged_audio(ordered, params)
    if record_level:
        grouped = record_level["group_paths"]
        if mode == "grouped":
            if grouped:
                return [
                    {
                        "seg_index": index + 1,
                        "file_path": path,
                        "duration": _wav_duration_seconds(path),
                        "source_seg_count": None,
                        "input_mode": "grouped",
                    }
                    for index, path in enumerate(grouped)
                ]
            return [{
                "seg_index": 1,
                "file_path": record_level["full_path"],
                "duration": record_level["duration"],
                "source_seg_count": len(ordered),
                "input_mode": "grouped",
            }]

        if record_level["estimated_base64_mb"] <= record_level["max_base64_mb"]:
            return [{
                "seg_index": 0,
                "file_path": record_level["full_path"],
                "duration": record_level["duration"],
                "source_seg_count": len(ordered),
                "input_mode": "merged",
            }]
        if grouped:
            return [
                {
                    "seg_index": index + 1,
                    "file_path": path,
                    "duration": _wav_duration_seconds(path),
                    "source_seg_count": None,
                    "input_mode": "grouped",
                }
                for index, path in enumerate(grouped)
            ]
        logger.warning(
            f"检查记录级合并音频预计 base64 {record_level['estimated_base64_mb']:.2f}MB 超过限制 "
            f"{record_level['max_base64_mb']}MB，且未能生成分组合并文件，回退原始分段: {record_level['full_path']}"
        )
        return ordered

    merged_path = resolve_merged_audio_path(ordered[0].get("file_path") or "")
    if not merged_path:
        logger.warning("未能解析合并音频路径，回退原始分段")
        return ordered

    grouped = resolve_grouped_audio_paths(merged_path)
    if mode == "grouped":
        if grouped:
            return [
                {
                    "seg_index": index + 1,
                    "file_path": path,
                    "duration": 0,
                    "source_seg_count": None,
                    "input_mode": "grouped",
                }
                for index, path in enumerate(grouped)
            ]
        logger.warning(f"连续分组合并音频不存在，回退原始分段: {Path(merged_path).parent}")
        return ordered

    if not os.path.isfile(merged_path):
        logger.warning(f"合并音频不存在，回退原始分段: {merged_path}")
        return ordered

    max_base64_mb = float((params or {}).get("max_base64_mb") or 9.8)
    estimated_base64_mb = os.path.getsize(merged_path) * 4 / 3 / 1024 / 1024
    if estimated_base64_mb > max_base64_mb:
        if grouped:
            return [
                {
                    "seg_index": index + 1,
                    "file_path": path,
                    "duration": 0,
                    "source_seg_count": None,
                    "input_mode": "grouped",
                }
                for index, path in enumerate(grouped)
            ]
        logger.warning(
            f"合并音频预计 base64 {estimated_base64_mb:.2f}MB 超过限制 {max_base64_mb}MB，未找到分组合并文件，回退原始分段: {merged_path}"
        )
        return ordered

    return [{
        "seg_index": 0,
        "file_path": merged_path,
        "duration": round(sum(float(item.get("duration") or 0) for item in ordered), 2),
        "source_seg_count": len(ordered),
        "input_mode": "merged",
    }]


def resolve_merged_audio_path(first_seg_path: str) -> str | None:
    """根据任一原始分段路径推导对应合并文件路径。"""
    if not first_seg_path:
        return None

    raw = Path(first_seg_path)
    recordings_root = Path(settings.RECORDINGS_DIR)
    merged_root = recordings_root.parent / "recordings_merged"

    try:
        relative = raw.resolve().relative_to(recordings_root.resolve())
    except Exception:
        normalized = str(raw).replace("\\", "/")
        marker = "/recordings/"
        if marker not in normalized:
            return None
        relative = Path(normalized.split(marker, 1)[1])

    audio_dir = relative.parent
    return str((merged_root / audio_dir / "full.wav").resolve())


def resolve_grouped_audio_paths(merged_full_path: str) -> list[str]:
    audio_dir = Path(merged_full_path).parent
    paths = sorted(str(path.resolve()) for path in audio_dir.glob("group-*.wav") if path.is_file())
    return paths


def build_record_level_merged_audio(segs: list[dict[str, Any]], params: dict | None = None) -> dict[str, Any] | None:
    """按检查记录实际关联分段生成完整合并音频。

    旧逻辑基于第一段所在时间戳目录查找 recordings_merged/<date>/<record>/<timestamp>/audio/full.wav。
    当同一检查记录的分段跨多个 timestamp 目录时，会只送入第一部分音频。

    本函数改为按 DB 传入的全部 segs 顺序合并，输出到 recordings_merged_by_record。
    """
    source_paths = [Path(str(item.get("file_path") or "")) for item in segs]
    source_paths = [path for path in source_paths if path.is_file()]
    if not source_paths or len(source_paths) != len(segs):
        return None

    recordings_root = Path(settings.RECORDINGS_DIR).resolve()
    parsed: list[tuple[Path, Path]] = []
    for path in source_paths:
        try:
            relative = path.resolve().relative_to(recordings_root)
        except Exception:
            return None
        # <date>/<record_id>/<timestamp>/audio/seg-xxxx.wav
        if len(relative.parts) < 5 or relative.parts[-2] != "audio":
            return None
        parsed.append((path, relative))

    date = parsed[0][1].parts[0]
    record_id = parsed[0][1].parts[1]
    if any(relative.parts[0] != date or relative.parts[1] != record_id for _, relative in parsed):
        return None

    signature = hashlib.sha1()
    for path in source_paths:
        stat = path.stat()
        signature.update(str(path.resolve()).encode("utf-8"))
        signature.update(str(stat.st_size).encode("ascii"))
        signature.update(str(int(stat.st_mtime)).encode("ascii"))
    digest = signature.hexdigest()[:16]

    merged_root = recordings_root.parent / "recordings_merged_by_record"
    out_dir = merged_root / date / record_id / digest / "audio"
    full_path = out_dir / "full.wav"

    max_base64_mb = float((params or {}).get("max_base64_mb") or 9.8)
    group_size = int((params or {}).get("merge_group_size") or 0)

    if not full_path.is_file():
        try:
            _merge_wav_files(source_paths, full_path)
        except Exception as exc:
            logger.warning(f"检查记录级合并音频生成失败，回退旧合并逻辑: {exc}")
            return None

    # 每次按当前参数重建 group，避免 group_size 改变但旧文件残留。
    for old_group in out_dir.glob("group-*.wav"):
        old_group.unlink()

    group_paths = _build_group_wavs(source_paths, out_dir, max_base64_mb, group_size)
    estimated_base64_mb = full_path.stat().st_size * 4 / 3 / 1024 / 1024
    return {
        "full_path": str(full_path.resolve()),
        "group_paths": [str(path.resolve()) for path in group_paths],
        "duration": _wav_duration_seconds(full_path),
        "estimated_base64_mb": estimated_base64_mb,
        "max_base64_mb": max_base64_mb,
    }


def _merge_wav_files(source_paths: list[Path], out_path: Path) -> None:
    params = None
    comparable_params = None
    chunks: list[bytes] = []
    for path in source_paths:
        with wave.open(str(path), "rb") as wav:
            current_params = wav.getparams()
            current_comparable = current_params[:3] + current_params[4:]
            if params is None:
                params = current_params
                comparable_params = current_comparable
            elif current_comparable != comparable_params:
                raise ValueError(f"音频参数不一致: {path}")
            chunks.append(wav.readframes(wav.getnframes()))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        for chunk in chunks:
            out.writeframes(chunk)


def _build_group_wavs(source_paths: list[Path], out_dir: Path, max_base64_mb: float, group_size: int) -> list[Path]:
    raw_limit = int(max_base64_mb * 1024 * 1024 * 3 / 4)
    if group_size > 0:
        groups = [source_paths[offset:offset + group_size] for offset in range(0, len(source_paths), group_size)]
    else:
        total_size = sum(path.stat().st_size for path in source_paths)
        if total_size <= raw_limit:
            return []
        groups: list[list[Path]] = []
        current: list[Path] = []
        current_size = 44
        for path in source_paths:
            size = path.stat().st_size
            if current and current_size + size > raw_limit:
                groups.append(current)
                current = []
                current_size = 44
            current.append(path)
            current_size += size
        if current:
            groups.append(current)

    group_paths: list[Path] = []
    for index, group in enumerate(groups, start=1):
        group_path = out_dir / f"group-{index:04d}.wav"
        _merge_wav_files(group, group_path)
        group_paths.append(group_path)
    return group_paths


def _wav_duration_seconds(path: str | Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            return round(wav.getnframes() / float(wav.getframerate()), 2)
    except Exception:
        return 0.0
