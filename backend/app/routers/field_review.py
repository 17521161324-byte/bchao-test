"""
字段人工标记路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db
from app.models import FieldReviewMark

router = APIRouter()


@router.get("/{patient_id}/field-review-marks")
async def list_field_review_marks(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取某检查记录的所有字段标记"""
    result = await db.execute(
        select(FieldReviewMark).where(FieldReviewMark.patient_id == patient_id)
    )
    marks = result.scalars().all()
    return [
        {
            "id": m.id,
            "patient_id": m.patient_id,
            "field_group": m.field_group,
            "field_key": m.field_key,
            "mark_type": m.mark_type,
            "reason": m.reason,
            "note": m.note,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        }
        for m in marks
    ]


@router.post("/{patient_id}/field-review-marks")
async def upsert_field_review_mark(
    patient_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """新增或更新字段标记"""
    field_group = data.get("field_group")
    field_key = data.get("field_key") or None
    mark_type = data.get("mark_type")

    if not field_group or not mark_type:
        raise HTTPException(status_code=400, detail="field_group 和 mark_type 必填")
    if mark_type not in ("exclude", "mismatch_note"):
        raise HTTPException(status_code=400, detail="mark_type 必须为 exclude 或 mismatch_note")

    # 查找现有标记
    query = select(FieldReviewMark).where(
        FieldReviewMark.patient_id == patient_id,
        FieldReviewMark.field_group == field_group,
    )
    if field_key:
        query = query.where(FieldReviewMark.field_key == field_key)
    else:
        query = query.where(FieldReviewMark.field_key.is_(None))

    result = await db.execute(query)
    mark = result.scalar_one_or_none()

    if mark:
        mark.mark_type = mark_type
        mark.reason = data.get("reason") or None
        mark.note = data.get("note") or None
    else:
        mark = FieldReviewMark(
            patient_id=patient_id,
            field_group=field_group,
            field_key=field_key,
            mark_type=mark_type,
            reason=data.get("reason") or None,
            note=data.get("note") or None,
        )
        db.add(mark)

    await db.commit()
    await db.refresh(mark)
    return {
        "id": mark.id,
        "patient_id": mark.patient_id,
        "field_group": mark.field_group,
        "field_key": mark.field_key,
        "mark_type": mark.mark_type,
        "reason": mark.reason,
        "note": mark.note,
        "created_at": mark.created_at.isoformat() if mark.created_at else None,
        "updated_at": mark.updated_at.isoformat() if mark.updated_at else None,
    }


@router.delete("/{patient_id}/field-review-marks")
async def delete_field_review_mark(
    patient_id: int,
    field_group: str = Query(...),
    field_key: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """删除字段标记"""
    stmt = delete(FieldReviewMark).where(
        FieldReviewMark.patient_id == patient_id,
        FieldReviewMark.field_group == field_group,
    )
    if field_key:
        stmt = stmt.where(FieldReviewMark.field_key == field_key)
    else:
        stmt = stmt.where(FieldReviewMark.field_key.is_(None))

    await db.execute(stmt)
    await db.commit()
    return {"message": "已清除标记"}
