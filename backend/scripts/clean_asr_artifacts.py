"""
清理 ASR 转写文本中的模型输出伪标记

运行方式：
    cd backend
    python scripts/clean_asr_artifacts.py

功能：
    - 清理 patient_asr_results 表中的 language Chinese<asr_text> 伪标记
    - 清理 test_runs 表中的 language Chinese<asr_text> 伪标记
    - 清理 experiment_tasks 表中的 language Chinese<asr_text> 伪标记
    - 同时清理 segments/asr_results 等 JSON 数组中的 text 字段
"""

import re
import json
import sqlite3
from pathlib import Path


def clean_text(text: str) -> str:
    """清洗 ASR 转写文本，移除模型输出伪标记"""
    if not text:
        return text

    cleaned = text.strip()

    # 1. 移除所有 "language Chinese<asr_text>" 组合模式
    cleaned = re.sub(
        r'language\s*[:：]?\s*chinese\s*[:：]?\s*<asr_text>',
        '',
        cleaned,
        flags=re.IGNORECASE
    )

    # 2. 提取 <asr_text>...</asr_text> 闭合标签内的内容
    m = re.search(r'<asr_text>(.*?)</asr_text>', cleaned, re.DOTALL)
    if m:
        cleaned = m.group(1)
    else:
        # 3. 无闭合标签时，移除所有残留标记
        cleaned = cleaned.replace('<asr_text>', '').replace('</asr_text>', '')

    # 4. 兜底：过滤开头的 "language chinese" 前缀
    cleaned = re.sub(
        r'^language\s*[:：]?\s*chinese\s*[:：]?\s*',
        '',
        cleaned,
        flags=re.IGNORECASE
    )

    return cleaned.strip()


def has_artifacts(text: str) -> bool:
    """检查文本是否包含需要清理的伪标记"""
    if not text:
        return False
    return bool(
        re.search(r'language\s*[:：]?\s*chinese', text, re.IGNORECASE)
        or '<asr_text>' in text
    )


def clean_json_array_texts(json_val) -> tuple[bool, any]:
    """清洗 JSON 数组中所有 text 字段，返回 (是否修改, 清洗后数据)"""
    if not json_val:
        return False, json_val

    try:
        items = json.loads(json_val) if isinstance(json_val, str) else json_val
    except (json.JSONDecodeError, TypeError):
        return False, json_val

    if not isinstance(items, list):
        return False, json_val

    changed = False
    for item in items:
        if isinstance(item, dict) and "text" in item and has_artifacts(item["text"]):
            item["text"] = clean_text(item["text"])
            changed = True

    return changed, items


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """获取表的所有列名"""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def clean_table(conn: sqlite3.Connection, table_name: str) -> int:
    """清理指定表中所有包含伪标记的字段，返回更新的行数"""
    columns = get_table_columns(conn, table_name)

    # JSON 数组字段（包含 text 子字段）
    json_array_columns = {"segments", "asr_results", "asr_results_snapshot"}

    # 需要直接清理的文本字段
    text_columns = {"full_transcript"}

    updated_count = 0

    # 查询所有行
    cursor = conn.execute(f"SELECT id FROM {table_name}")
    row_ids = [row[0] for row in cursor.fetchall()]

    for row_id in row_ids:
        row_changed = False

        # 清理文本字段
        for text_col in text_columns.intersection(columns):
            cursor = conn.execute(
                f"SELECT {text_col} FROM {table_name} WHERE id = ?",
                (row_id,)
            )
            text_val = cursor.fetchone()[0]
            if has_artifacts(text_val):
                cleaned = clean_text(text_val)
                conn.execute(
                    f"UPDATE {table_name} SET {text_col} = ? WHERE id = ?",
                    (cleaned, row_id)
                )
                row_changed = True

        # 清理 JSON 数组字段中的 text
        for json_col in json_array_columns.intersection(columns):
            cursor = conn.execute(
                f"SELECT {json_col} FROM {table_name} WHERE id = ?",
                (row_id,)
            )
            json_val = cursor.fetchone()[0]
            if not json_val:
                continue

            changed, new_val = clean_json_array_texts(json_val)
            if changed:
                # 序列化回 JSON 字符串
                new_json = json.dumps(new_val, ensure_ascii=False)
                conn.execute(
                    f"UPDATE {table_name} SET {json_col} = ? WHERE id = ?",
                    (new_json, row_id)
                )
                row_changed = True

        if row_changed:
            updated_count += 1

    return updated_count


def main():
    backend_dir = Path(__file__).resolve().parents[1]
    # 优先使用 .env 配置的路径，否则使用默认路径
    db_path = backend_dir / "data" / "bchao.db"
    if not db_path.exists():
        db_path = backend_dir / "data.db"

    if not db_path.exists():
        print(f"错误：数据库文件不存在 {db_path}")
        print("请确保在 backend 目录下运行此脚本")
        return

    print(f"数据库路径：{db_path}")
    print("=" * 50)

    conn = sqlite3.connect(str(db_path))

    try:
        # 获取所有表
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        all_tables = {row[0] for row in cursor.fetchall()}

        # 需要清理的表
        target_tables = {"patient_asr_results", "test_runs", "experiment_tasks"}
        tables_to_clean = target_tables.intersection(all_tables)

        print(f"待清理的表：{sorted(tables_to_clean)}")
        print()

        total_updated = 0

        for table in sorted(tables_to_clean):
            updated = clean_table(conn, table)
            print(f"  {table}：更新 {updated} 条记录")
            total_updated += updated

        conn.commit()
        print()
        print("=" * 50)
        print(f"完成！共更新 {total_updated} 条记录")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
