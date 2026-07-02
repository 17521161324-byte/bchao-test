"""
录音管理路由
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger

from app.database import get_db
from app.models import DateFolder, PatientRecord, AudioSeg, BUltraResult
from app.schemas import DateFolderOut, PatientRecordOut, DataStatusOut
from app.config import settings

router = APIRouter()


@router.get("/tree")
async def get_audio_tree(db: AsyncSession = Depends(get_db)):
    """获取录音文件树（日期→病历号→seg）"""
    result = await db.execute(
        select(DateFolder)
        .options(
            selectinload(DateFolder.patients)
            .selectinload(PatientRecord.segs),
            selectinload(DateFolder.patients)
            .selectinload(PatientRecord.result),
        )
        .order_by(DateFolder.date.desc())
    )
    folders = result.unique().scalars().all()

    # 构建响应
    output = []
    for folder in folders:
        patients_out = []
        for p in folder.patients:
            has_result = p.result is not None
            patients_out.append({
                "id": p.id,
                "record_id": p.record_id,
                "date_folder_id": p.date_folder_id,
                "timestamp_folder": p.timestamp_folder,
                "segs": [
                    {
                        "id": s.id,
                        "seg_index": s.seg_index,
                        "filename": s.filename,
                        "duration": s.duration,
                        "file_path": s.file_path,
                        "file_size": s.file_size,
                    }
                    for s in sorted(p.segs, key=lambda x: x.seg_index)
                ],
                "has_result": has_result,
            })
        output.append({
            "id": folder.id,
            "date": folder.date,
            "patient_count": len(patients_out),
            "patients": patients_out,
        })
    return output


@router.get("/file")
async def get_audio_file(path: str):
    """获取音频文件流（支持 range 请求）"""
    # 安全检查：防止路径遍历
    recordings_dir = os.path.realpath(settings.RECORDINGS_DIR)
    full_path = os.path.realpath(path)

    if not full_path.startswith(recordings_dir):
        raise HTTPException(status_code=403, message="禁止访问")

    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, message="文件不存在")

    from fastapi.responses import FileResponse
    return FileResponse(
        full_path,
        media_type="audio/wav",
        filename=os.path.basename(full_path),
    )


@router.get("/status", response_model=DataStatusOut)
async def get_data_status(db: AsyncSession = Depends(get_db)):
    """获取数据匹配状态统计"""
    # 总日期数
    date_count = await db.execute(select(func.count(DateFolder.id)))
    total_dates = date_count.scalar()

    # 总病历数
    patient_count = await db.execute(select(func.count(PatientRecord.id)))
    total_patients = patient_count.scalar()

    # 已匹配数（有结果）
    matched = await db.execute(
        select(func.count(PatientRecord.id))
        .join(BUltraResult, BUltraResult.patient_id == PatientRecord.id)
    )
    matched_count = matched.scalar()

    # 仅有录音（无结果）
    audio_only = total_patients - matched_count

    # 仅有结果（无录音）- 理论上不应存在
    result_only = 0

    return {
        "total_dates": total_dates,
        "total_patients": total_patients,
        "matched_count": matched_count,
        "audio_only_count": audio_only,
        "result_only_count": result_only,
    }


@router.post("/scan")
async def scan_recordings(db: AsyncSession = Depends(get_db)):
    """
    扫描录音目录，同步文件结构到数据库
    读取 settings.RECORDINGS_DIR 下的日期→病历号→seg 层级
    """
    recordings_dir = settings.RECORDINGS_DIR
    if not os.path.isdir(recordings_dir):
        raise HTTPException(status_code=400, message=f"录音目录不存在: {recordings_dir}")

    scanned = {"dates": 0, "patients": 0, "segs": 0}

    # 遍历日期文件夹
    for date_name in sorted(os.listdir(recordings_dir)):
        date_path = os.path.join(recordings_dir, date_name)
        if not os.path.isdir(date_path) or not date_name.isdigit():
            continue

        # 查找或创建日期记录
        result = await db.execute(select(DateFolder).where(DateFolder.date == date_name))
        date_folder = result.scalar_one_or_none()
        if not date_folder:
            date_folder = DateFolder(date=date_name, path=date_path)
            db.add(date_folder)
            await db.flush()
            scanned["dates"] += 1

        # 遍历病历号文件夹
        for record_name in sorted(os.listdir(date_path)):
            record_path = os.path.join(date_path, record_name)
            if not os.path.isdir(record_path):
                continue

            # 查找或创建病历记录
            result = await db.execute(
                select(PatientRecord).where(
                    PatientRecord.record_id == record_name,
                    PatientRecord.date_folder_id == date_folder.id,
                )
            )
            patient = result.scalar_one_or_none()
            if not patient:
                patient = PatientRecord(
                    record_id=record_name,
                    date_folder_id=date_folder.id,
                    timestamp_folder="",
                )
                db.add(patient)
                await db.flush()
                scanned["patients"] += 1

            # 查找时间戳文件夹 和 audio/ 子目录
            audio_dir = self_find_audio_dir(record_path)
            if audio_dir and patient:
                patient.timestamp_folder = os.path.basename(os.path.dirname(audio_dir))
                # 遍历 seg 文件
                existing_segs = {s.filename for s in patient.segs}
                for seg_file in sorted(os.listdir(audio_dir)):
                    if not seg_file.endswith(".wav"):
                        continue
                    if seg_file in existing_segs:
                        continue
                    seg_path = os.path.join(audio_dir, seg_file)
                    seg_index = self_parse_seg_index(seg_file)
                    seg = AudioSeg(
                        patient_id=patient.id,
                        seg_index=seg_index,
                        filename=seg_file,
                        file_path=seg_path,
                        file_size=os.path.getsize(seg_path),
                    )
                    db.add(seg)
                    scanned["segs"] += 1

    await db.commit()
    logger.info(f"扫描完成: {scanned}")
    return {"message": "扫描完成", "scanned": scanned}


@router.get("/batches")
async def get_batches(db: AsyncSession = Depends(get_db)):
    """获取批次列表（按日期）及统计"""
    result = await db.execute(
        select(DateFolder.id, DateFolder.date)
        .order_by(DateFolder.date.desc())
    )
    rows = result.all()

    batches = []
    for row in rows:
        # Count patients in this batch
        patient_count = await db.execute(
            select(func.count(PatientRecord.id))
            .where(PatientRecord.date_folder_id == row.id)
        )
        # Count matched (with results)
        matched = await db.execute(
            select(func.count(PatientRecord.id))
            .join(BUltraResult, BUltraResult.patient_id == PatientRecord.id)
            .where(PatientRecord.date_folder_id == row.id)
        )
        batches.append({
            "id": row.id,
            "date": row.date,
            "patient_count": patient_count.scalar(),
            "matched_count": matched.scalar(),
        })
    return batches


@router.get("/verify")
async def verify_data(date: str = None, db: AsyncSession = Depends(get_db)):
    """数据核对：检测异常数据"""
    import os

    result = await db.execute(
        select(DateFolder)
        .options(
            selectinload(DateFolder.patients)
            .selectinload(PatientRecord.segs),
            selectinload(DateFolder.patients)
            .selectinload(PatientRecord.result),
        )
        .order_by(DateFolder.date.desc())
    )
    folders = result.unique().scalars().all()

    if date:
        folders = [f for f in folders if f.date == date]

    issues = []
    for folder in folders:
        # Detect duplicates
        seen_ids = {}
        for p in folder.patients:
            if p.record_id in seen_ids:
                issues.append({
                    "type": "duplicate",
                    "date": folder.date,
                    "record_id": p.record_id,
                    "patient_id": p.id,
                    "detail": f"重复病历号 (同日期已有 id={seen_ids[p.record_id]})",
                    "action": "merge_or_delete",
                })
            else:
                seen_ids[p.record_id] = p.id

        # Check each patient
        for p in folder.patients:
            has_segs = len(p.segs) > 0
            has_result = p.result is not None

            # Check if files actually exist
            missing_files = []
            for s in p.segs:
                if not os.path.isfile(s.file_path):
                    missing_files.append(s.filename)

            if not has_segs and has_result:
                issues.append({
                    "type": "no_audio_has_result",
                    "date": folder.date,
                    "record_id": p.record_id,
                    "patient_id": p.id,
                    "detail": f"无录音但有B超结果",
                    "action": "delete_result",
                })
            elif has_segs and missing_files:
                issues.append({
                    "type": "missing_files",
                    "date": folder.date,
                    "record_id": p.record_id,
                    "patient_id": p.id,
                    "detail": f"缺少 {len(missing_files)} 个录音文件",
                    "action": "investigate",
                    "missing_files": missing_files[:5],
                })

    return {
        "total_issues": len(issues),
        "issues": issues,
    }


@router.get("/records")
async def get_records_flat(date: str = None, db: AsyncSession = Depends(get_db)):
    """获取平铺的患者检查记录列表（用于表格展示）"""
    result = await db.execute(
        select(DateFolder)
        .options(
            selectinload(DateFolder.patients)
            .selectinload(PatientRecord.segs),
            selectinload(DateFolder.patients)
            .selectinload(PatientRecord.result),
        )
        .order_by(DateFolder.date.desc())
    )
    folders = result.unique().scalars().all()

    if date:
        folders = [f for f in folders if f.date == date]

    records = []
    for folder in folders:
        for p in folder.patients:
            records.append({
                "id": p.id,
                "record_id": p.record_id,
                "date": folder.date,
                "date_folder_id": folder.id,
                "timestamp_folder": p.timestamp_folder,
                "has_audio": len(p.segs) > 0,
                "has_result": p.result is not None,
                "segs": [
                    {
                        "id": s.id,
                        "seg_index": s.seg_index,
                        "filename": s.filename,
                        "duration": s.duration,
                        "file_path": s.file_path,
                        "file_size": s.file_size,
                    }
                    for s in sorted(p.segs, key=lambda x: x.seg_index)
                ],
                "result": None,
            })
            if p.result:
                records[-1]["result"] = {
                    "id": p.result.id,
                    "right_follicles": p.result.right_follicles,
                    "left_follicles": p.result.left_follicles,
                    "right_follicle_total": p.result.right_follicle_total,
                    "left_follicle_total": p.result.left_follicle_total,
                    "endometrium_thickness": p.result.endometrium_thickness,
                    "endometrium_type": p.result.endometrium_type,
                    "right_ovary_length": p.result.right_ovary_length,
                    "right_ovary_width": p.result.right_ovary_width,
                    "left_ovary_length": p.result.left_ovary_length,
                    "left_ovary_width": p.result.left_ovary_width,
                    "remark": p.result.remark,
                }

    return records


@router.delete("/patient/{patient_id}")
async def delete_patient(patient_id: int, db: AsyncSession = Depends(get_db)):
    """删除患者记录（包括关联的 B超结果）"""
    import asyncio

    def _do_delete():
        import sqlite3
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Delete associated result
        cursor.execute("DELETE FROM b_ultra_results WHERE patient_id = ?", (patient_id,))
        # Delete associated segs
        cursor.execute("DELETE FROM audio_segs WHERE patient_id = ?", (patient_id,))
        # Delete patient
        cursor.execute("DELETE FROM patient_records WHERE id = ?", (patient_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted

    deleted = await asyncio.to_thread(_do_delete)
    if deleted == 0:
        raise HTTPException(status_code=404, message="患者不存在")
    return {"message": "已删除", "id": patient_id}


@router.get("/patients")
async def get_patients_list(date: str = None, db: AsyncSession = Depends(get_db)):
    """获取患者检查列表（按病历号分组，含录音和结果），支持按日期筛选"""
    result = await db.execute(
        select(DateFolder)
        .options(
            selectinload(DateFolder.patients)
            .selectinload(PatientRecord.segs),
            selectinload(DateFolder.patients)
            .selectinload(PatientRecord.result),
        )
        .order_by(DateFolder.date.desc())
    )
    folders = result.unique().scalars().all()

    # Filter by date if provided
    if date:
        folders = [f for f in folders if f.date == date]

    # Group by record_id
    patients_map: dict[str, list] = {}
    for folder in folders:
        for p in folder.patients:
            record = {
                "id": p.id,
                "record_id": p.record_id,
                "date": folder.date,
                "date_folder_id": folder.id,
                "timestamp_folder": p.timestamp_folder,
                "segs": [
                    {
                        "id": s.id,
                        "seg_index": s.seg_index,
                        "filename": s.filename,
                        "duration": s.duration,
                        "file_path": s.file_path,
                        "file_size": s.file_size,
                    }
                    for s in sorted(p.segs, key=lambda x: x.seg_index)
                ],
                "result": None,
            }
            if p.result:
                record["result"] = {
                    "id": p.result.id,
                    "right_follicles": p.result.right_follicles,
                    "left_follicles": p.result.left_follicles,
                    "right_follicle_total": p.result.right_follicle_total,
                    "left_follicle_total": p.result.left_follicle_total,
                    "endometrium_thickness": p.result.endometrium_thickness,
                    "endometrium_type": p.result.endometrium_type,
                    "right_ovary_length": p.result.right_ovary_length,
                    "right_ovary_width": p.result.right_ovary_width,
                    "left_ovary_length": p.result.left_ovary_length,
                    "left_ovary_width": p.result.left_ovary_width,
                    "remark": p.result.remark,
                }
            if p.record_id not in patients_map:
                patients_map[p.record_id] = []
            patients_map[p.record_id].append(record)

    # Output sorted by date
    output = []
    for record_id, records in patients_map.items():
        output.append({
            "record_id": record_id,
            "examinations": sorted(records, key=lambda x: x["date"], reverse=True),
        })
    return output


def self_find_audio_dir(record_path: str) -> str | None:
    """查找病历号目录下的 audio 文件夹"""
    for root, dirs, files in os.walk(record_path):
        if os.path.basename(root) == "audio":
            return root
    return None


def self_parse_seg_index(filename: str) -> int:
    """从 seg-0001.wav 解析索引"""
    import re
    m = re.search(r"seg-(\d+)", filename)
    return int(m.group(1)) if m else 0
