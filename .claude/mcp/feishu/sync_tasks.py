#!/usr/bin/env python3
"""
同步真实开发任务到飞书表格
先清空现有数据，再插入真实任务
"""
import json
import subprocess
import sys

APP_TOKEN = "SCcZb0mwYaaQvkscvGCcv98Knmc"
TABLE_ID = "tblMJVakuPzWGiFE"
SCRIPT = ".claude/mcp/feishu/feishu_table.py"


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout else {}


def delete_all():
    """删除所有现有记录"""
    data = run(["python", SCRIPT, "list", APP_TOKEN, TABLE_ID])
    items = data.get("data", {}).get("items", [])
    print(f"Deleting {len(items)} existing records...")
    for item in items:
        rid = item["record_id"]
        result = run(["python", SCRIPT, "delete", APP_TOKEN, TABLE_ID, rid])
        code = result.get("code", -1)
        if code != 0:
            print(f"  Failed to delete {rid}: {result}")
    print("Done deleting.")


def create_tasks(tasks):
    """批量创建任务"""
    print(f"Creating {len(tasks)} tasks...")
    for i, task in enumerate(tasks, 1):
        result = run(["python", SCRIPT, "create", APP_TOKEN, TABLE_ID, json.dumps(task, ensure_ascii=False)])
        code = result.get("code", -1)
        name = task.get("任务名", "?")
        if code == 0:
            print(f"  [{i}] OK {name}")
        else:
            print(f"  [{i}] FAIL {name}: {result}")
    print("Done creating.")


# Real development tasks
TASKS = [
    {
        "任务ID": "1",
        "任务名": "数据管理页面：患者列表+播放器+结果展示",
        "模块": "数据管理",
        "优先级": "P0",
        "状态": "已完成",
        "前后端": "全栈",
        "预估工时": 16,
        "验收标准": "患者按病历号分组展示，点击检查显示录音播放器（自动连播+拖拽）和B超结果表格，支持编辑结果"
    },
    {
        "任务ID": "2",
        "任务名": "模型配置页面CRUD",
        "模块": "模型配置",
        "优先级": "P1",
        "状态": "待开发",
        "前后端": "全栈",
        "预估工时": 8,
        "验收标准": "ASR/LLM模型的增删改查，内置本地FunASR默认配置，连通性测试"
    },
    {
        "任务ID": "3",
        "任务名": "单条测试：选患者→选ASR模型→SSE转写进度",
        "模块": "单条测试",
        "优先级": "P0",
        "状态": "待开发",
        "前后端": "全栈",
        "预估工时": 20,
        "验收标准": "选择病历号和ASR模型后开始测试，SSE实时推送每段转写进度，音频播放器自动切换到正在转写的段"
    },
    {
        "任务ID": "4",
        "任务名": "LLM后处理：结构化字段提取+总结文本",
        "模块": "单条测试",
        "优先级": "P1",
        "状态": "待开发",
        "前后端": "后端",
        "预估工时": 12,
        "验收标准": "ASR转写完成后调用LLM，输出右侧卵泡、左侧卵泡、内膜厚度/类型、卵巢尺寸、备注等结构化字段+总结文本"
    },
    {
        "任务ID": "5",
        "任务名": "结果评估页面：识别结果vs真实值对比",
        "模块": "结果评估",
        "优先级": "P1",
        "状态": "待开发",
        "前后端": "全栈",
        "预估工时": 14,
        "验收标准": "逐字段对比识别结果与ground truth，差异标红，字段级准确率统计，支持人工修正后重新评估"
    },
    {
        "任务ID": "6",
        "任务名": "测试历史页面：列表+筛选+详情",
        "模块": "测试历史",
        "优先级": "P2",
        "状态": "待开发",
        "前后端": "全栈",
        "预估工时": 8,
        "验收标准": "历史测试记录列表，按病历号筛选，点击查看转写全文、结构化结果、总结"
    },
    {
        "任务ID": "7",
        "任务名": "批量测试编排：多组变量组合批量执行",
        "模块": "批量测试",
        "优先级": "P2",
        "状态": "待开发",
        "前后端": "全栈",
        "预估工时": 16,
        "验收标准": "选择多个病历号×多个ASR模型×多个LLM模型批量执行，结果自动对比"
    },
]


if __name__ == "__main__":
    delete_all()
    print()
    create_tasks(TASKS)
    print()
    print("=" * 50)
    print("Sync complete!")
