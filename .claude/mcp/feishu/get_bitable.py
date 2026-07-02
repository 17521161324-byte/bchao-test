#!/usr/bin/env python3
"""
从飞书wiki链接获取bitable信息
"""
import sys
import json
import urllib.request
import urllib.error

APP_ID = "cli_aacf6b10c5f95cb6"
APP_SECRET = "n5Cpxk05IgJoIplRD9DPTePl0uN1iR0C"
BASE_URL = "https://open.feishu.cn/open-apis"


def get_token():
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["tenant_access_token"]


def api_get(path, token):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode()}


def get_wiki_node(token, wiki_token):
    return api_get(f"/wiki/v2/spaces/get_node?token={wiki_token}", token)


def list_bitable_tables(token, app_token):
    return api_get(f"/bitable/v1/apps/{app_token}/tables", token)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_bitable.py <wiki_token_or_bitable_url>")
        sys.exit(1)

    arg = sys.argv[1]
    token = get_token()

    # If it's a wiki URL, extract token
    if "wiki/" in arg:
        wiki_token = arg.split("wiki/")[1].split("?")[0].split("#")[0]
        print(f"Wiki token: {wiki_token}")
        node = get_wiki_node(token, wiki_token)
        print(json.dumps(node, ensure_ascii=False, indent=2))
    elif arg.startswith("bitable/") or arg.startswith("app/"):
        # It's a bitable app token, list tables
        app_token = arg.split("/")[-1].split("?")[0]
        print(f"Bitable app token: {app_token}")
        tables = list_bitable_tables(token, app_token)
        print(json.dumps(tables, ensure_ascii=False, indent=2))
