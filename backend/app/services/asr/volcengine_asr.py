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
import gzip
import hmac
import hashlib
import struct
import asyncio
import uuid
from datetime import datetime, timezone
from enum import IntEnum
from loguru import logger


class MessageType(IntEnum):
    FULL_CLIENT_REQUEST = 0b0001
    AUDIO_ONLY_REQUEST = 0b0010
    FULL_SERVER_RESPONSE = 0b1001
    ERROR_RESPONSE = 0b1111


class VolcengineBigModelASR:
    """豆包大模型流式语音识别 (WebSocket 二进制协议)

    兼容新旧两版控制台:
    - 新版: 只填 api_key (作为 X-Api-Key)
    - 旧版: 填 api_key (App ID) + api_secret (Access Token) + secret_key (签名密钥)
    """

    def __init__(self, api_key: str = None, endpoint: str = None, **kwargs):
        self.api_key = api_key or os.environ.get("VOLC_API_KEY", "")
        # 旧版可能同时需要 access_key 和 secret_key
        self._access_key = kwargs.get("access_key") or os.environ.get("VOLC_ACCESS_KEY", "")
        self._secret_key = kwargs.get("secret_key") or os.environ.get("VOLC_SECRET_KEY", "")
        # 默认使用双向流式
        self.endpoint = endpoint or "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
        self._resource_id = kwargs.get("resource_id") or "volc.seedasr.sauc.duration"
        # 分包大小: 200ms * 16000Hz * 2bytes = 6400 bytes
        self._frame_size = kwargs.get("frame_size", 6400)

    def _build_auth_headers(self, request_id: str) -> dict:
        """构建鉴权头 (按文档要求: 旧版只需 App-Key + Access-Key)"""
        # 新版控制台: 只需 X-Api-Key
        if not self._access_key and not self._secret_key:
            return {
                "X-Api-Key": self.api_key,
                "X-Api-Resource-Id": self._resource_id,
                "X-Api-Request-Id": request_id,
                "X-Api-Sequence": "-1",
            }
        # 旧版控制台: App-Key + Access-Key (无需签名)
        return {
            "X-Api-App-Key": self.api_key,
            "X-Api-Access-Key": self._access_key,
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1",
        }

    def _build_header(
        self,
        msg_type: MessageType,
        flags: int = 0b0000,
        serialization: int = 0b0001,  # JSON
        compression: int = 0b0001,  # Gzip (按文档示例)
    ) -> bytes:
        """构建 4 字节 header (大端)"""
        # Byte 0: version(4 bits) + header_size(4 bits)
        byte0 = (0b0001 << 4) | 0b0001  # version=1, header_size=1 (x4 = 4 bytes)
        # Byte 1: message_type(4 bits) + flags(4 bits)
        byte1 = (msg_type << 4) | flags
        # Byte 2: serialization(4 bits) + compression(4 bits)
        byte2 = (serialization << 4) | compression
        # Byte 3: reserved
        byte3 = 0x00
        return struct.pack("BBBB", byte0, byte1, byte2, byte3)

    def _build_full_client_request_payload(self, audio_format: str = "pcm", rate: int = 16000) -> bytes:
        """构建 full client request 的 JSON payload (Gzip 压缩)"""
        payload = {
            "user": {"uid": "bchao-test"},
            "audio": {
                "format": audio_format,
                "rate": rate,
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
        json_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return gzip.compress(json_bytes)

    def _build_audio_payload(self, audio_bytes: bytes, seq: int = 1) -> bytes:
        """构建 audio only request 帧 (Gzip 压缩)"""
        compressed = gzip.compress(audio_bytes)
        header = self._build_header(
            MessageType.AUDIO_ONLY_REQUEST,
            flags=0b0001,  # 带正序 sequence
            serialization=0b0000,
            compression=0b0001,  # Gzip
        )
        seq_bytes = struct.pack(">I", seq)
        size = struct.pack(">I", len(compressed))
        return header + seq_bytes + size + compressed

    def _build_last_audio_payload(self, audio_bytes: bytes, seq: int = 1) -> bytes:
        """构建最后一包 (负序, Gzip 压缩)"""
        compressed = gzip.compress(audio_bytes)
        header = self._build_header(
            MessageType.AUDIO_ONLY_REQUEST,
            flags=0b0011,  # 带负序 sequence (最后一包)
            serialization=0b0000,
            compression=0b0001,  # Gzip
        )
        seq_bytes = struct.pack(">i", -seq)  # 有符号负数
        size = struct.pack(">I", len(compressed))
        return header + seq_bytes + size + compressed

    def _parse_server_response(self, data: bytes) -> dict:
        """解析服务端响应"""
        if len(data) < 8:
            return {}
        # 前 4 字节 header
        header = data[:4]
        msg_type = (header[1] >> 4) & 0xF
        # 接下来 4 字节 sequence (可选)
        offset = 4
        flags = header[1] & 0xF
        if flags & 0b0001:  # 有 sequence
            offset += 4
        # 4 字节 payload size
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
            logger.error(f"服务端错误: code={error_code}, msg={error_msg}")
            return {"error": error_msg, "code": error_code}
        return {}

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        """转写本地音频文件"""
        import websockets

        # 读取音频文件 - 提取原始 PCM 数据
        with open(audio_path, "rb") as f:
            raw = f.read()

        # 如果是 WAV 文件，提取 PCM 数据（去掉 RIFF header）
        audio_data = raw
        if raw[:4] == b"RIFF":
            pos = 12
            while pos < len(raw) - 8:
                chunk_id = raw[pos:pos + 4]
                chunk_size = struct.unpack("<I", raw[pos + 4:pos + 8])[0]
                if chunk_id == b"data":
                    audio_data = raw[pos + 8:pos + 8 + chunk_size]
                    break
                pos += 8 + chunk_size + (chunk_size % 2)

        logger.info(f"[Volcengine] 音频数据大小: {len(audio_data)} bytes")
        request_id = str(uuid.uuid4())
        headers = self._build_auth_headers(request_id)

        full_text = ""
        if not self.api_key:
            raise RuntimeError("豆包 ASR 未配置 API Key，请在模型配置中填写")

        try:
            import websockets
            logger.info(f"[Volcengine] 调用 ASR: endpoint={self.endpoint}, api_key={self.api_key[:8]}..., resource_id={self._resource_id}")
            async with websockets.connect(
                self.endpoint,
                additional_headers=headers,
                ping_interval=None,
            ) as ws:
                logger.info("[Volcengine] WebSocket 已连接")
                # 1. 发送 full client request
                client_payload = self._build_full_client_request_payload()
                client_header = self._build_header(MessageType.FULL_CLIENT_REQUEST)
                client_frame = client_header + struct.pack(">I", len(client_payload)) + client_payload
                await ws.send(client_frame)
                logger.info("[Volcengine] 已发送 full client request")

                # 2. 接收服务端确认
                resp = await asyncio.wait_for(ws.recv(), timeout=10)
                logger.info(f"[Volcengine] 已收到服务端确认, {len(resp)} bytes")
                self._parse_server_response(resp)

                # 3. 分帧发送音频 (sequence 从 2 开始, 1 已被 full client request 使用)
                offset = 0
                total = len(audio_data)
                seq = 2  # sequence 1 已被 full client request 占用
                logger.info(f"[Volcengine] 开始发送 {total} bytes 音频...")
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

                logger.info(f"[Volcengine] 音频发送完成, 共 {seq - 2} 帧, 等待识别结果...")
                # 4. 循环接收所有响应
                while True:
                    try:
                        resp = await asyncio.wait_for(ws.recv(), timeout=5)
                        result = self._parse_server_response(resp)
                        if result and "result" in result and "text" in result["result"]:
                            full_text = result["result"]["text"]
                            logger.info(f"[Volcengine] 收到识别结果, 长度: {len(full_text)}")
                        if "error" in result:
                            logger.error(f"[Volcengine] 服务端返回错误: {result}")
                    except asyncio.TimeoutError:
                        break
                    except Exception:
                        # 服务器正常关闭连接 (如 "received 1000 OK")
                        break

        except Exception as e:
            logger.error(f"豆包 ASR WebSocket 调用失败: {e}")
            raise RuntimeError(f"豆包 ASR 调用失败: {e}") from e

        return full_text

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            import websockets
            headers = {
                "X-Api-Key": self.api_key,
                "X-Api-Resource-Id": self._resource_id,
                "X-Api-Request-Id": str(uuid.uuid4()),
            }
            logger.info(f"[Volcengine] 连接测试 → {self.endpoint}")
            async with websockets.connect(
                self.endpoint,
                additional_headers=headers,
                open_timeout=10,
                ping_interval=None,
            ) as ws:
                logger.info("[Volcengine] WebSocket 建连成功")
                return True
        except Exception as e:
            logger.error(f"[Volcengine] 健康检查失败: {e}")
            return False
