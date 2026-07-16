"""Recalculate saved evaluation/accuracy values without counting remark.

Run from backend directory:
    python scripts/recalculate_accuracy_without_remark.py
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any


DB_PATH = os.environ.get("BCHAO_DB_PATH", os.path.join("data", "bchao.db"))


FIELD_CONFIGS = [
    ("right_follicle_total", "right_follicle_total", "follicle_total", 0),
    ("left_follicle_total", "left_follicle_total", "follicle_total", 0),
    ("right_follicles", "right_follicles", "follicles", 0),
    ("left_follicles", "left_follicles", "follicles", 0),
    ("endometrium_thickness", "endometrium_thickness", "number", 0.5),
    ("endometrium_type", "endometrium_type", "string", 0),
    ("right_ovary_length", "right_ovary_length", "number", 2.0),
    ("right_ovary_width", "right_ovary_width", "number", 2.0),
    ("left_ovary_length", "left_ovary_length", "number", 2.0),
    ("left_ovary_width", "left_ovary_width", "number", 2.0),
]


def load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def normalize_follicles(follicles: Any) -> list[dict]:
    if not isinstance(follicles, list):
        return []
    merged: dict[float, int] = {}
    for item in follicles:
        if not isinstance(item, dict):
            continue
        try:
            size = round(float(item.get("size")), 1)
            count = int(item.get("count") or 0)
        except Exception:
            continue
        if count <= 0:
            continue
        merged[size] = merged.get(size, 0) + count
    return [{"size": size, "count": count} for size, count in sorted(merged.items(), reverse=True)]


def follicle_total(follicles: list[dict]) -> int:
    return sum(int(f.get("count") or 0) for f in follicles)


def normalize_structured(data: dict) -> dict:
    normalized = dict(data or {})
    for side in ("right", "left"):
        list_key = f"{side}_follicles"
        total_key = f"{side}_follicle_total"
        follicles = normalize_follicles(normalized.get(list_key))
        normalized[list_key] = follicles
        if follicles:
            normalized[total_key] = follicle_total(follicles)
    return normalized


def evaluate_field(identified: Any, truth: Any, field_type: str, tolerance: float = 0) -> dict:
    if identified is None and truth is None:
        return {"match": True, "identified": None, "truth": None, "diff": None}
    if identified is None or truth is None:
        return {"match": False, "identified": identified, "truth": truth, "diff": None}
    if field_type == "number":
        try:
            diff = abs(float(identified) - float(truth))
            return {"match": diff <= tolerance, "identified": identified, "truth": truth, "diff": diff}
        except Exception:
            return {"match": False, "identified": identified, "truth": truth, "diff": None}
    if field_type == "follicle_total":
        try:
            diff = int(identified) - int(truth)
            return {"match": diff == 0, "identified": identified, "truth": truth, "diff": diff}
        except Exception:
            return {"match": False, "identified": identified, "truth": truth, "diff": None}
    if field_type == "follicles":
        id_list = normalize_follicles(identified)
        gt_list = normalize_follicles(truth)
        return {
            "match": id_list == gt_list,
            "identified": id_list,
            "truth": gt_list,
            "diff": None if id_list == gt_list else {"identified_count": follicle_total(id_list), "truth_count": follicle_total(gt_list)},
        }
    match = str(identified).strip() == str(truth).strip()
    return {"match": match, "identified": identified, "truth": truth, "diff": None}


def evaluate_result(identified: dict, ground_truth: dict) -> dict:
    identified = normalize_structured(identified or {})
    result = {"fields": {}, "total_fields": 0, "correct_fields": 0, "accuracy": 0.0}
    for id_field, gt_field, field_type, tolerance in FIELD_CONFIGS:
        field_result = evaluate_field(identified.get(id_field), ground_truth.get(gt_field), field_type, tolerance)
        result["fields"][id_field] = field_result
        result["total_fields"] += 1
        if field_result["match"]:
            result["correct_fields"] += 1
    result["accuracy"] = round(result["correct_fields"] / result["total_fields"], 4) if result["total_fields"] else 0.0
    return result


def ground_truth_from_row(row: sqlite3.Row) -> dict:
    return {
        "right_follicle_total": row["right_follicle_total"],
        "left_follicle_total": row["left_follicle_total"],
        "right_follicles": load_json(row["right_follicles"], []),
        "left_follicles": load_json(row["left_follicles"], []),
        "endometrium_thickness": row["endometrium_thickness"],
        "endometrium_type": row["endometrium_type"],
        "right_ovary_length": row["right_ovary_length"],
        "right_ovary_width": row["right_ovary_width"],
        "left_ovary_length": row["left_ovary_length"],
        "left_ovary_width": row["left_ovary_width"],
    }


def update_table(conn: sqlite3.Connection, table: str, id_col: str = "id") -> int:
    rows = conn.execute(
        f"""
        SELECT t.{id_col} AS row_id, t.structured_result,
               gt.right_follicle_total, gt.left_follicle_total,
               gt.right_follicles, gt.left_follicles,
               gt.endometrium_thickness, gt.endometrium_type,
               gt.right_ovary_length, gt.right_ovary_width,
               gt.left_ovary_length, gt.left_ovary_width
        FROM {table} t
        JOIN b_ultra_results gt ON gt.patient_id = t.patient_id
        WHERE t.structured_result IS NOT NULL
        """
    ).fetchall()
    updated = 0
    for row in rows:
        structured = load_json(row["structured_result"], {})
        if not structured:
            continue
        evaluation = evaluate_result(structured, ground_truth_from_row(row))
        conn.execute(
            f"UPDATE {table} SET evaluation = ?, accuracy = ? WHERE {id_col} = ?",
            (json.dumps(evaluation, ensure_ascii=False), evaluation["accuracy"], row["row_id"]),
        )
        updated += 1
    return updated


def update_test_runs(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT t.id AS row_id, t.structured_result,
               gt.right_follicle_total, gt.left_follicle_total,
               gt.right_follicles, gt.left_follicles,
               gt.endometrium_thickness, gt.endometrium_type,
               gt.right_ovary_length, gt.right_ovary_width,
               gt.left_ovary_length, gt.left_ovary_width
        FROM test_runs t
        JOIN b_ultra_results gt ON gt.record_id = t.record_id AND gt.date = t.date
        WHERE t.structured_result IS NOT NULL
        """
    ).fetchall()
    updated = 0
    for row in rows:
        structured = load_json(row["structured_result"], {})
        if not structured:
            continue
        evaluation = evaluate_result(structured, ground_truth_from_row(row))
        conn.execute(
            "UPDATE test_runs SET evaluation = ?, accuracy = ? WHERE id = ?",
            (json.dumps(evaluation, ensure_ascii=False), evaluation["accuracy"], row["row_id"]),
        )
        updated += 1
    return updated


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        patient_count = update_table(conn, "patient_llm_results")
        experiment_count = update_table(conn, "experiment_tasks")
        test_count = update_test_runs(conn)
        conn.commit()
        print(
            "recalculated:",
            f"patient_llm_results={patient_count}",
            f"experiment_tasks={experiment_count}",
            f"test_runs={test_count}",
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
