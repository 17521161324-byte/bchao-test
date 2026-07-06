"""
提示词模版管理路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db
from app.models import PromptTemplate

router = APIRouter()


@router.get("")
async def list_templates(db: AsyncSession = Depends(get_db)):
    """列出所有提示词模版"""
    result = await db.execute(select(PromptTemplate).order_by(PromptTemplate.is_default.desc(), PromptTemplate.name))
    return result.scalars().all()


@router.get("/{template_id}")
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """获取单个模版"""
    tmpl = await db.get(PromptTemplate, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="模版不存在")
    return tmpl


@router.post("")
async def create_template(data: dict, db: AsyncSession = Depends(get_db)):
    """新建模版"""
    name = (data.get("name") or "").strip()
    content = data.get("content", "")
    if not name:
        raise HTTPException(status_code=400, detail="模版名称不能为空")
    if not content:
        raise HTTPException(status_code=400, detail="模版内容不能为空")
    if "{transcript}" not in content:
        raise HTTPException(status_code=400, detail="模版内容必须包含 {transcript} 占位符")

    # 名称唯一性检查
    existing = await db.execute(select(PromptTemplate).where(PromptTemplate.name == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"模版名称「{name}」已存在")

    tmpl = PromptTemplate(
        name=name,
        content=content,
        is_default=data.get("is_default", False),
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.put("/{template_id}")
async def update_template(template_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """更新模版"""
    tmpl = await db.get(PromptTemplate, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="模版不存在")

    if "name" in data:
        name = data["name"].strip()
        if not name:
            raise HTTPException(status_code=400, detail="模版名称不能为空")
        # 名称唯一性检查（排除自身）
        existing = await db.execute(
            select(PromptTemplate).where(PromptTemplate.name == name, PromptTemplate.id != template_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"模版名称「{name}」已存在")
        tmpl.name = name

    if "content" in data:
        if not data["content"]:
            raise HTTPException(status_code=400, detail="模版内容不能为空")
        if "{transcript}" not in data["content"]:
            raise HTTPException(status_code=400, detail="模版内容必须包含 {transcript} 占位符")
        tmpl.content = data["content"]

    if "is_default" in data:
        tmpl.is_default = bool(data["is_default"])

    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.delete("/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """删除模版"""
    tmpl = await db.get(PromptTemplate, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="模版不存在")
    await db.delete(tmpl)
    await db.commit()
    return {"message": "删除成功"}


@router.post("/init-defaults")
async def init_default_templates(db: AsyncSession = Depends(get_db)):
    """初始化默认模版"""
    from app.services.parser import DEFAULT_PROMPT_TEMPLATE

    # 检查是否已有模版
    result = await db.execute(select(PromptTemplate))
    if result.scalars().all():
        return {"message": "已存在模版，跳过初始化"}

    default = PromptTemplate(
        name="默认 B 超提取模版",
        content=DEFAULT_PROMPT_TEMPLATE,
        is_default=True,
    )
    db.add(default)
    await db.commit()
    return {"message": "初始化成功"}
