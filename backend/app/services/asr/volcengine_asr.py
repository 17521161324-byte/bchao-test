"""
豆包 / 火山引擎 流式语音识别 (WebSocket BigModel ASR)
文档: https://www.volcengine.com/docs/6561/1354869

协议要点 (参考文档 1354869):
- 双向流式: wss://openspeech.bytedance.com/api/v3/sauc/bigmodel
- 流式输入: wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream
- 双向流式(优化版): wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async

鉴权: WebSocket 请求头携带 X-Api-Key / X-Api-Resource-Id / X-Api-Request-Id
协议: 自定义二进制协议 (4-byte header + [sequence] + payload_size + payload)

分包策略:
- 默认 100~200ms/帧,16k/16bit/mono 下 1 秒 = 32000 bytes
- 100ms = 3200 bytes, 200ms = 6400 bytes
- 推荐默认 frame_size=6400, 发包间隔 0.2 秒

结果判断:
- 服务端 FULL_SERVER_RESPONSE 的 flags == 0b0011 表示最后一包结果,收到后立即结束
"""
import os
import json
import gzip
import struct
import asyncio
from enum import IntEnum
from typing import Optional
from loguru import logger


class MessageType(IntEnum):
    FULL_CLIENT_REQUEST = 0b0001
    AUDIO_ONLY_REQUEST = 0b0010
    FULL_SERVER_RESPONSE = 0b1001
    ERROR_RESPONSE = 0b1111


class VolcengineBigModelASR:
    """豆包大模型流式语音识别 (WebSocket 二进制协议)

    实现要点:
    - 分包: 默认 200ms/帧 (6400 bytes), 发包间隔 0.2s
    - 解析: 返回结构化 dict, 支持 gzip 解压, error 按 JSON 解析
    - 结束: 收到 flags==0b0011 的最终响应后立即退出
    - 聚合: 智能合并多轮文本, 优先使用 utterances
    """

    # 16k / 16bit / mono: 1 秒 = 32000 bytes
    BYTES_PER_SECOND = 16000 * 2

    def __init__(self, api_key: str = None, endpoint: str = None, **kwargs):
        self.api_key = api_key or os.environ.get("VOLC_API_KEY", "")
        self.endpoint = endpoint or "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
        self._resource_id = kwargs.get("resource_id") or "volc.seedasr.sauc.duration"
        # 默认 200ms 分包 (6400 bytes), 符合文档 100~200ms 建议
        self._frame_size = kwargs.get("frame_size", 6400)
        # 发包间隔, 默认 0.2 秒
        self._send_interval = kwargs.get("send_interval", 0.2)
        # 是否开启 utterances 分句输出
        self._show_utterances = kwargs.get("show_utterances", True)

    # ------------------------------------------------------------------
    # 二进制帧构建
    # ------------------------------------------------------------------

    def _build_header(
        self,
        msg_type: MessageType,
        flags: int = 0b0000,
        serialization: int = 0b0001,  # JSON
        compression: int = 0b0000,    # 无压缩
    ) -> bytes:
        """构建 4 字节 header (大端)

        Byte0: version(4bits=1) + header_size(4bits=1, 表示 x4=4 bytes)
        Byte1: msg_type(4bits) + flags(4bits)
        Byte2: serialization(4bits) + compression(4bits)
        Byte3: reserved (=0)
        """
        byte0 = (0b0001 << 4) | 0b0001
        byte1 = (msg_type << 4) | flags
        byte2 = (serialization << 4) | compression
        byte3 = 0x00
        return struct.pack("BBBB", byte0, byte1, byte2, byte3)

    def _build_full_client_request_payload(self) -> bytes:
        """构建 full client request 的 JSON payload"""
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
                "show_utterances": self._show_utterances,
            },
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def _build_audio_payload(self, audio_bytes: bytes, seq: int = 1) -> bytes:
        """构建中间音频帧 (正序 sequence)"""
        header = self._build_header(
            MessageType.AUDIO_ONLY_REQUEST,
            flags=0b0001,  # 带正序 sequence
            serialization=0b0000,
            compression=0b0000,
        )
        seq_bytes = struct.pack(">I", seq)
        size = struct.pack(">I", len(audio_bytes))
        return header + seq_bytes + size + audio_bytes

    def _build_last_audio_payload(self, audio_bytes: bytes, seq: int = 1) -> bytes:
        """构建最后一帧 (负序 sequence, 表示音频结束)"""
        header = self._build_header(
            MessageType.AUDIO_ONLY_REQUEST,
            flags=0b0011,  # 带负序 sequence (最后一包)
            serialization=0b0000,
            compression=0b0000,
        )
        seq_bytes = struct.pack(">i", -seq)  # 有符号负数
        size = struct.pack(">I", len(audio_bytes))
        return header + seq_bytes + size + audio_bytes

    # ------------------------------------------------------------------
    # 响应解析
    # ------------------------------------------------------------------

    def _parse_server_response(self, data: bytes) -> dict:
        """解析服务端二进制响应

        返回结构化 dict:
        {
            "msg_type": int,
            "flags": int,
            "sequence": int | None,
            "payload": dict | str | None,  # JSON 解析后的 result / error
            "raw_payload": bytes,          # 解压后的原始 payload
        }
        """
        if len(data) < 8:
            return {"msg_type": None, "flags": 0, "sequence": None, "payload": None, "raw_payload": b""}

        header = data[:4]
        msg_type = (header[1] >> 4) & 0xF
        flags = header[1] & 0xF
        offset = 4

        # flags bit0: 是否带 sequence
        sequence = None
        if flags & 0b0001:
            if len(data) < offset + 4:
                return {"msg_type": msg_type, "flags": flags, "sequence": None, "payload": None, "raw_payload": b""}
            # 正序/负序按有符号 i4 读取, 便于判断最终包
            sequence = struct.unpack(">i", data[offset:offset + 4])[0]
            offset += 4

        if len(data) < offset + 4:
            return {"msg_type": msg_type, "flags": flags, "sequence": sequence, "payload": None, "raw_payload": b""}

        payload_size = struct.unpack(">I", data[offset:offset + 4])[0]
        offset += 4
        raw_payload = data[offset:offset + payload_size]

        # 解压: header byte2 低 4 位为 compression, 0b0001 = gzip
        compression = header[2] & 0xF
        if compression & 0b0001:
            try:
                raw_payload = gzip.decompress(raw_payload)
            except Exception as e:
                logger.warning(f"[Volcengine] gzip 解压失败: {e}")

        # 按消息类型解析 payload
        payload = None
        if msg_type == MessageType.FULL_SERVER_RESPONSE:
            try:
                payload = json.loads(raw_payload.decode("utf-8"))
            except Exception as e:
                logger.error(f"[Volcengine] 解析 FULL_SERVER_RESPONSE JSON 失败: {e}")
                payload = None
        elif msg_type == MessageType.ERROR_RESPONSE:
            # 文档: error response payload 整体为 JSON, 不要再按前 4 字节解析 error_code
            try:
                payload = json.loads(raw_payload.decode("utf-8"))
            except Exception:
                # 兜底: 非 JSON 时保留原始字符串
                payload = {"error": raw_payload.decode("utf-8", errors="ignore")}
        else:
            # 其他类型 (如服务端确认) 尝试 JSON 解析
            try:
                payload = json.loads(raw_payload.decode("utf-8"))
            except Exception:
                payload = None

        return {
            "msg_type": msg_type,
            "flags": flags,
            "sequence": sequence,
            "payload": payload,
            "raw_payload": raw_payload,
        }

    # ------------------------------------------------------------------
    # 文本聚合
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_text(current: str, candidate: str) -> str:
        """智能合并两条候选文本

        规则:
        - 候选比当前长或相等, 视为全量更新, 直接替换
        - 候选是当前子串, 保留当前 (更完整)
        - 当前是候选子串, 替换为候选
        - 互不为子串, 追加去重 (保留 current + candidate 的差异尾段)
        """
        if not candidate:
            return current
        if not current:
            return candidate

        # 一方是另一方子串, 取更长者
        if candidate in current:
            return current
        if current in candidate:
            return candidate

        # 互不为子串: 找最大重叠后缀/前缀, 拼接
        # 简化处理: 直接拼接, 保留 current + candidate
        # 实际场景中服务端通常返回全量, 此分支极少触发
        overlap = 0
        max_overlap = min(len(current), len(candidate))
        for i in range(1, max_overlap + 1):
            if current[-i:] == candidate[:i]:
                overlap = i
        return current + candidate[overlap:]

    @staticmethod
    def _extract_text_from_result(result: dict) -> tuple[str, list[str]]:
        """从单条响应 result 提取候选文本

        返回 (best_text, list_of_utterances_text):
        - 优先使用 utterances 中 definite=true 的句子拼接
        - 否则使用 result.text
        """
        if not result:
            return "", []

        utterances = result.get("utterances") or []
        utterance_texts = [u.get("text", "") for u in utterances if u.get("text")]

        # 优先: definite=true 的 utterances
        definite_texts = [u.get("text", "") for u in utterances if u.get("definite") and u.get("text")]
        if definite_texts:
            return "".join(definite_texts), utterance_texts

        # 否则: result.text
        text = result.get("text", "")
        return text, utterance_texts

    def _aggregate_text(self, full_text: str, parsed: dict) -> tuple[str, list[str]]:
        """聚合多轮响应文本

        返回 (new_full_text, all_utterances):
        - 维护 full_text 为当前最优全量文本
        - 维护 all_utterances 为所有见过的 utterance 候选
        """
        payload = parsed.get("payload")
        if not payload or not isinstance(payload, dict):
            return full_text, []

        result = payload.get("result") or {}
        candidate, utterance_texts = self._extract_text_from_result(result)
        new_full = self._merge_text(full_text, candidate) if candidate else full_text
        return new_full, utterance_texts

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        """转写本地音频文件

        流程:
        1. 建立 WebSocket 连接
        2. 发送 full client request (配置参数)
        3. 等待服务端确认
        4. 按 frame_size 分帧发送音频, 最后一帧带负序
        5. 循环接收响应, 收到最终响应 (flags==0b0011) 后退出
        6. 返回聚合后的完整文本
        """
        import websockets

        with open(audio_path, "rb") as f:
            audio_data = f.read()

        request_id = f"req-{id(audio_data) % 100000}"
        headers = {
            "X-Api-Key": str(self.api_key),
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Request-Id": request_id,
        }

        # 脱敏日志: 不输出 api_key / headers / 音频内容
        logger.info(
            f"[Volcengine] 开始转写: request_id={request_id}, "
            f"audio_size={len(audio_data)} bytes, "
            f"frame_size={self._frame_size}, "
            f"interval={self._send_interval}s"
        )

        full_text = ""
        all_utterance_texts: list[str] = []
        final_received = False
        seq = 2  # 从 2 开始, 1 保留给 full client request

        try:
            async with websockets.connect(
                self.endpoint,
                additional_headers=headers,
                ping_interval=None,
            ) as ws:
                # 1. 发送 full client request
                client_payload = self._build_full_client_request_payload()
                client_header = self._build_header(MessageType.FULL_CLIENT_REQUEST)
                client_frame = client_header + struct.pack(">I", len(client_payload)) + client_payload
                await ws.send(client_frame)

                # 2. 等待服务端确认
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=10)
                    parsed_ack = self._parse_server_response(resp)
                    logger.info(
                        f"[Volcengine] 服务端确认: msg_type={parsed_ack.get('msg_type')}, "
                        f"flags={parsed_ack.get('flags')}"
                    )
                except asyncio.TimeoutError:
                    logger.warning("[Volcengine] 等待服务端确认超时, 继续发送音频")

                # 3. 分帧发送音频
                offset = 0
                total = len(audio_data)
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

                    # 发包间隔, 最后一帧后不需要等
                    if not is_last:
                        await asyncio.sleep(self._send_interval)

                # 4. 接收响应, 直到收到最终响应 (flags==0b0011)
                while not final_received:
                    try:
                        resp = await asyncio.wait_for(ws.recv(), timeout=60)
                        parsed = self._parse_server_response(resp)

                        msg_type = parsed.get("msg_type")
                        flags = parsed.get("flags")
                        sequence = parsed.get("sequence")

                        # 脱敏日志: 不输出 payload 内容, 只输出元信息
                        logger.info(
                            f"[Volcengine] 收到响应: msg_type={msg_type}, "
                            f"flags={flags}, sequence={sequence}"
                        )

                        if msg_type == MessageType.FULL_SERVER_RESPONSE:
                            full_text, utts = self._aggregate_text(full_text, parsed)
                            all_utterance_texts.extend(utts)

                            # 最终响应判断: flags == 0b0011
                            if flags == 0b0011:
                                logger.info(
                                    f"[Volcengine] 收到最终响应 (flags=0b0011), "
                                    f"text_len={len(full_text)}"
                                )
                                final_received = True
                                break

                        elif msg_type == MessageType.ERROR_RESPONSE:
                            # error payload 已按 JSON 解析
                            logger.error(f"[Volcengine] 服务端错误: {parsed.get('payload')}")
                            # 收到错误也退出, 避免死等
                            break

                    except asyncio.TimeoutError:
                        logger.warning("[Volcengine] 接收响应超时, 主动退出")
                        break
                    except Exception as e:
                        logger.warning(f"[Volcengine] 接收响应异常: {e}")
                        break

        except Exception as e:
            logger.error(f"[Volcengine] WebSocket 调用失败: {e}")
            raise RuntimeError(f"豆包 ASR 调用失败: {e}") from e

        # 最终文本选择: 优先使用 utterances 拼接 (更完整), 否则用 full_text
        if all_utterance_texts:
            utterances_combined = "".join(all_utterance_texts)
            if len(utterances_combined) >= len(full_text):
                full_text = utterances_combined

        logger.info(
            f"[Volcengine] 转写完成: request_id={request_id}, "
            f"final_text_len={len(full_text)}"
        )
        return full_text

    async def health_check(self) -> bool:
        """连通性测试 (仅检查 TCP+TLS 握手, 不发送音频)"""
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
