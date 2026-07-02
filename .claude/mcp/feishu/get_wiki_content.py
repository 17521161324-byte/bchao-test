#!/usr/bin/env python3
"""
获取 wiki 页面内容，从中提取嵌入的云文档 ID
"""
import json, urllib.request, urllib.error

APP_ID = "cli_aacf6b10c5f95cb6"
APP_SECRET = "n5Cpxk05IgJoIplRD9DPTePl0uN1iR0C"
BASE_URL = "https://open.feishu.cn/open-apis"

def get_token():
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["tenant_access_token"]

def api_get(path, token):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode()}

token = get_token()

# Try to get wiki page as a docx document
wiki_token = "GYFewIaSsiZOpTkuz0mcza1bnCd"

# Get document blocks (wiki is also a docx)
print("Getting wiki page blocks...")
result = api_get(f"/docx/v1/documents/{wiki_token}/blocks", token)
print(json.dumps(result, ensure_ascii=False)[:1000])

# Also try raw content
print("\n\nGetting raw content...")
result = api_get(f"/docx/v1/documents/{wiki_token}/raw_content", token)
print(json.dumps(result, ensure_ascii=False)[:3000])
