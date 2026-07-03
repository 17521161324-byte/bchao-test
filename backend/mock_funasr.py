#!/usr/bin/env python3
"""
本地简易 FunASR 兼容服务（开发用）
提供与 FunASR 相同的 /transcribe 和 /health 接口
实际转写需要部署完整的 FunASR，此处返回占位文本用于 UI 验证

启动方式:
    python mock_funasr.py
或
    uvicorn mock_funasr:app --host 0.0.0.0 --port 50000
"""
import os
import wave
import json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock FunASR (Dev)")


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "mock"}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """模拟转写 - 返回占位文本"""
    if not file.filename.endswith(".wav"):
        raise HTTPException(400, "Only WAV supported")

    # Read file to get duration roughly
    content = await file.read()
    duration = len(content) / 32000  # Rough estimate for 16kHz 16bit mono

    # Return mock transcript
    transcript = (
        "右侧卵泡可见多个发育卵泡，较大的约15毫米乘以1毫米，"
        "13毫米乘以1毫米，12毫米乘以1毫米，10毫米乘以1毫米，"
        "左侧卵泡可见16毫米乘以1毫米，15毫米乘以1毫米，"
        "14毫米乘以1毫米，内膜厚度8毫米，类型A。"
    )

    return {"transcript": transcript, "duration": duration, "mode": "mock"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=50000)
