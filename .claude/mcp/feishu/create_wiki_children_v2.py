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

# First get info about the parent wiki page
wiki_token = "GYFewIaSsiZOpTkuz0mcza1bnCd"
result = api("GET", f"/wiki/v2/spaces/get_node?token={wiki_token}", token)
print("Get node:", json.dumps(result, ensure_ascii=False)[:500])

if result.get("code") == 0:
    space_id = result.get("data", {}).get("node", {}).get("space_id", "")
    print(f"\nSpace ID: {space_id}")

    # Create children under that node
    for title in ["技术实现方案", "产品功能规划"]:
        body = {
            "parent_node_token": wiki_token,
            "title": title,
            "obj_type": "docx"
        }
        result = api("POST", f"/wiki/v2/spaces/{space_id}/nodes", token, body)
        print(f"\n{title}: code={result.get('code')}")
        if result.get("code") == 0:
            node = result.get("data", {}).get("node", {})
            print(f"  token: {node.get('token', '')}")
        else:
            print(f"  Error: {json.dumps(result, ensure_ascii=False)[:300]}")
