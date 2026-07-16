"""
B 超语音测试平台 - 提示词分析与优化工具
==========================================
独立分析工具，从数据库读取已有测试数据，分析 LLM 提取结果与真实结果的偏差模式，
生成提示词优化建议。

使用方式:
    python -m app.services.prompt_analyzer              # 完整分析报告
    python -m app.services.prompt_analyzer --template DP-v4   # 指定模板
    python -m app.services.prompt_analyzer --detail           # 显示详细样本对比
    python -m app.services.prompt_analyzer --suggest          # 生成优化建议

不影响任何现有代码和数据。
"""

import sqlite3
import json
import argparse
import os
import re
from collections import defaultdict
from typing import Any, Optional


# ─────────────────────────────────────────────
# 数据库连接
# ─────────────────────────────────────────────

def get_db_path() -> str:
    """自动定位数据库文件"""
    env_path = os.environ.get("BCHAO_DB_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_path = os.path.join(base_dir, "data", "bchao.db")
    if os.path.exists(default_path):
        return default_path

    smb_path = "/Volumes/bchao-test/backend/data/bchao.db"
    if os.path.exists(smb_path):
        return smb_path

    raise FileNotFoundError("找不到数据库，请设置环境变量 BCHAO_DB_PATH")


def connect_db(db_path: str) -> sqlite3.Connection:
    """只读连接数据库"""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────
# 卵泡归一化（独立实现，不依赖项目代码）
# ─────────────────────────────────────────────

def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return round(float(value), 1)
    except (ValueError, TypeError):
        return None


def normalize_follicles(follicles) -> list[dict]:
    """卵泡明细归一化: 数值化、同尺寸合并、按大小降序。"""
    if not isinstance(follicles, list):
        return []
    merged: dict[float, int] = {}
    for item in follicles:
        if not isinstance(item, dict):
            continue
        size = _to_float(item.get("size"))
        if size is None:
            continue
        try:
            count = int(item.get("count") or 1)
        except (ValueError, TypeError):
            count = 1
        if count <= 0:
            continue
        merged[size] = merged.get(size, 0) + count
    return [
        {"size": size, "count": count}
        for size, count in sorted(merged.items(), key=lambda x: x[0], reverse=True)
    ]


def follicle_total(follicles: list[dict]) -> int:
    return sum(int(f.get("count") or 0) for f in follicles)


# ─────────────────────────────────────────────
# 核心分析逻辑
# ─────────────────────────────────────────────

class PromptAnalyzer:
    """提示词分析器"""

    def __init__(self, db_path: str):
        self.conn = connect_db(db_path)
        self.db_path = db_path

    def close(self):
        self.conn.close()

    # ── 数据概览 ──

    def get_overview(self) -> dict:
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM patient_records")
        total_records = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM patient_records WHERE id IN (SELECT patient_id FROM b_ultra_results)")
        records_with_gt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM patient_asr_results WHERE status='success'")
        asr_success = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM patient_llm_results WHERE status='success' AND accuracy IS NOT NULL")
        llm_evaluated = c.fetchone()[0]
        c.execute("""
            SELECT ROUND(AVG(accuracy) * 100, 1), ROUND(MIN(accuracy) * 100, 1),
                   ROUND(MAX(accuracy) * 100, 1)
            FROM patient_llm_results WHERE status='success' AND accuracy IS NOT NULL
        """)
        avg_acc, min_acc, max_acc = c.fetchone()
        return {
            "total_records": total_records,
            "records_with_gt": records_with_gt,
            "asr_success": asr_success,
            "llm_evaluated": llm_evaluated,
            "avg_accuracy": avg_acc,
            "min_accuracy": min_acc,
            "max_accuracy": max_acc,
        }

    # ── 模板效果对比 ──

    def get_template_stats(self) -> list[dict]:
        c = self.conn.cursor()
        c.execute("""
            SELECT prompt_template_name, COUNT(*) as cnt,
                   ROUND(AVG(accuracy) * 100, 1) as avg_acc,
                   ROUND(MIN(accuracy) * 100, 1) as min_acc,
                   ROUND(MAX(accuracy) * 100, 1) as max_acc,
                   SUM(CASE WHEN accuracy >= 0.8 THEN 1 ELSE 0 END) as high_count,
                   SUM(CASE WHEN accuracy < 0.3 THEN 1 ELSE 0 END) as low_count
            FROM patient_llm_results
            WHERE status='success' AND accuracy IS NOT NULL AND prompt_template_name IS NOT NULL
            GROUP BY prompt_template_name
            ORDER BY avg_acc DESC
        """)
        return [
            {
                "template": row[0], "count": row[1],
                "avg_accuracy": row[2], "min_accuracy": row[3],
                "max_accuracy": row[4], "high_count": row[5], "low_count": row[6],
            }
            for row in c.fetchall()
        ]

    # ── 字段匹配率 ──

    def get_field_match_rates(self, template: str = None) -> dict:
        c = self.conn.cursor()
        query = "SELECT evaluation, prompt_template_name FROM patient_llm_results WHERE status='success' AND evaluation IS NOT NULL AND accuracy IS NOT NULL"
        params = []
        if template:
            query += " AND prompt_template_name = ?"
            params.append(template)
        c.execute(query, params)
        field_stats = defaultdict(lambda: {"total": 0, "match": 0, "mismatch": 0, "null": 0})
        for row in c.fetchall():
            eval_data = json.loads(row[0]) if row[0] else {}
            fields = eval_data.get("fields", {})
            for field_name, field_result in fields.items():
                match = field_result.get("match")
                field_stats[field_name]["total"] += 1
                if match is True:
                    field_stats[field_name]["match"] += 1
                elif match is False:
                    field_stats[field_name]["mismatch"] += 1
                else:
                    field_stats[field_name]["null"] += 1
        return dict(field_stats)

    # ── 错误模式分析 ──

    def analyze_error_patterns(self, template: str = None) -> dict:
        c = self.conn.cursor()
        query = """
            SELECT p.record_id, a.full_transcript, l.structured_result,
                   b.right_follicles, b.left_follicles,
                   l.evaluation, l.accuracy
            FROM patient_llm_results l
            JOIN patient_records p ON l.patient_id = p.id
            JOIN patient_asr_results a ON l.asr_result_id = a.id
            LEFT JOIN b_ultra_results b ON b.patient_id = p.id
            WHERE l.status='success' AND l.accuracy IS NOT NULL AND b.id IS NOT NULL
        """
        params = []
        if template:
            query += " AND l.prompt_template_name = ?"
            params.append(template)
        c.execute(query, params)
        rows = c.fetchall()

        patterns = {
            "left_right_confusion": [],
            "count_mismatch": [],
            "empty_but_has_gt": [],
            "asr_noise": [],
        }

        for row in rows:
            record_id = row[0]
            transcript = row[1] or ""
            structured = json.loads(row[2]) if row[2] else {}
            gt_right = json.loads(row[3]) if row[3] else []
            gt_left = json.loads(row[4]) if row[4] else []
            accuracy = row[6]

            llm_right = normalize_follicles(structured.get("right_follicles", []))
            llm_left = normalize_follicles(structured.get("left_follicles", []))
            llm_right_total = follicle_total(llm_right)
            llm_left_total = follicle_total(llm_left)
            gt_right_total = len(gt_right)
            gt_left_total = len(gt_left)

            # 一侧为空但有GT
            if llm_right_total == 0 and gt_right_total > 0:
                patterns["empty_but_has_gt"].append({
                    "record_id": record_id, "side": "right",
                    "gt_count": gt_right_total, "accuracy": accuracy,
                })
            if llm_left_total == 0 and gt_left_total > 0:
                patterns["empty_but_has_gt"].append({
                    "record_id": record_id, "side": "left",
                    "gt_count": gt_left_total, "accuracy": accuracy,
                })

            # 左右混淆: 一侧数量 >= 自身GT + 另一侧GT*0.5
            if llm_right_total > 0 and gt_right_total > 0:
                if llm_right_total >= gt_right_total + gt_left_total * 0.5:
                    patterns["left_right_confusion"].append({
                        "record_id": record_id, "side": "right",
                        "llm_total": llm_right_total,
                        "gt_right": gt_right_total, "gt_left": gt_left_total,
                        "accuracy": accuracy,
                    })
            if llm_left_total > 0 and gt_left_total > 0:
                if llm_left_total >= gt_left_total + gt_right_total * 0.5:
                    patterns["left_right_confusion"].append({
                        "record_id": record_id, "side": "left",
                        "llm_total": llm_left_total,
                        "gt_right": gt_right_total, "gt_left": gt_left_total,
                        "accuracy": accuracy,
                    })

            # 数量偏差 >1 (排除混淆类)
            confusion_ids = {e["record_id"] for e in patterns["left_right_confusion"]}
            if record_id not in confusion_ids:
                if llm_right_total > 0 and abs(llm_right_total - gt_right_total) > 1:
                    patterns["count_mismatch"].append({
                        "record_id": record_id, "side": "right",
                        "llm": llm_right_total, "gt": gt_right_total,
                        "diff": llm_right_total - gt_right_total,
                    })
                if llm_left_total > 0 and abs(llm_left_total - gt_left_total) > 1:
                    patterns["count_mismatch"].append({
                        "record_id": record_id, "side": "left",
                        "llm": llm_left_total, "gt": gt_left_total,
                        "diff": llm_left_total - gt_left_total,
                    })

            # ASR 噪声
            if accuracy < 0.5:
                noise_found = re.findall(r'\d+[:：]\d+', transcript)
                if noise_found:
                    patterns["asr_noise"].append({
                        "record_id": record_id,
                        "noise": noise_found[:5],
                        "accuracy": accuracy,
                    })

        return patterns

    # ── 详细样本对比 ──

    def get_sample_comparisons(self, template: str = None, limit: int = 5,
                                max_accuracy: float = None) -> list[dict]:
        c = self.conn.cursor()
        query = """
            SELECT p.record_id, a.full_transcript, l.structured_result,
                   b.right_follicles, b.left_follicles,
                   b.endometrium_thickness, b.endometrium_type,
                   b.right_ovary_length, b.right_ovary_width,
                   b.left_ovary_length, b.left_ovary_width,
                   l.evaluation, l.accuracy
            FROM patient_llm_results l
            JOIN patient_records p ON l.patient_id = p.id
            JOIN patient_asr_results a ON l.asr_result_id = a.id
            LEFT JOIN b_ultra_results b ON b.patient_id = p.id
            WHERE l.status='success' AND l.accuracy IS NOT NULL AND b.id IS NOT NULL
        """
        params = []
        conditions = []
        if template:
            conditions.append("l.prompt_template_name = ?")
            params.append(template)
        if max_accuracy is not None:
            conditions.append("l.accuracy <= ?")
            params.append(max_accuracy)
        if conditions:
            query += " AND " + " AND ".join(conditions)
        query += " ORDER BY l.accuracy ASC LIMIT ?"
        params.append(limit)
        c.execute(query, params)

        results = []
        for row in c.fetchall():
            structured = json.loads(row[2]) if row[2] else {}
            results.append({
                "record_id": row[0],
                "transcript": row[1],
                "llm_result": structured,
                "gt_right": json.loads(row[3]) if row[3] else [],
                "gt_left": json.loads(row[4]) if row[4] else [],
                "gt_endometrium": f"{row[5]} / {row[6]}",
                "gt_ovary_right": f"{row[7]} x {row[8]}",
                "gt_ovary_left": f"{row[9]} x {row[10]}",
                "evaluation": json.loads(row[11]) if row[11] else {},
                "accuracy": row[12],
            })
        return results

    # ── 提示词模板 ──

    def get_prompt_templates(self) -> list[dict]:
        c = self.conn.cursor()
        c.execute("SELECT id, name, content, is_default FROM prompt_templates ORDER BY is_default DESC, name")
        return [{"id": r[0], "name": r[1], "content": r[2], "is_default": r[3]} for r in c.fetchall()]

    # ── 优化建议 ──

    def generate_suggestions(self, template: str = None) -> list[dict]:
        suggestions = []
        patterns = self.analyze_error_patterns(template)
        field_stats = self.get_field_match_rates(template)

        confusion_count = len(patterns["left_right_confusion"])
        if confusion_count > 0:
            suggestions.append({
                "priority": "高", "category": "侧别识别",
                "issue": f"发现 {confusion_count} 次左右侧别混淆",
                "suggestion": "在提示词中增加'换边''对侧''另一边'等侧别切换关键词的识别规则，"
                              "明确要求 LLM 在遇到这些词时切换数据归属侧",
            })

        empty_count = len(patterns["empty_but_has_gt"])
        if empty_count > 0:
            suggestions.append({
                "priority": "高", "category": "数据遗漏",
                "issue": f"发现 {empty_count} 次一侧卵泡完全遗漏",
                "suggestion": "增加'分段报数'识别规则 — 医生可能先报一侧再报另一侧，"
                              "中间有闲聊打断。要求 LLM 扫描全文寻找所有侧别数据",
            })

        for field_name in ["right_follicles", "left_follicles"]:
            stats = field_stats.get(field_name, {})
            total = stats.get("total", 0)
            match = stats.get("match", 0)
            rate = (match / total * 100) if total > 0 else 0
            if rate < 40:
                suggestions.append({
                    "priority": "高", "category": "卵泡提取",
                    "issue": f"{field_name} 匹配率仅 {rate:.1f}%",
                    "suggestion": "增加'先数后归类'策略 — 先按文本顺序提取所有数字并标注来源，"
                                  "再根据侧别词分组到对应字段",
                })
                break

        noise_count = len(patterns["asr_noise"])
        if noise_count > 0:
            suggestions.append({
                "priority": "中", "category": "ASR 噪声",
                "issue": f"发现 {noise_count} 次 ASR 噪声导致的数字格式异常",
                "suggestion": "在提示词中增加更多 ASR 噪声模式：冒号分隔的数字视为小数（19:3 -> 19.3）",
            })

        count_mismatch = len(patterns["count_mismatch"])
        if count_mismatch > 0:
            suggestions.append({
                "priority": "中", "category": "数量控制",
                "issue": f"发现 {count_mismatch} 次卵泡数量偏差 >1",
                "suggestion": "增加'数字范围校验'规则 — 卵泡大小通常 3-30mm，"
                              "不在该范围的数字不应计入卵泡列表",
            })

        fol_right = field_stats.get("right_follicles", {})
        fol_left = field_stats.get("left_follicles", {})
        fol_total = fol_right.get("total", 0) + fol_left.get("total", 0)
        fol_match = fol_right.get("match", 0) + fol_left.get("match", 0)
        fol_rate = (fol_match / max(fol_total, 1)) * 100
        if fol_rate < 30:
            suggestions.append({
                "priority": "建议", "category": "评估逻辑",
                "issue": f"卵泡明细匹配率仅 {fol_rate:.1f}%，当前精确匹配过于严格",
                "suggestion": "考虑引入部分得分：卵泡总数容差 +-1 算部分正确，"
                              "卵泡明细改为逐条最近距离匹配",
            })

        return suggestions

    # ── 完整报告 ──

    def generate_report(self, template: str = None, show_detail: bool = False,
                        show_suggestions: bool = False) -> str:
        lines = []
        sep = "=" * 70

        # 1. 概览
        overview = self.get_overview()
        lines.append(sep)
        lines.append("B 超语音测试平台 - 提示词分析报告")
        lines.append(sep)
        lines.append(f"\n数据库: {self.db_path}")
        if template:
            lines.append(f"筛选模板: {template}")
        lines.append(f"\n【数据概览】")
        lines.append(f"  检查记录总数: {overview['total_records']}")
        lines.append(f"  有真实结果:   {overview['records_with_gt']}")
        lines.append(f"  ASR 成功数:   {overview['asr_success']}")
        lines.append(f"  LLM 已评估:   {overview['llm_evaluated']}")
        lines.append(f"  平均准确率:   {overview['avg_accuracy']}%")
        lines.append(f"  最低/最高:    {overview['min_accuracy']}% / {overview['max_accuracy']}%")

        # 2. 模板对比
        template_stats = self.get_template_stats()
        lines.append(f"\n【各模板效果对比】")
        lines.append(f"  {'模板':<20} {'数量':>4} {'平均':>7} {'最低':>7} {'最高':>7} {'>=80%':>5} {'<30%':>5}")
        lines.append(f"  {'-' * 65}")
        for s in template_stats:
            lines.append(
                f"  {s['template']:<20} {s['count']:>4} {s['avg_accuracy']:>6.1f}% "
                f"{s['min_accuracy']:>6.1f}% {s['max_accuracy']:>6.1f}% "
                f"{s['high_count']:>5} {s['low_count']:>5}"
            )

        # 3. 字段匹配率
        field_stats = self.get_field_match_rates(template)
        lines.append(f"\n【各字段匹配率】")
        lines.append(f"  {'字段':<30} {'总数':>4} {'匹配':>4} {'不匹配':>5} {'匹配率':>7}")
        lines.append(f"  {'-' * 60}")
        for field, stats in sorted(field_stats.items(),
                                    key=lambda x: x[1]["match"] / max(x[1]["total"], 1)):
            total = stats["total"]
            match = stats["match"]
            mismatch = stats["mismatch"]
            rate = (match / total * 100) if total > 0 else 0
            lines.append(f"  {field:<30} {total:>4} {match:>4} {mismatch:>5} {rate:>6.1f}%")

        # 4. 错误模式
        patterns = self.analyze_error_patterns(template)
        lines.append(f"\n【错误模式分析】")
        lines.append(f"  左右侧别混淆: {len(patterns['left_right_confusion'])} 次")
        lines.append(f"  一侧完全遗漏: {len(patterns['empty_but_has_gt'])} 次")
        lines.append(f"  数量偏差>1:   {len(patterns['count_mismatch'])} 次")
        lines.append(f"  ASR噪声异常:  {len(patterns['asr_noise'])} 次")

        if patterns["left_right_confusion"]:
            lines.append(f"\n  侧别混淆详情 (前5):")
            for item in patterns["left_right_confusion"][:5]:
                lines.append(
                    f"    {item['record_id']} {item['side']}侧: "
                    f"LLM提取{item['llm_total']}个, GT右={item['gt_right']} GT左={item['gt_left']}, "
                    f"准确率={round(item['accuracy'] * 100)}%"
                )

        if patterns["empty_but_has_gt"]:
            lines.append(f"\n  完全遗漏详情 (前5):")
            for item in patterns["empty_but_has_gt"][:5]:
                lines.append(
                    f"    {item['record_id']} {item['side']}侧: "
                    f"GT有{item['gt_count']}个, 准确率={round(item['accuracy'] * 100)}%"
                )

        # 5. 详细样本
        if show_detail:
            lines.append(f"\n【详细样本对比 (最低准确率前5)】")
            samples = self.get_sample_comparisons(template=template, limit=5)
            for s in samples:
                llm = s["llm_result"]
                llm_right = normalize_follicles(llm.get("right_follicles", []))
                llm_left = normalize_follicles(llm.get("left_follicles", []))
                lines.append(f"\n  --- {s['record_id']} (准确率 {round(s['accuracy'] * 100)}%) ---")
                lines.append(f"  ASR (前300字): {s['transcript'][:300]}...")
                lines.append(f"  LLM 右卵泡 ({follicle_total(llm_right)}个): {llm.get('right_follicles', 'N/A')}")
                lines.append(f"  GT  右卵泡 ({len(s['gt_right'])}个): {s['gt_right']}")
                lines.append(f"  LLM 左卵泡 ({follicle_total(llm_left)}个): {llm.get('left_follicles', 'N/A')}")
                lines.append(f"  GT  左卵泡 ({len(s['gt_left'])}个): {s['gt_left']}")
                lines.append(f"  LLM 内膜: {llm.get('endometrium_thickness', 'N/A')} / {llm.get('endometrium_type', 'N/A')}")
                lines.append(f"  GT  内膜: {s['gt_endometrium']}")
                fields = s["evaluation"].get("fields", {})
                wrong = [k for k, v in fields.items() if v.get("match") is False]
                if wrong:
                    lines.append(f"  错误字段: {', '.join(wrong)}")

        # 6. 优化建议
        if show_suggestions:
            suggestions = self.generate_suggestions(template)
            lines.append(f"\n【优化建议】")
            if not suggestions:
                lines.append("  未发现明显问题")
            for i, s in enumerate(suggestions, 1):
                lines.append(f"\n  {i}. [{s['priority']}] {s['category']}")
                lines.append(f"     问题: {s['issue']}")
                lines.append(f"     建议: {s['suggestion']}")

        lines.append(f"\n{sep}")
        lines.append("分析完成")
        return "\n".join(lines)


# ─────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="B 超语音测试平台 - 提示词分析工具")
    parser.add_argument("--template", "-t", type=str, default=None,
                        help="指定分析的模板名称 (如 DP-v4)")
    parser.add_argument("--detail", "-d", action="store_true",
                        help="显示详细样本对比")
    parser.add_argument("--suggest", "-s", action="store_true",
                        help="生成优化建议")
    parser.add_argument("--db", type=str, default=None,
                        help="指定数据库路径")
    parser.add_argument("--all", "-a", action="store_true",
                        help="显示完整报告（含详情和建议）")
    args = parser.parse_args()

    db_path = args.db or get_db_path()
    analyzer = PromptAnalyzer(db_path)
    try:
        show_detail = args.detail or args.all
        show_suggestions = args.suggest or args.all
        report = analyzer.generate_report(
            template=args.template,
            show_detail=show_detail,
            show_suggestions=show_suggestions,
        )
        print(report)
    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
