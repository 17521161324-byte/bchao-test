"""ASR 音频输入策略。

支持按模型配置选择:
- segments: 使用原始 25 秒分段
- grouped: 使用连续分组合并音频
- merged: 优先使用预生成的整段合并音频，找不到时回退分段
"""
from __future__ import annotations

import os
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
