"""
CLI 执行器路由 — 实时日志 SSE 推送
"""
import asyncio
import json
import os
import shlex
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger

from app.config import settings

router = APIRouter()

# 命令白名单 — 允许执行的命令前缀
ALLOWED_COMMAND_PREFIXES = [
    "git ",
    "npm ",
    "pnpm ",
    "yarn ",
    "node ",
    "python ",
    "python3 ",
    "pip ",
    "pip3 ",
    "ls ",
    "pwd ",
    "cat ",
    "echo ",
    "mkdir ",
    "cd ",
    "rm ",
    "cp ",
    "mv ",
    "grep ",
    "find ",
    "wc ",
    "head ",
    "tail ",
    "kimi ",
    "codex ",
    "claude ",
    "gemini ",
]

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 300

# 任务存储
_tasks: dict[str, dict] = {}


def _is_command_allowed(command: str) -> bool:
    """检查命令是否在白名单中"""
    cmd = command.strip().lower()
    # 检查危险命令
    dangerous_patterns = ["sudo", "chmod", "chown", "mkfs", "dd", "format", "del", "rm -rf /"]
    for pattern in dangerous_patterns:
        if pattern in cmd:
            return False
    # 检查是否在白名单中
    for prefix in ALLOWED_COMMAND_PREFIXES:
        if cmd.startswith(prefix):
            return True
    return False


def _get_cwd(cwd: Optional[str]) -> str:
    """获取并验证工作目录"""
    if not cwd:
        return settings.PROJECT_DIR or os.getcwd()
    # 确保路径在 PROJECT_DIR 内
    project_dir = os.path.abspath(settings.PROJECT_DIR or os.getcwd())
    target_dir = os.path.abspath(cwd)
    if not target_dir.startswith(project_dir):
        raise ValueError(f"工作目录必须在项目目录内: {project_dir}")
    return target_dir


@router.post("/execute")
async def execute_command(data: dict):
    """启动 CLI 命令执行"""
    command = data.get("command", "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="命令不能为空")

    if not _is_command_allowed(command):
        raise HTTPException(status_code=403, detail="该命令不在白名单中，无权执行")

    try:
        cwd = _get_cwd(data.get("cwd"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    timeout = min(int(data.get("timeout", DEFAULT_TIMEOUT)), 3600)  # 最大 1 小时
    task_id = str(uuid.uuid4())[:8]

    env = os.environ.copy()
    env.update(data.get("env", {}))

    _tasks[task_id] = {
        "task_id": task_id,
        "command": command,
        "cwd": cwd,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }

    # 启动异步执行
    asyncio.create_task(_run_command(task_id, command, cwd, timeout, env))

    return {"task_id": task_id, "status": "started"}


async def _run_command(task_id: str, command: str, cwd: str, timeout: int, env: dict):
    """后台执行命令"""
    task = _tasks[task_id]
    task["status"] = "running"
    task["started_at"] = datetime.utcnow().isoformat()

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        task["pid"] = process.pid

        async def read_stream(stream, stream_type: str):
            while True:
                line = await stream.readline()
                if not line:
                    break
                yield {
                    "type": stream_type,
                    "content": line.decode("utf-8", errors="replace"),
                    "timestamp": datetime.utcnow().isoformat(),
                }

        # 合并 stdout 和 stderr
        async def merged_output():
            stdout_done = False
            stderr_done = False
            stdout_queue = asyncio.Queue()
            stderr_queue = asyncio.Queue()

            async def read_stdout():
                async for item in read_stream(process.stdout, "stdout"):
                    await stdout_queue.put(item)
                await stdout_queue.put(None)

            async def read_stderr():
                async for item in read_stream(process.stderr, "stderr"):
                    await stderr_queue.put(item)
                await stderr_queue.put(None)

            asyncio.create_task(read_stdout())
            asyncio.create_task(read_stderr())

            while not (stdout_done and stderr_done):
                if not stdout_done:
                    item = await stdout_queue.get()
                    if item is None:
                        stdout_done = True
                    else:
                        yield item
                if not stderr_done:
                    item = await stderr_queue.get()
                    if item is None:
                        stderr_done = True
                    else:
                        yield item

        # 等待进程完成或超时
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
            exit_code = process.returncode
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            exit_code = -1
            task["timeout"] = True

        task["status"] = "completed" if exit_code == 0 else "failed"
        task["exit_code"] = exit_code
        task["completed_at"] = datetime.utcnow().isoformat()

    except Exception as e:
        logger.error(f"CLI 执行失败 [{task_id}]: {e}")
        task["status"] = "failed"
        task["error"] = str(e)
        task["completed_at"] = datetime.utcnow().isoformat()


@router.get("/tasks/{task_id}/stream")
async def stream_logs(task_id: str):
    """SSE 流式推送执行日志"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = _tasks[task_id]

    async def event_generator():
        process = None
        # 重新创建进程用于流式输出（简化实现）
        try:
            cwd = task["cwd"]
            command = task["command"]

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            yield f"event: status\ndata: {json.dumps({'status': 'running', 'pid': process.pid}, ensure_ascii=False)}\n\n"

            async def read_stream(stream, stream_type: str):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    yield {
                        "type": stream_type,
                        "content": line.decode("utf-8", errors="replace"),
                        "timestamp": datetime.utcnow().isoformat(),
                    }

            stdout_done = False
            stderr_done = False
            stdout_queue = asyncio.Queue()
            stderr_queue = asyncio.Queue()

            async def read_stdout():
                async for item in read_stream(process.stdout, "stdout"):
                    await stdout_queue.put(item)
                await stdout_queue.put(None)

            async def read_stderr():
                async for item in read_stream(process.stderr, "stderr"):
                    await stderr_queue.put(item)
                await stderr_queue.put(None)

            asyncio.create_task(read_stdout())
            asyncio.create_task(read_stderr())

            while not (stdout_done and stderr_done):
                if not stdout_done:
                    item = await asyncio.wait_for(stdout_queue.get(), timeout=0.1)
                    if item is None:
                        stdout_done = True
                    else:
                        yield f"event: log\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
                if not stderr_done:
                    item = await asyncio.wait_for(stderr_queue.get(), timeout=0.1)
                    if item is None:
                        stderr_done = True
                    else:
                        yield f"event: log\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"

            # 等待进程完成
            try:
                await asyncio.wait_for(process.wait(), timeout=DEFAULT_TIMEOUT)
                exit_code = process.returncode
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                exit_code = -1
                yield f"event: log\ndata: {json.dumps({'type': 'stderr', 'content': '\n[执行超时，已自动终止]', 'timestamp': datetime.utcnow().isoformat()}, ensure_ascii=False)}\n\n"

            task["status"] = "completed" if exit_code == 0 else "failed"
            task["exit_code"] = exit_code

            yield f"event: status\ndata: {json.dumps({'status': task['status'], 'exit_code': exit_code}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"SSE 流式推送失败 [{task_id}]: {e}")
            yield f"event: status\ndata: {json.dumps({'status': 'failed', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _tasks[task_id]


@router.get("/tasks")
async def list_tasks():
    """获取任务列表"""
    return list(_tasks.values())


@router.post("/tasks/{task_id}/stop")
async def stop_task(task_id: str):
    """停止任务（通过 PID）"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    task = _tasks[task_id]
    pid = task.get("pid")
    if pid:
        try:
            os.kill(pid, 9)
            task["status"] = "stopped"
            return {"status": "stopped"}
        except ProcessLookupError:
            return {"status": "already_finished"}
    return {"status": "no_pid"}
