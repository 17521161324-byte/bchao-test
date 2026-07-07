"""
豆包 / 火山引擎 流式语音识别 (WebSocket BigModel ASR)
文档: https://www.volcengine.com/docs/6561/1354869

接口:
- 双向流式: wss://openspeech.bytedance.com/api/v3/sauc/bigmodel
- 流式输入: wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream
- 双向流式(优化版): wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async

鉴权: WebSocket 请求头携带 X-Api-Key / X-Api-Resource-Id / X-Api-Request-Id
协议: 自定义二进制协议 (header + payload_size + payload)
"""
import os
import json
import struct
import asyncio
from enum import IntEnum
from loguru import logger


class MessageType(IntEnum):
    FULL_CLIENT_REQUEST = 0b0001
    AUDIO_ONLY_REQUEST = 0b0010
    FULL_SERVER_RESPONSE = 0b1001
    ERROR_RESPONSE = 0b1111


class VolcengineBigModelASR:
    """豆包大模型流式语音识别 (WebSocket 二进制协议)

    优化:单包32000 bytes(1秒音频),帧数减少8倍,发包间隔0.5秒
    """

    def __init__(self, api_key: str = None, endpoint: str = None, **kwargs):
        self.api_key = api_key or os.environ.get("VOLC_API_KEY", "")
        self.endpoint = endpoint or "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
        self._resource_id = kwargs.get("resource_id") or "volc.seedasr.sauc.duration"
        # 关键优化:单包从6400 bytes(200ms)增大到32000 bytes(1秒)
        # 这样原来约1100帧降到约110帧,大幅减少收发次数
        self._frame_size = kwargs.get("frame_size", 32000)

    def _build_header(
        self,
        msg_type: MessageType,
        flags: int = 0b0000,
        serialization: int = 0b0001,
        compression: int = 0b0000,
    ) -> bytes:
        """构建 4 字节 header (大端)"""
        byte0 = (0b0001 << 4) | 0b0001  # version=1, header_size=1 (x4 = 4 bytes)
        byte1 = (msg_type << 4) | flags
        byte2 = (serialization << 4) | compression
        byte3 = 0x00
        return struct.pack("BBBB", byte0, byte1, byte2, byte3)

    def _build_full_client_request_payload(self) -> bytes:
        payload = {
            "user": {"uid": "bchao-test"},
            "audio": {
                "format": "wav",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": False,
            },
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def _build_audio_payload(self, audio_bytes: bytes, seq: int = 1) -> bytes:
        header = self._build_header(
            MessageType.AUDIO_ONLY_REQUEST,
            flags=0b0001,
            serialization=0b0000,
            compression=0b0000,
        )
        seq_bytes = struct.pack(">I", seq)
        size = struct.pack(">I", len(audio_bytes))
        return header + seq_bytes + size + audio_bytes

    def _build_last_audio_payload(self, audio_bytes: bytes, seq: int = 1) -> bytes:
        header = self._build_header(
            MessageType.AUDIO_ONLY_REQUEST,
            flags=0b0011,
            serialization=0b0000,
            compression=0b0000,
        )
        seq_bytes = struct.pack(">i", -seq)
        size = struct.pack(">I", len(audio_bytes))
        return header + seq_bytes + size + audio_bytes

    def _parse_server_response(self, data: bytes) -> dict:
        if len(data) < 8:
            return {}
        header = data[:4]
        msg_type = (header[1] >> 4) & 0xF
        offset = 4
        flags = header[1] & 0xF
        if flags & 0b0001:
            offset += 4
        if len(data) < offset + 4:
            return {}
        payload_size = struct.unpack(">I", data[offset:offset + 4])[0]
        offset += 4
        payload = data[offset:offset + payload_size]

        if msg_type == MessageType.FULL_SERVER_RESPONSE:
            try:
                return json.loads(payload.decode("utf-8"))
            except Exception as e:
                logger.error(f"解析响应 JSON 失败: {e}")
                return {}
        elif msg_type == MessageType.ERROR_RESPONSE:
            error_code = struct.unpack(">I", payload[:4])[0] if len(payload) >= 4 else 0
            error_msg = payload[8:].decode("utf-8", errors="ignore") if len(payload) > 8 else ""
            return {"error": error_msg, "code": error_code}
        return {}

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        import websockets

        with open(audio_path, "rb") as f:
            audio_data = f.read()

        request_id = f"req-{id(audio_data) % 100000}"
        headers = {
            "X-Api-Key": str(self.api_key),
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Request-Id": request_id,
        }

        logger.info(f"[Volcengine] 调用 ASR: audio_size={len(audio_data)}, frame_size={self._frame_size}")

        full_text = ""
        try:
            async with websockets.connect(
                self.endpoint,
                additional_headers=headers,
                ping_interval=None,
            ) as ws:
                # 1. full client request
                client_payload = self._build_full_client_request_payload()
                client_header = self._build_header(MessageType.FULL_CLIENT_REQUEST)
                client_frame = client_header + struct.pack(">I", len(client_payload)) + client_payload
                await ws.send(client_frame)

                # 2. 服务端确认
                resp = await asyncio.wait_for(ws.recv(), timeout=10)
                self._parse_server_response(resp)

                # 3. 分帧发送音频 (每帧1秒,间隔0.5秒)
                offset = 0
                total = len(audio_data)
                seq = 2
                frame_duration = self._frame_size / 32000  # 1秒

                while offset < total:
                    chunk = audio_data[offset:offset + self._frame_size]
                    offset += self._frame_size
                    is_last = offset >= total

                    if is_last:
                        frame = self._build_last_audio_payload(chunk, seq)
                    else:
                        frame = self._build_audio_payload(chunk, seq)
                    await ws.send(frame)
                    seq += 1

                    # 间隔:发送1秒音频,等0.5秒让服务端处理跟上
                    if not is_last:
                        await asyncio.sleep(frame_duration * 0.5)

                # 4. 接收结果
                while True:
                    try:
                        resp = await asyncio.wait_for(ws.recv(), timeout=60)
                        result = self._parse_server_response(resp)
                        if result and "result" in result:
                            text = result["result"].get("text", "")
                            if text:
                                full_text = text
                        if "error" in result:
                            logger.error(f"[Volcengine] 服务端错误: {result}")
                    except asyncio.TimeoutError:
                        break
                    except Exception:
                        break

        except Exception as e:
            logger.error(f"豆包 ASR WebSocket 调用失败: {e}")
            raise RuntimeError(f"豆包 ASR 调用失败: {e}") from e

        return full_text

    async def health_check(self) -> bool:
        try:
            import websockets
            headers = {
                "X-Api-Key": self.api_key,
                "X-Api-Resource-Id": self._resource_id,
                "X-Api-Request-Id": "health-check",
            }
            async with websockets.connect(
                self.endpoint,
                additional_headers=headers,
                open_timeout=5,
            ) as ws:
                return True
        except Exception:
            return False
