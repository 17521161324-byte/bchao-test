#!/usr/bin/env python3
"""
把 markdown 内容同步到飞书文档中
"""
import json
import urllib.request
import urllib.error
import re

APP_ID = "cli_aacf6b10c5f95cb6"
APP_SECRET = "n5Cpxk05IgJoIplRD9DPTePl0uN1iR0C"
BASE_URL = "https://open.feishu.cn/open-apis"


def get_token():
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["tenant_access_token"]


def api(method, path, token, body=None):
    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = json.dumps(body, ensure_ascii=False).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode()}


def markdown_to_blocks(md_text):
    """简单 markdown 转飞书 block"""
    blocks = []
    lines = md_text.split('\n')
    in_code = False
    for line in lines:
        if line.strip().startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            blocks.append({
                "block_type": 2,
                "text": {"elements": [{"text_run": {"content": line}}]}
            })
            continue
        # Heading
        heading_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if heading_match:
            text = heading_match.group(2).strip()
            blocks.append({
                "block_type": 2,
                "text": {"elements": [{"text_run": {"content": text}}]}
            })
        elif line.strip() == "---":
            pass  # skip dividers
        elif line.strip():
            # Remove markdown bold/italic markers
            clean = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
            clean = re.sub(r'`(.*?)`', r'\1', clean)
            blocks.append({
                "block_type": 2,
                "text": {"elements": [{"text_run": {"content": clean}}]}
            })
    return blocks


def add_content_to_doc(token, doc_id, blocks):
    """向文档添加 block 内容（分批，每次最多 50 个）"""
    result = api("GET", f"/docx/v1/documents/{doc_id}/blocks", token)
    if result.get("code") != 0:
        return result

    items = result.get("data", {}).get("items", [])
    if not items:
        return {"error": "no root block found"}

    root_block_id = items[0].get("block_id", "")

    # Batch in chunks of 50
    total = len(blocks)
    batch_size = 50
    for i in range(0, total, batch_size):
        batch = blocks[i:i+batch_size]
        body = {"children": batch}
        result = api("POST", f"/docx/v1/documents/{doc_id}/blocks/{root_block_id}/children", token, body)
        if result.get("code") != 0:
            return result
        print(f"  Batch {i//batch_size + 1}: {len(batch)} blocks OK")

    return {"code": 0, "total": total}


if __name__ == "__main__":
    token = get_token()

    for doc_file, doc_id, title in [
        ("docs/技术实现方案.md", "P0X7dWyESoE1mfxRs9QcTN0Cnbg", "技术实现方案"),
        ("docs/产品功能规划.md", "MoUfdsmfFoQAvtxvWEmc5DmPnib", "产品功能规划"),
    ]:
        with open(doc_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        blocks = markdown_to_blocks(md_content)
        print(f"\nWriting '{title}' ({len(blocks)} blocks)...")

        result = add_content_to_doc(token, doc_id, blocks)
        if result.get("code") == 0:
            print(f"  OK - content written")
        else:
            print(f"  Result: {json.dumps(result, ensure_ascii=False)[:200]}")
