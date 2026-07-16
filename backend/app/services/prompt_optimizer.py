"""
B 超语音测试平台 - 闭环提示词优化器
======================================
半自动优化循环：
  1. 从数据库加载测试数据（ASR文本 + Ground Truth）
  2. 用当前提示词调用 LLM 提取结构化结果
  3. 与 Ground Truth 对比评估
  4. 分析错误模式，展示报告
  5. 暂停等待用户审核
  6. 用户可修改提示词后进入下一轮

使用方式:
    python3 -m app.services.prompt_optimizer
    python3 -m app.services.prompt_optimizer --template DP-v4 --rounds 5
    python3 -m app.services.prompt_optimizer --sample 20  # 只取20条快速迭代

不影响任何现有代码和数据。
"""

import sqlite3
import json
import argparse
import os
import re
import time
import sys
import httpx
from collections import defaultdict
from typing import Any, Optional


# ─────────────────────────────────────────────
# 数据库
# ─────────────────────────────────────────────

def get_db_path() -> str:
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
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────
# 卵泡归一化 & 评估（独立实现）
# ─────────────────────────────────────────────

def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return round(float(value), 1)
    except (ValueError, TypeError):
        return None


def normalize_follicles(follicles) -> list[dict]:
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
    return [{"size": s, "count": c} for s, c in sorted(merged.items(), key=lambda x: x[0], reverse=True)]


def follicle_total(follicles: list[dict]) -> int:
    return sum(int(f.get("count") or 0) for f in follicles)


def evaluate_field(identified, ground_truth, field_type="number", tolerance=0.0) -> dict:
    if identified is None and ground_truth is None:
        return {"match": True}
    if identified is None or ground_truth is None:
        return {"match": False}
    if field_type == "number":
        try:
            diff = abs(float(identified) - float(ground_truth))
            return {"match": diff <= tolerance, "diff": round(diff, 2)}
        except (ValueError, TypeError):
            return {"match": False}
    if field_type == "string":
        return {"match": str(identified).strip() == str(ground_truth).strip()}
    if field_type == "follicle_total":
        try:
            return {"match": int(identified) == int(ground_truth), "diff": int(identified) - int(ground_truth)}
        except (ValueError, TypeError):
            return {"match": False}
    if field_type == "follicles":
        id_list = normalize_follicles(identified)
        gt_list = normalize_follicles(ground_truth)
        return {"match": id_list == gt_list, "id_count": follicle_total(id_list), "gt_count": follicle_total(gt_list)}
    return {"match": str(identified) == str(ground_truth)}


def evaluate_result(identified: dict, ground_truth: dict) -> dict:
    field_configs = [
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
    fields = {}
    correct = 0
    for id_f, gt_f, ftype, tol in field_configs:
        r = evaluate_field(identified.get(id_f), ground_truth.get(gt_f), ftype, tol)
        fields[id_f] = r
        if r["match"]:
            correct += 1
    total = len(field_configs)
    return {
        "fields": fields,
        "accuracy": round(correct / total, 4) if total > 0 else 0.0,
        "correct": correct,
        "total": total,
    }


# ─────────────────────────────────────────────
# LLM 调用（同步版本，用于 CLI 工具）
# ─────────────────────────────────────────────

class LLMClient:
    def __init__(self, api_key: str, endpoint: str, model_name: str):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        if self.endpoint.endswith("/chat/completions"):
            self.endpoint = self.endpoint[:-len("/chat/completions")]
        self.model_name = model_name

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def extract(self, transcript: str, prompt_template: str, temperature: float = 0.1) -> dict:
        """调用 LLM 提取结构化结果，返回 parsed JSON 或 None"""
        user_prompt = prompt_template.replace("{transcript}", transcript)
        if "{transcript}" not in prompt_template:
            user_prompt = f"{prompt_template}\n\n## 转写文本\n\n{transcript}"

        url = f"{self.endpoint}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "你是一名医学数据结构化专家。请严格按照用户要求的 JSON 格式返回，不要附加任何解释或 Markdown。"},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "stream": False,
        }

        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(url, headers=self._headers(), json=payload)
                resp.raise_for_status()
                data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            return self._parse_json(raw), raw
        except Exception as e:
            print(f"  [LLM 错误] {e}")
            return None, None

    def _parse_json(self, text: str) -> dict:
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None


# ─────────────────────────────────────────────
# 测试数据加载
# ─────────────────────────────────────────────

def load_test_data(db_path: str, sample: int = None) -> list[dict]:
    """加载有 Ground Truth 的测试数据"""
    conn = connect_db(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT p.id, p.record_id, a.full_transcript,
               b.right_follicles, b.left_follicles,
               b.right_ovary_length, b.right_ovary_width,
               b.left_ovary_length, b.left_ovary_width,
               b.endometrium_thickness, b.endometrium_type,
               b.right_follicle_total, b.left_follicle_total
        FROM patient_records p
        JOIN patient_asr_results a ON a.patient_id = p.id AND a.is_current = 1
        JOIN b_ultra_results b ON b.patient_id = p.id
        WHERE a.status = 'success' AND a.full_transcript IS NOT NULL
        ORDER BY p.record_id
    """)
    data = []
    for row in c.fetchall():
        gt = {
            "right_follicles": json.loads(row[3]) if row[3] else [],
            "left_follicles": json.loads(row[4]) if row[4] else [],
            "right_ovary_length": row[5],
            "right_ovary_width": row[6],
            "left_ovary_length": row[7],
            "left_ovary_width": row[8],
            "endometrium_thickness": row[9],
            "endometrium_type": row[10],
            "right_follicle_total": row[11],
            "left_follicle_total": row[12],
        }
        data.append({
            "patient_id": row[0],
            "record_id": row[1],
            "transcript": row[2],
            "ground_truth": gt,
        })
    conn.close()
    if sample and sample < len(data):
        import random
        random.seed(42)
        data = random.sample(data, sample)
    return data


def load_prompt(db_path: str, name: str) -> str:
    """从数据库加载提示词模板"""
    conn = connect_db(db_path)
    c = conn.cursor()
    c.execute("SELECT content FROM prompt_templates WHERE name = ?", (name,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    raise ValueError(f"提示词模板 '{name}' 不存在")


def load_llm_config(db_path: str) -> dict:
    """加载默认 LLM 配置"""
    conn = connect_db(db_path)
    c = conn.cursor()
    c.execute("SELECT provider, model_name, endpoint, api_key FROM model_configs WHERE is_default = 1 AND provider != 'local' LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        return {"provider": row[0], "model_name": row[1], "endpoint": row[2], "api_key": row[3]}
    raise ValueError("未找到可用的 LLM 配置")


# ─────────────────────────────────────────────
# 报告生成
# ─────────────────────────────────────────────

def generate_round_report(results: list[dict], round_num: int, prompt_name: str) -> str:
    """生成单轮评估报告"""
    lines = []
    sep = "=" * 70

    accuracies = [r["accuracy"] for r in results]
    avg_acc = sum(accuracies) / len(accuracies) * 100

    # 字段统计
    field_names = ["right_follicle_total", "left_follicle_total", "right_follicles", "left_follicles",
                   "endometrium_thickness", "endometrium_type",
                   "right_ovary_length", "right_ovary_width", "left_ovary_length", "left_ovary_width"]
    field_match = defaultdict(lambda: {"match": 0, "total": 0})
    for r in results:
        for fn in field_names:
            fd = r["eval"]["fields"].get(fn, {})
            field_match[fn]["total"] += 1
            if fd.get("match"):
                field_match[fn]["match"] += 1

    lines.append(f"\n{sep}")
    lines.append(f"  第 {round_num} 轮评估报告 | 模板: {prompt_name}")
    lines.append(sep)
    lines.append(f"\n  样本数: {len(results)}")
    lines.append(f"  平均准确率: {avg_acc:.1f}%")
    lines.append(f"  完全正确(100%): {sum(1 for a in accuracies if a == 1.0)}")
    lines.append(f"  高准确率(>=80%): {sum(1 for a in accuracies if a >= 0.8)}")
    lines.append(f"  低准确率(<30%): {sum(1 for a in accuracies if a < 0.3)}")
    lines.append(f"  零准确率(0%): {sum(1 for a in accuracies if a == 0.0)}")

    lines.append(f"\n  【各字段匹配率】")
    lines.append(f"  {'字段':<25} {'匹配':>4} {'总数':>4} {'匹配率':>7}")
    lines.append(f"  {'-' * 45}")
    for fn in field_names:
        m = field_match[fn]["match"]
        t = field_match[fn]["total"]
        rate = m / t * 100 if t > 0 else 0
        bar = "█" * int(rate / 5)
        lines.append(f"  {fn:<25} {m:>4} {t:>4} {rate:>6.1f}% {bar}")

    # 错误样本 top 5
    sorted_results = sorted(results, key=lambda x: x["accuracy"])
    lines.append(f"\n  【最差 5 个样本】")
    for r in sorted_results[:5]:
        wrong = [k for k, v in r["eval"]["fields"].items() if not v.get("match")]
        lines.append(f"    {r['record_id']}: {r['accuracy']*100:.0f}% | 错误: {', '.join(wrong)}")

    # 错误模式分析
    lines.append(f"\n  【错误模式】")
    # 左右混淆
    confusion = 0
    for r in results:
        gt = r["ground_truth"]
        ev = r["eval"]["fields"]
        llm_result = r.get("llm_result", {})
        if not llm_result:
            continue
        llm_right = normalize_follicles(llm_result.get("right_follicles", []))
        llm_left = normalize_follicles(llm_result.get("left_follicles", []))
        gt_right_total = len(gt.get("right_follicles", []))
        gt_left_total = len(gt.get("left_follicles", []))
        lr_total = follicle_total(llm_right)
        ll_total = follicle_total(llm_left)
        if lr_total > 0 and gt_right_total > 0 and lr_total >= gt_right_total + gt_left_total * 0.5:
            confusion += 1
        if ll_total > 0 and gt_left_total > 0 and ll_total >= gt_left_total + gt_right_total * 0.5:
            confusion += 1
    lines.append(f"    左右侧别混淆: {confusion} 次")

    # 完全遗漏
    empty = 0
    for r in results:
        gt = r["ground_truth"]
        llm_result = r.get("llm_result", {})
        if not llm_result:
            continue
        llm_right = normalize_follicles(llm_result.get("right_follicles", []))
        llm_left = normalize_follicles(llm_result.get("left_follicles", []))
        if follicle_total(llm_right) == 0 and len(gt.get("right_follicles", [])) > 0:
            empty += 1
        if follicle_total(llm_left) == 0 and len(gt.get("left_follicles", [])) > 0:
            empty += 1
    lines.append(f"    一侧完全遗漏: {empty} 次")

    lines.append(f"\n{sep}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 主循环
# ─────────────────────────────────────────────

def run_optimizer(db_path: str, prompt_name: str, max_rounds: int, sample: int = None):
    """运行优化循环"""
    print("=" * 70)
    print("  B 超语音测试平台 - 闭环提示词优化器")
    print("=" * 70)

    # 1. 加载 LLM 配置
    print("\n[1/3] 加载 LLM 配置...")
    llm_config = load_llm_config(db_path)
    print(f"  Provider: {llm_config['provider']}")
    print(f"  Model: {llm_config['model_name']}")
    print(f"  Endpoint: {llm_config['endpoint']}")
    llm = LLMClient(
        api_key=llm_config["api_key"],
        endpoint=llm_config["endpoint"],
        model_name=llm_config["model_name"],
    )

    # 2. 加载测试数据
    print(f"\n[2/3] 加载测试数据...")
    test_data = load_test_data(db_path, sample=sample)
    print(f"  测试样本: {len(test_data)} 条")

    # 3. 加载提示词
    print(f"\n[3/3] 加载提示词模板: {prompt_name}")
    current_prompt = load_prompt(db_path, prompt_name)
    print(f"  模板长度: {len(current_prompt)} 字符")

    # 历史准确率
    history = []

    # ── 优化循环 ──
    for round_num in range(1, max_rounds + 1):
        print(f"\n{'─' * 70}")
        print(f"  第 {round_num}/{max_rounds} 轮 | 模板: {prompt_name}")
        print(f"{'─' * 70}")

        # 调用 LLM
        print(f"\n  正在调用 LLM 处理 {len(test_data)} 条数据...")
        results = []
        for i, item in enumerate(test_data):
            sys.stdout.write(f"\r  进度: {i+1}/{len(test_data)}")
            sys.stdout.flush()
            llm_result, raw_output = llm.extract(item["transcript"], current_prompt)
            if llm_result is None:
                eval_result = {"fields": {}, "accuracy": 0.0, "correct": 0, "total": 10}
            else:
                eval_result = evaluate_result(llm_result, item["ground_truth"])
            results.append({
                "record_id": item["record_id"],
                "patient_id": item["patient_id"],
                "ground_truth": item["ground_truth"],
                "llm_result": llm_result,
                "raw_output": raw_output,
                "eval": eval_result,
                "accuracy": eval_result["accuracy"],
            })
        print()  # 换行

        # 生成报告
        report = generate_round_report(results, round_num, prompt_name)
        print(report)

        avg_acc = sum(r["accuracy"] for r in results) / len(results) * 100
        history.append({"round": round_num, "avg_accuracy": avg_acc, "prompt_name": prompt_name})

        # 历史对比
        if len(history) > 1:
            prev = history[-2]["avg_accuracy"]
            diff = avg_acc - prev
            sign = "+" if diff >= 0 else ""
            print(f"\n  与上轮对比: {sign}{diff:.1f}%")

        # 如果最后一轮，不暂停
        if round_num >= max_rounds:
            break

        # ── 暂停等待用户操作 ──
        print(f"\n{'─' * 70}")
        print("  请选择操作:")
        print("    [n] 进入下一轮（使用当前提示词）")
        print("    [e] 编辑提示词后进入下一轮")
        print("    [s] 保存当前提示词为新模板")
        print("    [v] 查看某个样本的详细对比")
        print("    [q] 退出")
        print(f"{'─' * 70}")

        while True:
            try:
                choice = input("\n  你的选择 > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "q"

            if choice == "q":
                print("\n  退出优化器。")
                _save_history(history)
                return

            elif choice == "n":
                break  # 进入下一轮

            elif choice == "e":
                new_prompt = _interactive_edit(current_prompt)
                if new_prompt and new_prompt != current_prompt:
                    current_prompt = new_prompt
                    prompt_name = f"{prompt_name}-edited-r{round_num}"
                    print(f"  提示词已更新，进入下一轮...")
                break

            elif choice == "s":
                _save_prompt_interactive(db_path, current_prompt, prompt_name)

            elif choice == "v":
                _view_sample_detail(results)

            else:
                print("  无效选择，请重新输入。")

    # 最终汇总
    print(f"\n{'=' * 70}")
    print("  优化历史汇总")
    print(f"{'=' * 70}")
    for h in history:
        print(f"  第 {h['round']} 轮 | {h['prompt_name']:<30} | 准确率: {h['avg_accuracy']:.1f}%")

    _save_history(history)
    print("\n  优化完成！")


def _interactive_edit(current_prompt: str) -> str:
    """交互式编辑提示词"""
    print("\n  当前提示词（前 500 字符）:")
    print(f"  {'─' * 50}")
    print(f"  {current_prompt[:500]}...")
    print(f"  {'─' * 50}")
    print("  输入新提示词（输入完毕后，单独一行输入 :END）:")

    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() == ":END":
            break
        lines.append(line)

    if lines:
        return "\n".join(lines)
    return current_prompt


def _view_sample_detail(results: list[dict]):
    """查看某个样本的详细对比"""
    print(f"\n  输入病历号查看详细信息（直接回车返回）:")
    try:
        rid = input("  病历号 > ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not rid:
        return
    for r in results:
        if r["record_id"] == rid:
            print(f"\n  --- {rid} (准确率 {r['accuracy']*100:.0f}%) ---")
            gt = r["ground_truth"]
            llm = r.get("llm_result") or {}
            print(f"  GT  右卵泡 ({len(gt.get('right_follicles', []))}个): {gt.get('right_follicles')}")
            print(f"  LLM 右卵泡: {llm.get('right_follicles', 'N/A')}")
            print(f"  GT  左卵泡 ({len(gt.get('left_follicles', []))}个): {gt.get('left_follicles')}")
            print(f"  LLM 左卵泡: {llm.get('left_follicles', 'N/A')}")
            print(f"  GT  内膜: {gt.get('endometrium_thickness')} / {gt.get('endometrium_type')}")
            print(f"  LLM 内膜: {llm.get('endometrium_thickness', 'N/A')} / {llm.get('endometrium_type', 'N/A')}")
            print(f"  GT  右卵巢: {gt.get('right_ovary_length')} x {gt.get('right_ovary_width')}")
            print(f"  LLM 右卵巢: {llm.get('right_ovary_length', 'N/A')} x {llm.get('right_ovary_width', 'N/A')}")
            print(f"  GT  左卵巢: {gt.get('left_ovary_length')} x {gt.get('left_ovary_width')}")
            print(f"  LLM 左卵巢: {llm.get('left_ovary_length', 'N/A')} x {llm.get('left_ovary_width', 'N/A')}")

            ev_fields = r["eval"]["fields"]
            wrong = [k for k, v in ev_fields.items() if not v.get("match")]
            right = [k for k, v in ev_fields.items() if v.get("match")]
            print(f"\n  正确字段: {', '.join(right)}")
            print(f"  错误字段: {', '.join(wrong)}")

            # 卵泡详细对比
            for side in ["right", "left"]:
                gt_fol = normalize_follicles(gt.get(f"{side}_follicles", []))
                llm_fol = normalize_follicles(llm.get(f"{side}_follicles", []))
                if gt_fol != llm_fol:
                    gt_sizes = [f"{f['size']}x{f['count']}" for f in gt_fol]
                    llm_sizes = [f"{f['size']}x{f['count']}" for f in llm_fol]
                    print(f"\n  {side}侧卵泡对比:")
                    print(f"    GT:  {', '.join(gt_sizes)}")
                    print(f"    LLM: {', '.join(llm_sizes)}")
            return
    print(f"  未找到病历号 {rid}")


def _save_prompt_interactive(db_path: str, prompt: str, default_name: str):
    """保存提示词到数据库（需要可写连接）"""
    print(f"\n  保存为新模板（输入名称，直接回车取消）:")
    try:
        name = input(f"  模板名 [{default_name}-new] > ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not name:
        name = f"{default_name}-new"

    # 写入 SQL 文件而非直接改库
    sql_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"save_prompt_{name}.sql")
    escaped = prompt.replace("'", "''")
    sql = f"INSERT OR REPLACE INTO prompt_templates (name, content, is_default, created_at, updated_at) VALUES ('{name}', '{escaped}', 0, datetime('now'), datetime('now'));\n"
    with open(sql_path, "w", encoding="utf-8") as f:
        f.write(sql)
    print(f"  SQL 已保存到: {sql_path}")
    print(f"  请手动执行该 SQL 以保存模板。")


def _save_history(history: list[dict]):
    """保存优化历史"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "optimizer_history.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"\n  历史记录已保存到: {path}")


# ─────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="B 超提示词闭环优化器")
    parser.add_argument("--template", "-t", type=str, default="DP-v4",
                        help="起始提示词模板名称 (默认: DP-v4)")
    parser.add_argument("--rounds", "-r", type=int, default=5,
                        help="最大迭代轮数 (默认: 5)")
    parser.add_argument("--sample", "-s", type=int, default=None,
                        help="抽样数量 (默认: 全部)")
    parser.add_argument("--db", type=str, default=None,
                        help="数据库路径")
    args = parser.parse_args()

    db_path = args.db or get_db_path()
    run_optimizer(db_path, args.template, args.rounds, args.sample)


if __name__ == "__main__":
    main()
