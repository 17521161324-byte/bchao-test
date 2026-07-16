"""
讯飞实时语音转写大模型 (WebSocket)

文档: https://www.xfyun.cn/doc/spark/asr_llm/rtasr_llm.html

模型配置映射:
- endpoint: wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1
- api_key: accessKeyId
- api_secret: accessKeySecret
- secret_key: AppID
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import uuid
import wave
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import quote, urlencode

from loguru import logger


class IFlytekRealtimeLLMASRError(RuntimeError):
    """讯飞实时转写大模型异常"""


class IFlytekRealtimeLLMASR:
    """讯飞实时语音转写大模型。

    接口要求发送 16k / 16bit / mono 的 PCM 流，推荐 40ms 一包，即 1280 bytes。
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        app_id: str | None = None,
        params: dict[str, Any] | None = None,
        **_: Any,
    ):
        self.endpoint = (endpoint or "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1").strip()
        self.access_key_id = (access_key_id or "").strip()
        self.access_key_secret = (access_key_secret or "").strip()
        self.app_id = (app_id or "").strip()
        self.params = params or {}
        self.frame_size = int(self.params.get("frame_size") or 1280)
        self.send_interval = float(self.params.get("send_interval") or 0.04)
        self.receive_timeout = float(self.params.get("receive_timeout") or 30)

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        self._validate_config()
        audio_bytes = self._load_pcm(audio_path)
        if not audio_bytes:
            return ""

        session_id = uuid.uuid4().hex
        url = self._build_ws_url(session_id=session_id)
        segment_texts: dict[int, str] = {}
        latest_ordered_text = ""

        import websockets

        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=8 * 1024 * 1024) as ws:
                sender = asyncio.create_task(self._send_audio(ws, audio_bytes, session_id))
                try:
                    while True:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=self.receive_timeout)
                        except asyncio.TimeoutError as exc:
                            if sender.done() and latest_ordered_text:
                                logger.warning("讯飞 ASR 未返回 ls=true，使用已收到的转写结果")
                                break
                            raise IFlytekRealtimeLLMASRError("讯飞 ASR 接收结果超时") from exc

                        payload = self._loads_message(message)
                        msg_type = payload.get("msg_type") or payload.get("action")
                        if msg_type == "started":
                            continue
                        if msg_type == "error" or payload.get("code") not in (None, "0", 0):
                            raise IFlytekRealtimeLLMASRError(self._format_error(payload))

                        if msg_type == "result" or payload.get("res_type") == "asr":
                            data = payload.get("data") or {}
                            if isinstance(data, str):
                                data = self._loads_message(data)
                            if not isinstance(data, dict):
                                continue

                            seg_id = int(data.get("seg_id") or len(segment_texts))
                            text = self._extract_text(data)
                            if text:
                                segment_texts[seg_id] = text
                                latest_ordered_text = "".join(segment_texts[k] for k in sorted(segment_texts))

                            if data.get("ls") is True:
                                break

                        # 发送结束标识后继续等待 ls=true，避免截断最后一段。
                finally:
                    if not sender.done():
                        sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)
        except IFlytekRealtimeLLMASRError:
            raise
        except Exception as exc:
            logger.error(f"讯飞实时转写大模型调用失败: {exc}")
            raise IFlytekRealtimeLLMASRError(str(exc)) from exc

        return "".join(segment_texts[k] for k in sorted(segment_texts)).strip() or latest_ordered_text.strip()

    async def health_check(self) -> bool:
        # 该接口没有无音频 ping；这里检查必填配置，避免测试按钮误触发扣量。
        try:
            self._validate_config()
            self._build_ws_url(session_id=uuid.uuid4().hex)
            return True
        except Exception:
            return False

    def _validate_config(self) -> None:
        missing = []
        if not self.app_id:
            missing.append("AppID(secret_key)")
        if not self.access_key_id:
            missing.append("accessKeyId(api_key)")
        if not self.access_key_secret:
            missing.append("accessKeySecret(api_secret)")
        if missing:
            raise IFlytekRealtimeLLMASRError(f"讯飞 ASR 配置缺失: {', '.join(missing)}")

    def _build_ws_url(self, session_id: str) -> str:
        params: dict[str, Any] = {
            "accessKeyId": self.access_key_id,
            "appId": self.app_id,
            "uuid": session_id,
            "utc": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S%z"),
            "audio_encode": self.params.get("audio_encode") or "pcm_s16le",
            "lang": self.params.get("lang") or "autodialect",
            "samplerate": int(self.params.get("samplerate") or 16000),
        }

        optional_keys = [
            "recognized_language",
            "role_type",
            "feature_ids",
            "eng_spk_match",
            "pd",
            "eng_punc",
            "eng_vad_mdn",
        ]
        defaults = {"pd": "medical", "eng_vad_mdn": 2, "role_type": 0}
        for key, default in defaults.items():
            params[key] = self.params.get(key, default)
        for key in optional_keys:
            if key in params:
                continue
            value = self.params.get(key)
            if value is not None and value != "":
                params[key] = value

        base_string = self._signature_base_string(params)
        digest = hmac.new(
            self.access_key_secret.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        params["signature"] = base64.b64encode(digest).decode("utf-8")
        return f"{self.endpoint}?{urlencode(params)}"

    @staticmethod
    def _signature_base_string(params: dict[str, Any]) -> str:
        pairs = []
        for key in sorted(params):
            pairs.append(f"{quote(str(key), safe='')}={quote(str(params[key]), safe='')}")
        return "&".join(pairs)

    @staticmethod
    def _load_pcm(audio_path: str) -> bytes:
        try:
            with wave.open(audio_path, "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except wave.Error as exc:
            raise ValueError(f"讯飞 ASR 仅支持标准 WAV/PCM 输入，当前文件无法解析: {audio_path}") from exc

        if rate != 16000:
            raise ValueError(f"讯飞 ASR 当前仅支持 16000Hz，当前为 {rate}Hz: {audio_path}")
        if sample_width != 2:
            raise ValueError(f"讯飞 ASR 当前仅支持 16bit PCM，当前为 {sample_width * 8}bit: {audio_path}")
        if channels == 1:
            return frames
        if channels == 2:
            import audioop

            return audioop.tomono(frames, sample_width, 0.5, 0.5)
        raise ValueError(f"讯飞 ASR 仅支持单声道/双声道 WAV，当前声道数={channels}: {audio_path}")

    async def _send_audio(self, ws: Any, audio_bytes: bytes, session_id: str) -> None:
        for start in range(0, len(audio_bytes), self.frame_size):
            await ws.send(audio_bytes[start:start + self.frame_size])
            await asyncio.sleep(self.send_interval)
        await ws.send(json.dumps({"end": True, "sessionId": session_id}, ensure_ascii=False))

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

    @classmethod
    def _extract_text(cls, data: dict[str, Any]) -> str:
        st = (((data.get("cn") or {}).get("st")) or {})
        rt_list = st.get("rt") or []
        words: list[str] = []
        for rt in rt_list:
            for ws in rt.get("ws") or []:
                cw_list = ws.get("cw") or []
                if not cw_list:
                    continue
                # 通常取第一个候选词。
                word = cw_list[0].get("w")
                if word:
                    words.append(str(word))
        return "".join(words)

    @staticmethod
    def _format_error(payload: dict[str, Any]) -> str:
        code = payload.get("code") or payload.get("err_no") or ""
        desc = payload.get("desc") or payload.get("message") or payload.get("data") or payload
        return f"讯飞 ASR 错误 {code}: {desc}"
