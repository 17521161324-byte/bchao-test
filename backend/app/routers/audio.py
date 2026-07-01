"""
录音管理路由
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger

from app.database import get_db
from app.models import DateFolder, PatientRecord, AudioSeg, BUltraResult
from app.schemas import DateFolderOut, PatientRecordOut, DataStatusOut
from app.config import settings

router = APIRouter()


@router.get("/tree", response_model=list[DateFolderOut])
async def get_audio_tree(db: AsyncSession = Depends(get_db)):
    """获取录音文件树（日期→病历号→seg）"""
    result = await db.execute(
        select(DateFolder)
        .options(
            selectinload(DateFolder.patients)
            .selectinload(PatientRecord.segs)
        )
        .order_by(DateFolder.date.desc())
    )
    folders = result.scalars().all()

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
