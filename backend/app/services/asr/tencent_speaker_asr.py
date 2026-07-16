"""
腾讯云实时说话人分离 WebSocket ASR

文档: https://cloud.tencent.com/document/product/1093/131127

模型配置映射:
- endpoint: wss://asr.cloud.tencent.com/asr/v2
- api_key: SecretId
- api_secret: SecretKey
- secret_key: AppID
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import random
import re
import time
import uuid
import wave
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from loguru import logger


class TencentSpeakerASRError(RuntimeError):
    """腾讯云实时说话人分离 ASR 异常"""


class TencentSpeakerASR:
    """腾讯云实时说话人分离 WebSocket。

    当前系统只需要 ASR 文本，所以默认不把 speaker_id 拼进返回文本，避免影响后续 LLM 提取。
    """

    def __init__(
        self,
        endpoint: str | None = None,
        secret_id: str | None = None,
        secret_key: str | None = None,
        app_id: str | None = None,
        params: dict[str, Any] | None = None,
        **_: Any,
    ):
        self.endpoint = (endpoint or "wss://asr.cloud.tencent.com/asr/v2").rstrip("/")
        self.secret_id = (secret_id or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.app_id = (app_id or "").strip()
        self.params = params or {}
        self.frame_size = int(self.params.get("frame_size") or 1280)
        self.send_interval = float(self.params.get("send_interval") or 0.04)
        self.receive_timeout = float(self.params.get("receive_timeout") or 30)
        self.include_speaker = bool(self.params.get("include_speaker") or False)

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        self._validate_config()
        audio_bytes = self._load_pcm(audio_path)
        if not audio_bytes:
            return ""

        voice_id = uuid.uuid4().hex
        url = self._build_ws_url(voice_id=voice_id, hotwords=hotwords)
        sentences: dict[int, dict[str, Any]] = {}
        latest_text = ""

        import websockets

        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=8 * 1024 * 1024) as ws:
                sender = asyncio.create_task(self._send_audio(ws, audio_bytes))
                try:
                    while True:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=self.receive_timeout)
                        except asyncio.TimeoutError as exc:
                            if sender.done() and latest_text:
                                logger.warning("腾讯 ASR 未返回 final=1，使用已收到的转写结果")
                                break
                            raise TencentSpeakerASRError("腾讯 ASR 接收结果超时") from exc

                        payload = self._loads_message(message)
                        code = payload.get("code")
                        if code not in (None, 0, "0"):
                            raise TencentSpeakerASRError(self._format_error(payload))

                        for item in self._extract_sentence_items(payload.get("sentences")):
                            sentence_id = int(item.get("sentence_id") or len(sentences))
                            sentence_text = str(item.get("sentence") or "").strip()
                            if not sentence_text:
                                continue
                            sentences[sentence_id] = {
                                "text": sentence_text,
                                "speaker_id": item.get("speaker_id"),
                                "sentence_type": item.get("sentence_type"),
                            }
                            latest_text = self._join_sentences(sentences)

                        if payload.get("final") == 1:
                            break
                finally:
                    if not sender.done():
                        sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)
        except TencentSpeakerASRError:
            raise
        except Exception as exc:
            logger.error(f"腾讯实时说话人分离 ASR 调用失败: {exc}")
            raise TencentSpeakerASRError(str(exc)) from exc

        return self._join_sentences(sentences).strip() or latest_text.strip()

    async def health_check(self) -> bool:
        # 该接口没有无音频 ping；测试按钮只校验配置与签名 URL 是否可生成。
        try:
            self._validate_config()
            self._build_ws_url(voice_id=uuid.uuid4().hex)
            return True
        except Exception:
            return False

    def _validate_config(self) -> None:
        missing = []
        if not self.app_id:
            missing.append("AppID(secret_key)")
        if not self.secret_id:
            missing.append("SecretId(api_key)")
        if not self.secret_key:
            missing.append("SecretKey(api_secret)")
        if missing:
            raise TencentSpeakerASRError(f"腾讯 ASR 配置缺失: {', '.join(missing)}")

    def _build_ws_url(self, voice_id: str, hotwords: list[str] | None = None) -> str:
        timestamp = int(time.time())
        params: dict[str, Any] = {
            "secretid": self.secret_id,
            "timestamp": timestamp,
            "expired": timestamp + int(self.params.get("signature_ttl") or 24 * 60 * 60),
            "nonce": random.randint(100000, 9999999999),
            "engine_model_type": self.params.get("engine_model_type") or "16k_zh_en_speaker",
            "voice_id": voice_id,
            "voice_format": int(self.params.get("voice_format") or 1),
            "needvad": int(self.params.get("needvad") or 1),
            "filter_dirty": int(self.params.get("filter_dirty") or 0),
            "filter_modal": int(self.params.get("filter_modal") or 0),
            "filter_punc": int(self.params.get("filter_punc") or 0),
            "convert_num_mode": int(self.params.get("convert_num_mode") or 1),
        }

        optional_keys = [
            "enable_speaker_context",
            "speaker_context_id",
            "hotword_id",
            "customization_id",
            "filter_empty_result",
            "noise_threshold",
            "input_sample_rate",
            "replace_text_id",
            "sentence_strategy",
            "domain",
        ]
        for key in optional_keys:
            value = self.params.get(key)
            if value is not None and value != "":
                params[key] = value

        hotword_list = self.params.get("hotword_list") or self._format_hotwords(hotwords)
        if hotword_list:
            params["hotword_list"] = hotword_list

        signing_text = self._signature_base_string(params)
        signature = base64.b64encode(
            hmac.new(self.secret_key.encode("utf-8"), signing_text.encode("utf-8"), hashlib.sha1).digest()
        ).decode("utf-8")
        params["signature"] = signature
        return f"{self._base_ws_url()}?{urlencode(params, quote_via=quote)}"

    def _base_ws_url(self) -> str:
        if self.endpoint.endswith(f"/{self.app_id}"):
            return self.endpoint
        return f"{self.endpoint}/{self.app_id}"

    def _signature_base_string(self, params: dict[str, Any]) -> str:
        parsed = urlparse(self._base_ws_url())
        host = parsed.netloc or "asr.cloud.tencent.com"
        path = parsed.path or f"/asr/v2/{self.app_id}"
        query = "&".join(f"{key}={params[key]}" for key in sorted(params))
        return f"{host}{path}?{query}"

    @staticmethod
    def _format_hotwords(hotwords: list[str] | None) -> str:
        cleaned = [w.strip() for w in hotwords or [] if w and w.strip()]
        if not cleaned:
            return ""
        # 腾讯临时热词格式为 “词|权重”，未显式配置时给常规权重 10。
        return ",".join(f"{word}|10" if "|" not in word else word for word in cleaned[:128])

    @staticmethod
    def _load_pcm(audio_path: str) -> bytes:
        try:
            with wave.open(audio_path, "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except wave.Error as exc:
            raise ValueError(f"腾讯 ASR 仅支持标准 WAV/PCM 输入，当前文件无法解析: {audio_path}") from exc

        if rate != 16000:
            raise ValueError(f"腾讯 ASR 当前配置仅支持 16000Hz，当前为 {rate}Hz: {audio_path}")
        if sample_width != 2:
            raise ValueError(f"腾讯 ASR 当前配置仅支持 16bit PCM，当前为 {sample_width * 8}bit: {audio_path}")
        if channels == 1:
            return frames
        if channels == 2:
            import audioop

            return audioop.tomono(frames, sample_width, 0.5, 0.5)
        raise ValueError(f"腾讯 ASR 仅支持单声道/双声道 WAV，当前声道数={channels}: {audio_path}")

    async def _send_audio(self, ws: Any, audio_bytes: bytes) -> None:
        for start in range(0, len(audio_bytes), self.frame_size):
            await ws.send(audio_bytes[start:start + self.frame_size])
            await asyncio.sleep(self.send_interval)
        await ws.send(json.dumps({"type": "end"}, ensure_ascii=False))

    @staticmethod
    def _loads_message(message: Any) -> dict[str, Any]:
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="ignore")
        if isinstance(message, str):
            try:
                return json.loads(message)
            except json.JSONDecodeError:
                return {}
        return message if isinstance(message, dict) else {}

    @staticmethod
    def _extract_sentence_items(sentences: Any) -> list[dict[str, Any]]:
        if not sentences:
            return []
        if isinstance(sentences, list):
            return [s for s in sentences if isinstance(s, dict)]
        if isinstance(sentences, dict):
            if "sentence" in sentences:
                return [sentences]
            return [s for s in sentences.values() if isinstance(s, dict)]
        if isinstance(sentences, str):
            # 兼容文档示例里的字符串化结构。
            text = sentences
            sentence_match = re.search(r"(?:text|sentence)\s*[:：]\s*([^,，}]+)", text)
            if not sentence_match:
                return []
            sid_match = re.search(r"sentence_id\s*[:：]\s*(\d+)", text)
            speaker_match = re.search(r"speaker_id\s*[:：]\s*(-?\d+)", text)
            type_match = re.search(r"sentence_type\s*[:：]\s*(\d+)", text)
            return [{
                "sentence": sentence_match.group(1).strip(),
                "sentence_id": int(sid_match.group(1)) if sid_match else 0,
                "speaker_id": int(speaker_match.group(1)) if speaker_match else None,
                "sentence_type": int(type_match.group(1)) if type_match else None,
            }]
        return []

    def _join_sentences(self, sentences: dict[int, dict[str, Any]]) -> str:
        parts: list[str] = []
        for sid in sorted(sentences):
            item = sentences[sid]
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            if self.include_speaker and item.get("speaker_id") not in (None, -1, "-1"):
                parts.append(f"说话人{item.get('speaker_id')}：{text}")
            else:
                parts.append(text)
        return "\n".join(parts) if self.include_speaker else "".join(parts)

    @staticmethod
    def _format_error(payload: dict[str, Any]) -> str:
        return f"腾讯 ASR 错误 {payload.get('code')}: {payload.get('message') or payload}"
