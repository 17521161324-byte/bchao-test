#!/usr/bin/env python3
"""
将本地 markdown 文档同步到飞书 wiki 文档
"""
import json
import urllib.request
import urllib.error
import re
import sys

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


def get_root_wiki(token):
    """获取用户知识库根目录"""
    return api("GET", "/wiki/v2/spaces/node?token=", token)


def create_wiki_node(token, parent_token, title, obj_type="docx"):
    """创建 wiki 页面"""
    body = {
        "parent_node_token": parent_token,
        "title": title,
        "obj_type": obj_type,
    }
    return api("POST", "/wiki/v2/spaces/nodes", token, body)


def create_document(token, title, folder_token=""):
    """创建文档"""
    body = {"title": title}
    if folder_token:
        body["folder_token"] = folder_token
    return api("POST", "/docx/v1/documents", token, body)


def markdown_to_blocks(md_text):
    """简单 markdown 转为飞书 block 格式（仅支持标题和段落）"""
    blocks = []
    lines = md_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        # Heading
        heading_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            blocks.append({
                "block_type": 2,
                "text": {"elements": [{"text_run": {"content": text}}]}
            })
            # Store heading level in style
            blocks[-1]["text"]["elements"][0]["text_run"]["text_element_style"] = {"bold": True}
        elif line.strip() == "---":
            # Divider
            blocks.append({"block_type": 23})  # divider
        elif line.strip() and not line.strip().startswith('```'):
            blocks.append({
                "block_type": 2,
                "text": {"elements": [{"text_run": {"content": line}}]}
            })
        i += 1
    return blocks


if __name__ == "__main__":
    token = get_token()

    # Step 1: Get root wiki
    print("[1] Getting root wiki...")
    root = get_root_wiki(token)
    print(f"  Root: {json.dumps(root, ensure_ascii=False)[:200]}")

    # If no space found, try getting user's space list
    if root.get("code") != 0:
        # Try to get spaces
        spaces = api("GET", "/wiki/v2/spaces", token)
        print(f"  Spaces: {json.dumps(spaces, ensure_ascii=False)[:200]}")

    # For now, create directly under user's default space
    # The parent should be the wiki page where the bitable lives
    parent_token = "GYFewIaSsiZOpTkuz0mcza1bnCd"  # user's wiki page

    # Step 2: Create parent page
    print("\n[2] Creating parent page...")
    parent = create_wiki_node(token, "", "B 超语音测试平台", "docx")
    print(f"  Parent: {json.dumps(parent, ensure_ascii=False)[:200]}")

    if parent.get("code") != 0:
        print("  FAILED - trying to use token from response as document_id")
        # The wiki node might also be a usable document token
        doc_token = parent.get("data", {}).get("node", {}).get("obj_token", "")
        print(f"  Obj token: {doc_token}")
    else:
        doc_token = parent.get("data", {}).get("node", {}).get("token", "")

    # Step 3: Create documents with content
    print("\n[3] Creating documents with content...")
    for doc_file, title in [("docs/技术实现方案.md", "技术实现方案"), ("docs/产品功能规划.md", "产品功能规划")]:
        with open(doc_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # Create document
        result = create_document(token, title)
        print(f"\n  Creating '{title}': {json.dumps(result, ensure_ascii=False)[:200]}")

        if result.get("code") == 0:
            doc_id = result.get("data", {}).get("document", {}).get("document_id", "")
            print(f"  Document ID: {doc_id}")
            # Note: Adding content requires additional API calls
            print(f"  (Content sync requires document update API - skipped for now)")
        else:
            print(f"  FAILED: {result}")
