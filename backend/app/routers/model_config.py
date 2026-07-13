"""
模型配置路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db
from app.models import ModelConfig
from app.schemas import (
    ModelConfigCreate, ModelConfigUpdate, ModelConfigOut, ModelTestResult
)

router = APIRouter()


@router.get("", response_model=list[ModelConfigOut])
async def list_models(
    model_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """列出所有模型配置"""
    query = select(ModelConfig).order_by(ModelConfig.model_type, ModelConfig.name)
    if model_type:
        query = query.where(ModelConfig.model_type == model_type)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=ModelConfigOut)
async def create_model(
    data: ModelConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """新增模型配置"""
    model = ModelConfig(**data.model_dump())
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


@router.put("/{model_id}", response_model=ModelConfigOut)
async def update_model(
    model_id: int,
    data: ModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新模型配置"""
    result = await db.execute(select(ModelConfig).where(ModelConfig.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(model, k, v)

    await db.commit()
    await db.refresh(model)
    return model


@router.delete("/{model_id}")
async def delete_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除模型配置"""
    result = await db.execute(select(ModelConfig).where(ModelConfig.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    await db.delete(model)
    await db.commit()
    return {"message": "删除成功"}


@router.post("/{model_id}/test", response_model=ModelTestResult)
async def test_model_connection(
    model_id: int,
    db: AsyncSession = Depends(get_db),
):
    """测试模型连通性"""
    import time
    from app.services.asr import create_asr
    from app.services.llm import create_llm

    result = await db.execute(select(ModelConfig).where(ModelConfig.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    start = time.time()
    try:
        if model.model_type == "asr":
            asr = create_asr(model.provider, endpoint=model.endpoint,
                            api_key=model.api_key or "", api_secret=model.api_secret or "")
            # 仅当实现了 health_check 时才测试
            ok = await asr.health_check() if hasattr(asr, 'health_check') else False
        elif model.model_type == "llm":
            llm = create_llm(model.provider, endpoint=model.endpoint,
                             api_key=model.api_key or "")
            ok = await llm.health_check() if hasattr(llm, 'health_check') else False
        else:
            ok = False

        latency = round((time.time() - start) * 1000, 1)
        return ModelTestResult(
            success=ok,
            message="连接正常" if ok else "连接失败",
            latency_ms=latency,
        )
    except Exception as e:
        return ModelTestResult(
            success=False,
            message=f"连接异常: {str(e)}",
            latency_ms=round((time.time() - start) * 1000, 1),
        )


@router.post("/init-defaults")
async def init_default_models(db: AsyncSession = Depends(get_db)):
    """初始化默认模型配置"""
    from app.config import settings

    # 检查是否已存在 local ASR（任意一条即可）
    result = await db.execute(select(ModelConfig).where(ModelConfig.provider == "local"))
    if not result.scalars().all():
        default_asr = ModelConfig(
            name="本地 FunASR",
            model_type="asr",
            provider="local",
            endpoint=settings.LOCAL_ASR_URL,
            is_default=True,
            status="active",
        )
        db.add(default_asr)

    # 检查 MiMo ASR
    result = await db.execute(select(ModelConfig).where(
        ModelConfig.provider == "mimo", ModelConfig.model_type == "asr"
    ))
    if not result.scalars().all():
        mimo_asr = ModelConfig(
            name="MiMo-V2.5-ASR",
            model_type="asr",
            provider="mimo",
            endpoint="https://api.xiaomimimo.com/v1/chat/completions",
            api_key="",
            is_default=False,
            status="active",
        )
        db.add(mimo_asr)

    # 检查 MiMo-V2.5-LLM (用于结构化提取)
    result = await db.execute(select(ModelConfig).where(ModelConfig.name == "MiMo-V2.5-LLM"))
    if not result.scalars().all():
        mimo_llm = ModelConfig(
            name="MiMo-V2.5-LLM",
            model_type="llm",
            provider="mimo",
            endpoint="https://api.xiaomimimo.com/v1",
            api_key="",
            model_name="mimo-v2.5",
            is_default=False,  # 默认不启用，需配置 API Key 后手动启用
            status="inactive",  # 未配置 Key 前设为 inactive
        )
        db.add(mimo_llm)

    # 检查 DeepSeek (用于结构化提取)
    result = await db.execute(select(ModelConfig).where(ModelConfig.provider == "deepseek"))
    if not result.scalars().all():
        deepseek_llm = ModelConfig(
            name="DeepSeek",
            model_type="llm",
            provider="deepseek",
            endpoint="https://api.deepseek.com/v1",
            api_key="",
            model_name="deepseek-chat",
            is_default=False,
            status="active",
        )
        db.add(deepseek_llm)

    # 检查豆包 / 火山引擎 ASR
    result = await db.execute(select(ModelConfig).where(ModelConfig.provider == "volcengine"))
    if not result.scalars().all():
        volc_asr = ModelConfig(
            name="豆包 ASR",
            model_type="asr",
            provider="volcengine",
            endpoint="wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
            api_key="",
            api_secret="",
            secret_key="",
            is_default=False,
            status="active",
        )
        db.add(volc_asr)

    await db.commit()
    return {"message": "初始化成功"}
