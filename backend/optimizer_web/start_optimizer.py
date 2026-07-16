#!/usr/bin/env python3
"""
B超提示词优化器 - Web 启动脚本
运行后自动打开浏览器
"""
import http.server
import json
import subprocess
import tempfile
import sqlite3
import os
import sys
import webbrowser
import threading
from functools import partial

# ── 数据库路径 ──
def get_db_path():
    base = os.path.dirname(os.path.abspath(__file__))
    # 本地开发
    local = os.path.join(base, "data", "bchao.db")
    if os.path.exists(local):
        return local
    # SMB
    smb = "/Volumes/bchao-test/backend/data/bchao.db"
    if os.path.exists(smb):
        return smb
    print("找不到数据库！")
    sys.exit(1)

# ── 读取数据库 ──
def load_config():
    db_path = get_db_path()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # LLM 配置
    c.execute("SELECT provider, model_name, endpoint, api_key FROM model_configs WHERE is_default=1 AND provider != 'local' LIMIT 1")
    row = c.fetchone()
    config = {"provider": row[0], "model_name": row[1], "endpoint": row[2], "api_key": row[3]} if row else {}

    # 提示词模板
    c.execute("SELECT name, content FROM prompt_templates ORDER BY is_default DESC, name")
    templates = {row[0]: row[1] for row in c.fetchall()}
    config["templates"] = templates

    # ASR 模型列表
    c.execute("""
        SELECT DISTINCT provider, asr_model_name, asr_model_id
        FROM patient_asr_results
        WHERE status = 'success' AND full_transcript IS NOT NULL
        ORDER BY provider, asr_model_name
    """)
    asr_models = []
    for row in c.fetchall():
        asr_models.append({"provider": row[0], "name": row[1], "id": row[2]})
    config["asr_models"] = asr_models

    # 测试数据（带 ASR 模型信息，包含所有 ASR 结果）
    c.execute("""
        SELECT p.id, p.record_id, a.full_transcript,
               a.provider, a.asr_model_name,
               b.right_follicles, b.left_follicles,
               b.right_ovary_length, b.right_ovary_width,
               b.left_ovary_length, b.left_ovary_width,
               b.endometrium_thickness, b.endometrium_type,
               b.right_follicle_total, b.left_follicle_total
        FROM patient_records p
        JOIN patient_asr_results a ON a.patient_id = p.id
        JOIN b_ultra_results b ON b.patient_id = p.id
        WHERE a.status = 'success' AND a.full_transcript IS NOT NULL
        ORDER BY a.provider, a.asr_model_name, p.record_id
    """)
    test_data = []
    for row in c.fetchall():
        test_data.append({
            "patient_id": row[0],
            "record_id": row[1],
            "transcript": row[2],
            "asr_provider": row[3],
            "asr_model_name": row[4],
            "ground_truth": {
                "right_follicles": json.loads(row[5]) if row[5] else [],
                "left_follicles": json.loads(row[6]) if row[6] else [],
                "right_ovary_length": row[7],
                "right_ovary_width": row[8],
                "left_ovary_length": row[9],
                "left_ovary_width": row[10],
                "endometrium_thickness": row[11],
                "endometrium_type": row[12],
                "right_follicle_total": row[13],
                "left_follicle_total": row[14],
            }
        })
    config["test_data"] = test_data

    # 按患者分组的 ASR 数据（每个模型只保留最新一条）
    c.execute("""
        SELECT p.id, p.record_id,
               a.id as asr_id, a.provider, a.asr_model_name, a.full_transcript,
               a.created_at,
               b.right_follicles, b.left_follicles,
               b.right_ovary_length, b.right_ovary_width,
               b.left_ovary_length, b.left_ovary_width,
               b.endometrium_thickness, b.endometrium_type,
               b.right_follicle_total, b.left_follicle_total
        FROM patient_records p
        JOIN patient_asr_results a ON a.patient_id = p.id
        JOIN b_ultra_results b ON b.patient_id = p.id
        WHERE a.status = 'success' AND a.full_transcript IS NOT NULL
        ORDER BY p.record_id, a.asr_model_name, a.created_at DESC
    """)
    # 按患者+模型去重，只保留最新
    patient_groups = {}
    seen = set()
    for row in c.fetchall():
        rid = row[1]
        model = row[4]  # asr_model_name
        dedup_key = f"{rid}|{model}"
        if dedup_key in seen:
            continue  # 同患者同模型只保留第一条（最新的）
        seen.add(dedup_key)
        if rid not in patient_groups:
            patient_groups[rid] = {"record_id": rid, "asr_results": []}
        patient_groups[rid]["asr_results"].append({
            "asr_id": row[2], "provider": row[3], "asr_model_name": model,
            "transcript": row[5],
            "ground_truth": {
                "right_follicles": json.loads(row[7]) if row[7] else [],
                "left_follicles": json.loads(row[8]) if row[8] else [],
                "right_ovary_length": row[9], "right_ovary_width": row[10],
                "left_ovary_length": row[11], "left_ovary_width": row[12],
                "endometrium_thickness": row[13], "endometrium_type": row[14],
                "right_follicle_total": row[15], "left_follicle_total": row[16],
            }
        })
    # 只保留有2个及以上ASR结果的患者（才能做对比）
    config["patient_groups"] = {k:v for k,v in patient_groups.items() if len(v["asr_results"]) >= 2}
    conn.close()
    return config

# ── HTTP 服务 ──
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, config_data, *args, **kwargs):
        self.config_data = config_data
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == '/api/config':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(self.config_data, ensure_ascii=False).encode())
        elif self.path == '/api/patients':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(self.config_data.get('patient_groups', {}), ensure_ascii=False).encode())
        elif self.path == '/' or self.path == '/index.html':
            html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
            with open(html_path, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(f.read())
        else:
            self.send_error(404)


    def do_POST(self):
        if self.path == '/api/llm':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body)
                endpoint = payload.pop('_endpoint', 'https://api.deepseek.com/v1')
                api_key = payload.pop('_api_key', '')
                url = endpoint.rstrip('/') + '/chat/completions'
                # 用 curl 转发（绕过 Python 网络限制）
                import subprocess, tempfile
                body_file = tempfile.mktemp(suffix='.json')
                with open(body_file, 'w') as bf:
                    json.dump(payload, bf)
                cmd = [
                    'curl', '-s', '--max-time', '120',
                    '-X', 'POST', url,
                    '-H', 'Content-Type: application/json',
                ]
                if api_key:
                    cmd += ['-H', f'Authorization: Bearer {api_key}']
                cmd += ['-d', f'@{body_file}']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=130)
                os.unlink(body_file)
                if result.returncode != 0:
                    raise Exception(f'curl error: {result.stderr}')
                data = json.loads(result.stdout)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # 静默日志

def main():
    port = 8099
    print("=" * 50)
    print("  B超提示词优化器 - Web 版")
    print("=" * 50)
    print(f"\n  正在加载数据...")

    config = load_config()
    print(f"  模板: {len(config.get('templates', {}))} 个")
    print(f"  测试数据: {len(config.get('test_data', []))} 条")

    handler = partial(Handler, config)
    server = http.server.HTTPServer(("127.0.0.1", port), handler)

    url = f"http://127.0.0.1:{port}"
    print(f"\n  服务已启动: {url}")
    print(f"  正在打开浏览器...")
    print(f"  按 Ctrl+C 停止\n")

    # 延迟打开浏览器
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
        server.shutdown()

if __name__ == "__main__":
    main()
