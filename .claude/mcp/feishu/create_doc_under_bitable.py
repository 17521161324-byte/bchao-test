#!/usr/bin/env python3
import json, urllib.request, urllib.error

APP_ID = "cli_aacf6b10c5f95cb6"
APP_SECRET = "n5Cpxk05IgJoIplRD9DPTePl0uN1iR0C"
BASE_URL = "https://open.feishu.cn/open-apis"

def get_token():
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["tenant_access_token"]

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

token = get_token()
parent = "GYFewIaSsiZOpTkuz0mcza1bnCd"
space = "7657767212563926239"

# Create doc with folder_token = parent
title = "产品功能规划"
body = {"title": title, "folder_token": parent}
r = api("POST", "/docx/v1/documents", token, body)
print(f"Create '{title}': {json.dumps(r, ensure_ascii=False)[:300]}")

if r.get("code") == 0:
    did = r.get("data", {}).get("document", {}).get("document_id", "")
    print(f"  doc id: {did}")
