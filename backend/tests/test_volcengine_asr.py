# -*- coding: utf-8 -*-
"""
单元测试: 豆包 / 火山引擎 ASR WebSocket 实现

覆盖:
1. 多次 FULL_SERVER_RESPONSE 文本聚合 (不丢前段)
2. utterances 全量更新不重复
3. 收到最终响应 flags=0b0011 后立即退出
4. ERROR_RESPONSE 抛 VolcengineASRError (不返回空)
5. error response JSON 解析
6. gzip 解压 payload
7. _merge_text / _extract_text_from_result 边界
8. 帧构建
"""
import asyncio
import gzip
import json
import struct
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest

# 让 backend 目录可被 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.asr.volcengine_asr import (
    MessageType,
    VolcengineASRError,
    VolcengineBigModelASR,
)


# ------------------------------------------------------------------
# 辅助: 构造二进制帧
# ------------------------------------------------------------------

def build_header(msg_type: int, flags: int = 0, serialization: int = 1, compression: int = 0) -> bytes:
    byte0 = (0b0001 << 4) | 0b0001
    byte1 = (msg_type << 4) | flags
    byte2 = (serialization << 4) | compression
    byte3 = 0x00
    return struct.pack("BBBB", byte0, byte1, byte2, byte3)


def build_full_server_response_frame(
    text: str = "",
    utterances: list | None = None,
    flags: int = 0b0000,
    seq: int = 1,
    compression: int = 0,
) -> bytes:
    """构造一条 FULL_SERVER_RESPONSE 帧

    compression=1 时 payload 经 gzip 压缩, header byte2 对应位置 1
    seq 非 None 时自动置 flags bit0 = 1 (协议: 含 sequence 时需置位)
    """
    result = {"text": text}
    if utterances is not None:
        result["utterances"] = utterances
    payload = json.dumps({"result": result}, ensure_ascii=False).encode("utf-8")
    if compression:
        payload = gzip.compress(payload)
    if seq is not None:
        flags = flags | 0b0001
    header = build_header(MessageType.FULL_SERVER_RESPONSE, flags=flags, compression=compression)
    seq_bytes = struct.pack(">i", seq)
    size = struct.pack(">I", len(payload))
    return header + seq_bytes + size + payload


def build_error_response_frame(error_payload: dict, flags: int = 0b0000) -> bytes:
    """构造一条 ERROR_RESPONSE 帧 (payload 整体为 JSON)"""
    payload = json.dumps(error_payload, ensure_ascii=False).encode("utf-8")
    header = build_header(MessageType.ERROR_RESPONSE, flags=flags)
    size = struct.pack(">I", len(payload))
    return header + size + payload


def build_ack_frame() -> bytes:
    """构造一条服务端确认帧 (msg_type=0b1001, flags=0, payload={})"""
    payload = b"{}"
    header = build_header(MessageType.FULL_SERVER_RESPONSE, flags=0b0000)
    size = struct.pack(">I", len(payload))
    return header + size + payload


# ------------------------------------------------------------------
# 测试: _parse_server_response
# ------------------------------------------------------------------

class TestParseServerResponse:
    def test_basic_full_response(self):
        asr = VolcengineBigModelASR(api_key="test_key")
        frame = build_full_server_response_frame(text="你好世界", seq=3)
        parsed = asr._parse_server_response(frame)
        assert parsed["msg_type"] == MessageType.FULL_SERVER_RESPONSE
        assert parsed["flags"] == 0b0001  # 带 sequence
        assert parsed["sequence"] == 3
        assert parsed["payload"]["result"]["text"] == "你好世界"

    def test_negative_sequence_for_last_frame(self):
        """最后一帧 sequence 为负数"""
        asr = VolcengineBigModelASR(api_key="test_key")
        frame = build_full_server_response_frame(text="end", seq=-5, flags=0b0011)
        parsed = asr._parse_server_response(frame)
        assert parsed["sequence"] == -5
        assert parsed["flags"] == 0b0011

    def test_gzip_compressed_payload(self):
        """gzip 压缩的 payload 能正确解压"""
        asr = VolcengineBigModelASR(api_key="test_key")
        frame = build_full_server_response_frame(text="解压测试", compression=1)
        parsed = asr._parse_server_response(frame)
        assert parsed["payload"]["result"]["text"] == "解压测试"

    def test_error_response_json_parsing(self):
        """error response payload 按 JSON 解析, 不按前 4 字节解析 error_code"""
        asr = VolcengineBigModelASR(api_key="test_key")
        error_payload = {"code": 400000, "message": "invalid parameter", "request_id": "req-123"}
        frame = build_error_response_frame(error_payload)
        parsed = asr._parse_server_response(frame)
        assert parsed["msg_type"] == MessageType.ERROR_RESPONSE
        assert parsed["payload"] == error_payload
        assert parsed["payload"]["code"] == 400000
        assert parsed["payload"]["message"] == "invalid parameter"

    def test_error_response_non_json_fallback(self):
        """error response 非 JSON 时回退为字符串"""
        asr = VolcengineBigModelASR(api_key="test_key")
        raw = b"some non-json error"
        header = build_header(MessageType.ERROR_RESPONSE, flags=0)
        frame = header + struct.pack(">I", len(raw)) + raw
        parsed = asr._parse_server_response(frame)
        assert parsed["msg_type"] == MessageType.ERROR_RESPONSE
        assert "some non-json error" in parsed["payload"]["error"]

    def test_too_short_data(self):
        asr = VolcengineBigModelASR(api_key="test_key")
        parsed = asr._parse_server_response(b"\x11\x90\x00\x00")
        assert parsed["msg_type"] is None


# ------------------------------------------------------------------
# 测试: _merge_text / _extract_text_from_result
# ------------------------------------------------------------------

class TestTextAggregation:
    def test_merge_text_replace_if_longer(self):
        """候选更长 -> 替换"""
        merged = VolcengineBigModelASR._merge_text("你好", "你好世界")
        assert merged == "你好世界"

    def test_merge_text_keep_if_substring(self):
        """候选是当前子串 -> 保留当前"""
        merged = VolcengineBigModelASR._merge_text("你好世界", "你好")
        assert merged == "你好世界"

    def test_merge_text_empty_current(self):
        merged = VolcengineBigModelASR._merge_text("", "你好")
        assert merged == "你好"

    def test_merge_text_empty_candidate(self):
        merged = VolcengineBigModelASR._merge_text("你好", "")
        assert merged == "你好"

    def test_merge_text_overlap_dedup(self):
        """最大重叠去重拼接"""
        merged = VolcengineBigModelASR._merge_text("ABCDEF", "DEFGHI")
        # 重叠 "DEFG" -> "ABCDEFGHI" 或更短的 "ABCDEF" + "GHI" = "ABCDEFGHI" 均可接受, 但不能是 "ABCDEFGHI" 重复
        assert "ABCDEF" in merged
        assert "GHI" in merged
        # 核心: 不能出现 "DEFG" 重复
        assert "DEFGDEFG" not in merged

    def test_extract_text_uses_definite_utterances(self):
        """definite=true 的 utterances 优先"""
        result = {
            "text": "完整文本内容",
            "utterances": [
                {"text": "第一句", "definite": True},
                {"text": "第二句", "definite": True},
                {"text": "中间结果", "definite": False},
            ],
        }
        text = VolcengineBigModelASR._extract_text_from_result(result)
        assert text == "第一句第二句"

    def test_extract_text_falls_back_to_text(self):
        """无 definite utterances 时使用 result.text"""
        result = {
            "text": "回退文本",
            "utterances": [{"text": "临时", "definite": False}],
        }
        text = VolcengineBigModelASR._extract_text_from_result(result)
        assert text == "回退文本"

    def test_extract_text_falls_back_to_all_utterances(self):
        """无 text 且无 definite, 拼接所有 utterances"""
        result = {
            "text": "",
            "utterances": [
                {"text": "部分一", "definite": False},
                {"text": "部分二", "definite": False},
            ],
        }
        text = VolcengineBigModelASR._extract_text_from_result(result)
        assert text == "部分一部分二"

    def test_extract_text_no_utterances(self):
        result = {"text": "纯文本"}
        text = VolcengineBigModelASR._extract_text_from_result(result)
        assert text == "纯文本"


# ------------------------------------------------------------------
# 测试: transcribe 主流程 (mock websockets)
# ------------------------------------------------------------------

def _make_ws_mock(messages: list[bytes]):
    """构造一个 mock websocket, recv() 按序返回 messages, 耗尽后永远挂起"""
    ws = AsyncMock()
    ws.send = AsyncMock()
    recv_queue = list(messages)

    async def fake_recv():
        if not recv_queue:
            await asyncio.sleep(100)
            raise asyncio.TimeoutError()
        return recv_queue.pop(0)

    ws.recv = fake_recv
    ws.__aenter__ = AsyncMock(return_value=ws)
    ws.__aexit__ = AsyncMock(return_value=False)
    return ws


class TestTranscribe:
    @pytest.mark.asyncio
    async def test_multiple_responses_aggregate_not_replace(self):
        """多次 FULL_SERVER_RESPONSE 应聚合, 不是只保留最后一段"""
        asr = VolcengineBigModelASR(api_key="test_key", frame_size=100, send_interval=0)

        ack = build_ack_frame()
        resp1 = build_full_server_response_frame(text="这是第一段话", flags=0b0001, seq=2)
        resp2 = build_full_server_response_frame(text="这是第一段话这是第二段话", flags=0b0001, seq=3)
        resp3 = build_full_server_response_frame(
            text="这是第一段话这是第二段话这是第三段话", flags=0b0011, seq=-4
        )
        ws_mock = _make_ws_mock([ack, resp1, resp2, resp3])

        with patch("websockets.connect", return_value=ws_mock):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(b"\x00" * 100)
                audio_path = f.name

            result = await asr.transcribe(audio_path)
            Path(audio_path).unlink(missing_ok=True)

        assert "第一段" in result
        assert "第二段" in result
        assert "第三段" in result

    @pytest.mark.asyncio
    async def test_utterances_full_update_no_duplicate(self):
        """核心回归: utterances 全量返回时不应重复, 最终 = '第一句第二句第三句'"""
        asr = VolcengineBigModelASR(api_key="test_key", frame_size=100, send_interval=0)

        ack = build_ack_frame()
        # 三次响应: 每次 utterances 都是全量 (第一句) -> (第一句, 第二句) -> (第一句, 第二句, 第三句)
        resp1 = build_full_server_response_frame(
            text="第一句",
            utterances=[{"text": "第一句", "definite": True}],
            flags=0b0001, seq=2,
        )
        resp2 = build_full_server_response_frame(
            text="第一句第二句",
            utterances=[
                {"text": "第一句", "definite": True},
                {"text": "第二句", "definite": True},
            ],
            flags=0b0001, seq=3,
        )
        resp3 = build_full_server_response_frame(
            text="第一句第二句第三句",
            utterances=[
                {"text": "第一句", "definite": True},
                {"text": "第二句", "definite": True},
                {"text": "第三句", "definite": True},
            ],
            flags=0b0011, seq=-4,
        )
        ws_mock = _make_ws_mock([ack, resp1, resp2, resp3])

        with patch("websockets.connect", return_value=ws_mock):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(b"\x00" * 100)
                audio_path = f.name

            result = await asr.transcribe(audio_path)
            Path(audio_path).unlink(missing_ok=True)

        # 必须正好等于 "第一句第二句第三句", 不能重复
        assert result == "第一句第二句第三句", f"got: {result}"

    @pytest.mark.asyncio
    async def test_final_flags_exit_immediately(self):
        """收到 flags=0b0011 的最终响应后立即退出, 不依赖超时"""
        asr = VolcengineBigModelASR(api_key="test_key", frame_size=100, send_interval=0)

        ack = build_ack_frame()
        final = build_full_server_response_frame(text="最终结果", flags=0b0011, seq=-2)
        ws_mock = _make_ws_mock([ack, final])

        with patch("websockets.connect", return_value=ws_mock):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(b"\x00" * 100)
                audio_path = f.name

            result = await asr.transcribe(audio_path)
            Path(audio_path).unlink(missing_ok=True)

        assert result == "最终结果"
        # send 次数: 1 client request + 1 audio frame = 2
        assert ws_mock.send.call_count == 2

    @pytest.mark.asyncio
    async def test_error_response_raises(self):
        """收到 ERROR_RESPONSE 时抛 VolcengineASRError, 不返回空字符串"""
        asr = VolcengineBigModelASR(api_key="test_key", frame_size=100, send_interval=0)

        ack = build_ack_frame()
        err = build_error_response_frame({"code": 400000, "message": "参数错误", "request_id": "req-err"})
        ws_mock = _make_ws_mock([ack, err])

        with patch("websockets.connect", return_value=ws_mock):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(b"\x00" * 100)
                audio_path = f.name

            with pytest.raises(VolcengineASRError) as exc_info:
                await asr.transcribe(audio_path)
            Path(audio_path).unlink(missing_ok=True)

        # 异常信息应包含脱敏后的 code 和 message
        assert "400000" in str(exc_info.value)
        assert "参数错误" in str(exc_info.value)
        assert "test_key" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_utterances_definite_preferred(self):
        """definite utterances 优先于 result.text"""
        asr = VolcengineBigModelASR(api_key="test_key", frame_size=100, send_interval=0)

        ack = build_ack_frame()
        resp = build_full_server_response_frame(
            text="短",
            utterances=[{"text": "这是一个很长的完整句子", "definite": True}],
            flags=0b0011, seq=-2,
        )
        ws_mock = _make_ws_mock([ack, resp])

        with patch("websockets.connect", return_value=ws_mock):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(b"\x00" * 100)
                audio_path = f.name

            result = await asr.transcribe(audio_path)
            Path(audio_path).unlink(missing_ok=True)

        assert "这是一个很长的完整句子" in result

    @pytest.mark.asyncio
    async def test_no_api_key_still_logs_request_id(self):
        """脱敏: 日志中不输出 api_key"""
        asr = VolcengineBigModelASR(api_key="SUPER_SECRET_KEY", frame_size=100, send_interval=0)

        ack = build_ack_frame()
        final = build_full_server_response_frame(text="ok", flags=0b0011, seq=-2)
        ws_mock = _make_ws_mock([ack, final])

        with patch("websockets.connect", return_value=ws_mock):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(b"\x00" * 100)
                audio_path = f.name

            import io
            from loguru import logger

            log_buf = io.StringIO()
            handler_id = logger.add(log_buf, format="{message}")

            try:
                await asr.transcribe(audio_path)
            finally:
                logger.remove(handler_id)
                Path(audio_path).unlink(missing_ok=True)

            logs = log_buf.getvalue()
            assert "SUPER_SECRET_KEY" not in logs
            assert "req-" in logs
            assert "frame_size" in logs


# ------------------------------------------------------------------
# 测试: 帧构建
# ------------------------------------------------------------------

class TestFrameBuilding:
    def test_default_frame_size(self):
        asr = VolcengineBigModelASR(api_key="k")
        assert asr._frame_size == 6400  # 200ms

    def test_custom_frame_size(self):
        asr = VolcengineBigModelASR(api_key="k", frame_size=3200)
        assert asr._frame_size == 3200

    def test_custom_send_interval(self):
        asr = VolcengineBigModelASR(api_key="k", send_interval=0.1)
        assert asr._send_interval == 0.1

    def test_last_audio_payload_negative_sequence(self):
        """最后一帧 sequence 为负数"""
        asr = VolcengineBigModelASR(api_key="k")
        frame = asr._build_last_audio_payload(b"\x00" * 100, seq=5)
        seq = struct.unpack(">i", frame[4:8])[0]
        assert seq == -5

    def test_client_request_payload_has_bigmodel_and_show_utterances(self):
        asr = VolcengineBigModelASR(api_key="k")
        payload = json.loads(asr._build_full_client_request_payload().decode("utf-8"))
        assert payload["request"]["model_name"] == "bigmodel"
        assert payload["request"]["show_utterances"] is True

    def test_error_class_inherits_runtime_error(self):
        """VolcengineASRError 继承 RuntimeError, 可被 except RuntimeError 捕获"""
        assert issubclass(VolcengineASRError, RuntimeError)
