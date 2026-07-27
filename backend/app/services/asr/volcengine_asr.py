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

并发设计:
- sender task: 按 frame_size 分帧发送音频
- receiver task: 边接收边聚合 result.text / utterances
- 收到最终响应或错误后, 通过 Event 通知 sender 退出
"""
import os
import json
import gzip
import struct
import asyncio
import wave
import inspect
from enum import IntEnum
from typing import Optional, List, Dict, Tuple, Union
from loguru import logger


class VolcengineASRError(RuntimeError):
    """豆包 ASR 服务端返回错误"""
    pass


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
    - 聚合: 每轮响应独立生成 utterances_candidate, 用 _merge_text 合并
    - 并发: sender/receiver 异步协作, 最终响应/错误后互相通知退出
    - 错误: ERROR_RESPONSE 抛出 VolcengineASRError, 不返回空字符串
    - 热词: 支持传入 hotwords 列表, 写入 request.context 作为 JSON 字符串
    """

    # 16k / 16bit / mono: 1 秒 = 32000 bytes
    BYTES_PER_SECOND = 16000 * 2
    ENDPOINTS = {
        "bigmodel": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
        "bigmodel_nostream": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",
        "bigmodel_async": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
    }

    def __init__(self, api_key: str = None, endpoint: str = None, **kwargs):
        self.api_key = api_key or os.environ.get("VOLC_API_KEY", "")
        self._params = kwargs
        self._endpoint_mode = kwargs.get("endpoint_mode") or "bigmodel_nostream"
        self.endpoint = self._resolve_endpoint(endpoint, self._endpoint_mode)
        self._resource_id = kwargs.get("resource_id") or "volc.seedasr.sauc.duration"
        # 默认 200ms 分包 (6400 bytes), 符合文档 100~200ms 建议
        self._frame_size = kwargs.get("frame_size", 6400)
        # 发包间隔, 默认 0.2 秒
        self._send_interval = kwargs.get("send_interval", 0.2)
        # 是否开启 utterances 分句输出。默认关闭：豆包偶发返回 confidence=NaN，
        # 会导致服务端解析 utterances 失败；系统主要依赖 result.text。
        self._show_utterances = kwargs.get("show_utterances", False)
        # 单次 ws.recv 等待时间；nostream 通常会在音频超过 15s 或最后一包后返回。
        self._receive_timeout = float(kwargs.get("receive_timeout_seconds") or 60)
        # 总等待时间可显式覆盖；不配置时按音频时长/发送节奏动态计算。
        self._total_timeout = kwargs.get("total_timeout_seconds")

    @classmethod
    def _resolve_endpoint(cls, endpoint: Optional[str], endpoint_mode: Optional[str]) -> str:
        """按配置选择豆包 ASR 端点。

        已有模型里通常保存的是官方 bigmodel URL。为了不要求用户手工改 URL，
        当 endpoint 属于官方 sauc/bigmodel 系列时，按 endpoint_mode 归一化。
        自定义 URL 保持不变。
        """
        mode = str(endpoint_mode or "bigmodel_nostream").strip()
        target = cls.ENDPOINTS.get(mode, cls.ENDPOINTS["bigmodel_nostream"])
        if not endpoint:
            return target
        normalized = str(endpoint).strip()
        if "openspeech.bytedance.com/api/v3/sauc/bigmodel" in normalized:
            return target
        return normalized

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

    @staticmethod
    def _connect_kwargs(websockets_module, headers: Dict[str, str], **kwargs) -> Dict:
        """兼容不同 websockets 版本的请求头参数名。

        websockets <= 13 使用 extra_headers；
        websockets >= 14 使用 additional_headers。
        """
        params = dict(kwargs)
        signature = inspect.signature(websockets_module.connect)
        header_arg = "additional_headers" if "additional_headers" in signature.parameters else "extra_headers"
        params[header_arg] = headers
        return params

    def _build_full_client_request_payload(
        self,
        hotwords: Optional[List[str]] = None,
        audio_meta: Optional[Dict] = None,
    ) -> bytes:
        """构建 full client request 的 JSON payload

        如有 hotwords, 写入 request.context 作为 JSON 字符串:
        context = json.dumps({"hotwords": [{"word": w} for w in hotwords]})
        """
        request_params = {
            "model_name": "bigmodel",
            "result_type": self._params.get("result_type") or "full",  # 每次返回全量识别结果, 避免增量拼接
            "enable_itn": bool(self._params.get("enable_itn", True)),
            "enable_punc": bool(self._params.get("enable_punc", True)),
            "enable_ddc": bool(self._params.get("enable_ddc", False)),
            "show_utterances": self._show_utterances,
        }
        context_mode = str(self._params.get("context_mode") or "").strip()

        # 请求上下文共用 request.corpus.context，同次调用只应写入一种:
        # - hotwords: {"hotwords": [{"word": "..."}]}
        # - dialog_ctx: {"context_type": "dialog_ctx", "context_data": [{"text": "..."}]}
        # 旧配置没有 context_mode 时保持热词优先。
        if hotwords and context_mode != "dialog_ctx":
            cleaned = [w.strip() for w in hotwords if w and w.strip()]
            if cleaned:
                context_str = json.dumps(
                    {"hotwords": [{"word": w} for w in cleaned]},
                    ensure_ascii=False,
                )
                corpus = request_params.setdefault("corpus", {})
                corpus["context"] = context_str

        context_text = str(self._params.get("context_text") or "").strip()
        if context_text and (context_mode == "dialog_ctx" or "context" not in request_params.get("corpus", {})):
            context_str = json.dumps(
                {
                    "context_type": "dialog_ctx",
                    "context_data": [{"text": context_text}],
                },
                ensure_ascii=False,
            )
            corpus = request_params.setdefault("corpus", {})
            # 显式 hotwords 优先；没有 hotwords 时使用业务上下文。
            corpus.setdefault("context", context_str)

        # 火山自学习平台热词表 / 替换词表。
        # 文档字段名:
        # request.corpus.boosting_table_name / boosting_table_id
        # request.corpus.correct_table_name / correct_table_id
        for key in ("boosting_table_name", "boosting_table_id", "correct_table_name", "correct_table_id"):
            value = getattr(self, "_params", {}).get(key)
            if value is not None and str(value).strip():
                corpus = request_params.setdefault("corpus", {})
                corpus[key] = str(value).strip()

        for key in ("enable_nonstream", "enable_speaker_info", "end_window_size", "vad_segment_duration", "force_to_speech_time", "enable_auto_lang"):
            value = getattr(self, "_params", {}).get(key)
            if value is not None and value != "":
                request_params[key] = value

        audio = {
            "format": "pcm",
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
            "language": "zh-CN",
        }
        if audio_meta:
            audio.update(audio_meta)

        payload = {
            "user": {"uid": "bchao-test"},
            "audio": audio,
            "request": request_params,
        }
        logger.info(
            "[Volcengine] 请求参数: "
            f"endpoint_mode={self._endpoint_mode}, "
            f"request_keys={sorted(request_params.keys())}, "
            f"result_type={request_params.get('result_type')}, "
            f"enable_itn={request_params.get('enable_itn')}, "
            f"enable_punc={request_params.get('enable_punc')}, "
            f"enable_ddc={request_params.get('enable_ddc')}, "
            f"show_utterances={request_params.get('show_utterances')}, "
            f"has_corpus={'corpus' in request_params}, "
            f"has_context={'context' in request_params.get('corpus', {})}, "
            f"boosting_table_id={'yes' if request_params.get('corpus', {}).get('boosting_table_id') else 'no'}, "
            f"boosting_table_name={'yes' if request_params.get('corpus', {}).get('boosting_table_name') else 'no'}, "
            f"correct_table_id={'yes' if request_params.get('corpus', {}).get('correct_table_id') else 'no'}, "
            f"correct_table_name={'yes' if request_params.get('corpus', {}).get('correct_table_name') else 'no'}"
        )
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _load_audio_payload(audio_path: str) -> Tuple[bytes, Dict]:
        """读取音频并返回可流式分包的 payload 与 audio 元信息。

        豆包 WebSocket 的 audio-only payload 是每包 100~200ms 的音频数据。
        如果直接把 wav 容器文件按字节切片, 只有第一包带 wav header, 后续包不是合法
        wav 片段, 容易导致只识别到少量文本。这里对 wav 文件先抽取 PCM 帧,
        并在请求中声明 format=pcm/codec=raw。
        """
        try:
            with wave.open(audio_path, "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except wave.Error:
            # 单元测试或极少数非 wav 输入兜底: 按 16k/16bit/mono PCM 处理。
            with open(audio_path, "rb") as f:
                frames = f.read()
            logger.warning(f"[Volcengine] 音频不是标准 WAV, 按 raw PCM 兜底发送: {audio_path}")
            return frames, {
                "format": "pcm",
                "codec": "raw",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
                "language": "zh-CN",
            }

        bits = sample_width * 8
        if bits != 16:
            raise ValueError(f"豆包 ASR 仅支持 16bit PCM/WAV, 当前为 {bits}bit: {audio_path}")
        if rate != 16000:
            raise ValueError(f"豆包 ASR 当前配置仅支持 16000Hz, 当前为 {rate}Hz: {audio_path}")
        if channels not in (1, 2):
            raise ValueError(f"豆包 ASR 仅支持 mono/stereo, 当前声道数={channels}: {audio_path}")

        return frames, {
            "format": "pcm",
            "codec": "raw",
            "rate": rate,
            "bits": bits,
            "channel": channels,
            "language": "zh-CN",
        }

    def _build_audio_payload(self, audio_bytes: bytes, seq: int = 1) -> bytes:
        """构建中间音频帧 (正序 sequence)"""
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
        """构建最后一帧 (负序 sequence, 表示音频结束)"""
        header = self._build_header(
            MessageType.AUDIO_ONLY_REQUEST,
            flags=0b0011,
            serialization=0b0000,
            compression=0b0000,
        )
        seq_bytes = struct.pack(">i", -seq)
        size = struct.pack(">I", len(audio_bytes))
        return header + seq_bytes + size + audio_bytes

    # ------------------------------------------------------------------
    # 响应解析
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_error_message(message: object) -> str:
        """清理服务端错误文本，避免 \\x00 等不可见字符让界面只显示半截。"""
        text = "" if message is None else str(message)
        return "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32).strip()

    @classmethod
    def _is_retryable_utterances_error(cls, error: object) -> bool:
        """识别豆包 utterances/confidence=NaN 导致的可降级错误。"""
        text = cls._sanitize_error_message(error).lower()
        return (
            ("fail to parse big asr response" in text or "server-side generic error" in text)
            and ("confidence" in text or "nan" in text or "utterance" in text)
        )

    @staticmethod
    def _format_error_payload(error_payload) -> Tuple[Optional[Union[str, int]], str]:
        """兼容火山错误响应的多种字段名，避免日志里只剩 code=None/message=None。"""
        if isinstance(error_payload, dict):
            code = (
                error_payload.get("code")
                or error_payload.get("error_code")
                or error_payload.get("err_code")
                or error_payload.get("status_code")
            )
            message = (
                error_payload.get("message")
                or error_payload.get("error")
                or error_payload.get("error_msg")
                or error_payload.get("msg")
                or error_payload.get("reason")
            )
            if not message:
                message = json.dumps(error_payload, ensure_ascii=False)
            return code, VolcengineBigModelASR._sanitize_error_message(message)
        if error_payload is None:
            return None, "empty error payload"
        return None, VolcengineBigModelASR._sanitize_error_message(error_payload)

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
                payload = {"error": raw_payload.decode("utf-8", errors="ignore")}
        else:
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
        """全量快照式合并 (result_type=full 专用)

        火山豆包 result_type=full 时, 每次响应都是全量识别结果, 直接替换即可。
        不做重叠检测和拼接, 以避免重复文本。
        - candidate 非空: 直接以 candidate 作为当前 full_text
        - candidate 为空: 保留 current
        """
        if candidate:
            return candidate
        return current

    @staticmethod
    def _extract_text_from_result(result: dict) -> str:
        """从单条响应 result 提取候选文本

        result_type=full 下优先使用 result.text (全量)。
        只有 result.text 为空时, 才用 utterances 拼接兜底。
        """
        if not result:
            return ""

        # 最高优先: result.text (全量识别结果)
        text = result.get("text", "")
        if text:
            return text

        # 兜底: 所有 utterances 文本拼接
        utterances = result.get("utterances") or []
        all_texts = [u.get("text", "") for u in utterances if u.get("text")]
        return "".join(all_texts)

    # ------------------------------------------------------------------
    # 主流程 (并发 sender/receiver)
    # ------------------------------------------------------------------

    async def transcribe(self, audio_path: str, hotwords: Optional[List[str]] = None) -> str:
        """转写本地音频文件

        流程:
        1. 建立 WebSocket 连接
        2. 发送 full client request (含 hotwords context)
        3. 启动 receiver task 边收边聚合
        4. sender task 按 frame_size 分帧发送音频
        5. 收到 flags==0b0011 最终响应后, receiver 通知 sender 退出
        6. receiver 返回聚合后的完整文本
        """
        try:
            return await self._transcribe_once(audio_path, hotwords=hotwords)
        except VolcengineASRError as exc:
            if not self._show_utterances or not self._is_retryable_utterances_error(exc):
                raise VolcengineASRError(self._sanitize_error_message(exc)) from exc
            logger.warning("[Volcengine] utterances/confidence 解析失败，关闭 show_utterances 后自动重试一次")
            original = self._show_utterances
            try:
                self._show_utterances = False
                return await self._transcribe_once(audio_path, hotwords=hotwords)
            except Exception as retry_exc:
                raise RuntimeError(self._sanitize_error_message(retry_exc)) from retry_exc
            finally:
                self._show_utterances = original

    async def _transcribe_once(self, audio_path: str, hotwords: Optional[List[str]] = None) -> str:
        import websockets

        audio_data, audio_meta = self._load_audio_payload(audio_path)
        bytes_per_second = (
            int(audio_meta.get("rate") or 16000)
            * int(audio_meta.get("channel") or 1)
            * int(audio_meta.get("bits") or 16)
            / 8
        )
        audio_duration = len(audio_data) / bytes_per_second if bytes_per_second else 0
        chunk_count = max(1, (len(audio_data) + int(self._frame_size) - 1) // int(self._frame_size))
        estimated_send_seconds = chunk_count * float(self._send_interval or 0)
        if self._total_timeout:
            total_timeout = float(self._total_timeout)
        else:
            # 整段/长音频按实时节奏发送时，固定 120s 会在音频尚未发完前取消任务。
            # 这里按“预计发送耗时 + 2 分钟识别余量”动态放宽，同时保留 120s 下限。
            total_timeout = max(120.0, estimated_send_seconds + 120.0, audio_duration + 120.0)

        request_id = f"req-{id(audio_data) % 100000}"
        headers = {
            "X-Api-Key": str(self.api_key),
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Request-Id": request_id,
        }

        logger.info(
            f"[Volcengine] 开始转写: request_id={request_id}, "
            f"audio_payload_size={len(audio_data)} bytes, "
            f"audio_duration={audio_duration:.1f}s, "
            f"estimated_send_seconds={estimated_send_seconds:.1f}s, "
            f"total_timeout={total_timeout:.1f}s, "
            f"audio_meta={audio_meta}, "
            f"frame_size={self._frame_size}, "
            f"interval={self._send_interval}s, "
            f"hotwords_count={len(hotwords) if hotwords else 0}"
        )

        # 跨 task 状态
        full_text = ""
        final_received = asyncio.Event()  # receiver 收到最终响应/错误后 set
        ws_ref: list = []  # 让 sender 能感知连接是否断开
        error_holder: list = []  # 传递错误信息给 sender

        async def receiver(ws):
            """接收并聚合响应"""
            nonlocal full_text
            try:
                while True:
                    try:
                        resp = await asyncio.wait_for(ws.recv(), timeout=self._receive_timeout)
                    except asyncio.TimeoutError:
                        logger.warning(f"[Volcengine] 接收响应超时, request_id={request_id}")
                        break

                    parsed = self._parse_server_response(resp)
                    msg_type = parsed.get("msg_type")
                    flags = parsed.get("flags")
                    sequence = parsed.get("sequence")

                    logger.info(
                        f"[Volcengine] 收到响应: msg_type={msg_type}, "
                        f"flags={flags}, sequence={sequence}"
                    )

                    if msg_type == MessageType.FULL_SERVER_RESPONSE:
                        # 聚合: result_type=full 下, 每次响应都是全量, 直接替换
                        payload = parsed.get("payload")
                        final_text = None
                        if isinstance(payload, dict):
                            result = payload.get("result") or {}
                            candidate = self._extract_text_from_result(result)
                            if candidate:
                                full_text = candidate  # full snapshot, 直接替换
                            # 记录最终响应的文本 (优先作为返回值)
                            if flags == 0b0011:
                                final_text = result.get("text") or None

                        # 最终响应判断: flags == 0b0011
                        if flags == 0b0011:
                            logger.info(
                                f"[Volcengine] 收到最终响应 (flags=0b0011), "
                                f"text_len={len(full_text)}, request_id={request_id}"
                            )
                            # 最终响应有 result.text 时, 直接作为返回值
                            if final_text:
                                full_text = final_text
                            final_received.set()
                            return full_text

                    elif msg_type == MessageType.ERROR_RESPONSE:
                        # error payload 已按 JSON 解析
                        error_payload = parsed.get("payload", {})
                        error_holder.append(error_payload)
                        # 脱敏: 只输出 code / message / request_id
                        code, message = self._format_error_payload(error_payload)
                        logger.error(
                            f"[Volcengine] 服务端错误: code={code}, "
                            f"message={message}, request_id={request_id}"
                        )
                        final_received.set()
                        raise VolcengineASRError(
                            self._sanitize_error_message(f"豆包 ASR 错误: code={code}, message={message}")
                        )

            except VolcengineASRError:
                raise
            except Exception as e:
                logger.error(f"[Volcengine] receiver 异常: {e}, request_id={request_id}")
            finally:
                # 确保最终退出时 set, 避免 sender 悬挂
                final_received.set()
            return full_text

        async def sender(ws):
            """分帧发送音频, 收到 final_received 后提前退出"""
            try:
                # 发送 full client request (含 hotwords context)
                client_payload = self._build_full_client_request_payload(
                    hotwords=hotwords,
                    audio_meta=audio_meta,
                )
                client_header = self._build_header(MessageType.FULL_CLIENT_REQUEST)
                client_frame = client_header + struct.pack(">I", len(client_payload)) + client_payload
                await ws.send(client_frame)

                # 分帧发送音频
                offset = 0
                total = len(audio_data)
                seq = 2
                while offset < total:
                    # 如果 receiver 已收到最终响应, 提前停止发送
                    if final_received.is_set():
                        logger.info(f"[Volcengine] 收到最终响应, 提前停止发送, request_id={request_id}")
                        break

                    chunk = audio_data[offset:offset + self._frame_size]
                    offset += self._frame_size
                    is_last = offset >= total

                    if is_last:
                        frame = self._build_last_audio_payload(chunk, seq)
                    else:
                        frame = self._build_audio_payload(chunk, seq)

                    try:
                        await ws.send(frame)
                    except Exception:
                        # 连接断开, 停止发送
                        break
                    seq += 1

                    # 发包间隔, 最后一帧或已收到最终响应后不等
                    if not is_last and not final_received.is_set():
                        await asyncio.sleep(self._send_interval)
            except Exception as e:
                logger.warning(f"[Volcengine] sender 退出: {e}, request_id={request_id}")

        # 建立连接 + 并发运行 sender/receiver
        try:
            async with websockets.connect(
                self.endpoint,
                **self._connect_kwargs(websockets, headers, ping_interval=None),
            ) as ws:
                ws_ref.append(ws)

                # 注意: 标准双向流式需要先发 full client request 再接收确认,
                # 但豆包服务端实际行为是: 客户端发配置后, 服务端会先回一条确认。
                # 此处采用先发 client request 再并发收发的方式

                send_task = asyncio.create_task(sender(ws))
                recv_task = asyncio.create_task(receiver(ws))

                # 等待 receiver 完成 (收到最终响应或错误)
                try:
                    await asyncio.wait_for(recv_task, timeout=total_timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"[Volcengine] transcribe 总超时, request_id={request_id}")

                # 等 sender 完成 (应该很快, 因为 final_received 已 set)
                if not send_task.done():
                    send_task.cancel()
                    try:
                        await send_task
                    except (asyncio.CancelledError, Exception):
                        pass

                # 取出 receiver 结果或异常
                if recv_task.done():
                    exc = recv_task.exception()
                    if exc:
                        raise exc
                    full_text = recv_task.result()

        except VolcengineASRError:
            raise
        except Exception as e:
            logger.error(f"[Volcengine] WebSocket 调用失败: {e}, request_id={request_id}")
            raise RuntimeError(self._sanitize_error_message(f"豆包 ASR 调用失败: {e}")) from e

        final_text = full_text
        logger.info(
            f"[Volcengine] 转写完成: request_id={request_id}, "
            f"final_text_len={len(final_text)}"
        )
        return final_text

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
                **self._connect_kwargs(websockets, headers, open_timeout=5),
            ) as ws:
                return True
        except Exception:
            return False
