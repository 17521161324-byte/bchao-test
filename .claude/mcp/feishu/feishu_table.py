#!/usr/bin/env python3
"""
飞书多维表格操作脚本
用法:
  python feishu_table.py list <app_token> <table_id>
  python feishu_table.py create <app_token> <table_id> '<json_fields>'
  python feishu_table.py update <app_token> <table_id> <record_id> '<json_fields>'
  python feishu_table.py delete <app_token> <table_id> <record_id>
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
    result = json.loads(resp.read())
    return result["tenant_access_token"]


def api_request(method, path, token, body=None):
    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        return {"error": e.code, "message": error_body}


def list_records(app_token, table_id):
    token = get_token()
    path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records?page_size=100"
    result = api_request("GET", path, token)
    return result


def create_record(app_token, table_id, fields):
    token = get_token()
    path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    body = {"fields": fields}
    return api_request("POST", path, token, body)


def update_record(app_token, table_id, record_id, fields):
    token = get_token()
    path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
    body = {"fields": fields}
    return api_request("PUT", path, token, body)


def delete_record(app_token, table_id, record_id):
    token = get_token()
    path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
    return api_request("DELETE", path, token)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    app_token = sys.argv[2]
    table_id = sys.argv[3]

    if action == "list":
        result = list_records(app_token, table_id)
    elif action == "create":
        if len(sys.argv) < 5:
            print("需要字段 JSON")
            sys.exit(1)
        fields = json.loads(sys.argv[4])
        result = create_record(app_token, table_id, fields)
    elif action == "update":
        if len(sys.argv) < 6:
            print("需要 record_id 和字段 JSON")
            sys.exit(1)
        record_id = sys.argv[4]
        fields = json.loads(sys.argv[5])
        result = update_record(app_token, table_id, record_id, fields)
    elif action == "delete":
        if len(sys.argv) < 5:
            print("需要 record_id")
            sys.exit(1)
        record_id = sys.argv[4]
        result = delete_record(app_token, table_id, record_id)
    else:
        print(f"未知操作: {action}")
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
