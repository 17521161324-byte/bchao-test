# ASR Conversion Batch Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ASR 转化评估收敛为可追踪成功和失败检查记录的批次工作台。

**Architecture:** 保留现有单条记录 API 作为内部兼容层，在 `AsrConversionBatch` 与 `AsrConversionRecord` 上补充批次统计和记录状态。前端首页只操作批次，详情页按批次记录切换并复用现有文本分段与专家标注能力。

**Tech Stack:** FastAPI、SQLAlchemy async、SQLite、Pydantic v2、Vue 3、TypeScript、ant-design-vue。

## Global Constraints

- 不删除或覆盖现有检查记录、ASR 结果、专家标准 ASR 和优化评估数据。
- SQLite 新增字段必须通过 `database.py:init_db()` 的 `_ensure_column()` 兼容。
- 提示词模板不在本次范围内。
- 前端不提供单条创建入口。

---

### Task 1: 批次失败记录与统计

**Files:**
- Modify: `backend/tests/test_conversion_eval.py`
- Modify: `backend/app/models/conversion_eval.py`
- Modify: `backend/app/schemas/conversion_eval.py`
- Modify: `backend/app/routers/conversion_eval.py`
- Modify: `backend/app/database.py`

**Interfaces:**
- Produces: `AsrConversionRecord.status`, `AsrConversionRecord.error_message`
- Produces: `AsrConversionBatch.success_count`, `AsrConversionBatch.failed_count`

- [ ] 写入无 ASR 检查记录仍生成失败明细的测试。
- [ ] 运行测试并确认因状态字段缺失失败。
- [ ] 增加模型、schema 和 SQLite 兼容字段。
- [ ] 批次创建时为成功记录写入 `ready`，为无 ASR 记录写入 `failed`。
- [ ] 运行批次测试并确认通过。

### Task 2: 批次前端交互收敛

**Files:**
- Modify: `frontend/src/pages/ConversionEval/index.vue`
- Modify: `frontend/src/pages/ConversionEval/BatchDetail.vue`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: 批次和记录的成功/失败统计及状态字段。

- [ ] 新建批次允许选择缺少 ASR 的检查记录。
- [ ] 批次列表显示成功数、失败数和已审校数。
- [ ] 批次详情左侧失败记录显示状态提示。
- [ ] 失败记录详情禁用转化、判定、指标操作并显示原因。
- [ ] 删除文案与后端级联删除行为保持一致。

### Task 3: 回归验证

**Files:**
- Test: `backend/tests/test_conversion_eval.py`
- Test: `frontend/src/pages/ConversionEval/`

- [ ] 运行 `PYTHONPATH=. .venv/bin/pytest tests/test_conversion_eval.py tests/test_conversion_engine.py -q`。
- [ ] 运行 `npm run build`。
- [ ] 检查 `git diff --check`。
