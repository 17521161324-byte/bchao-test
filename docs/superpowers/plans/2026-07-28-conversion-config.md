# ASR Conversion Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a visual configuration workbench for ASR conversion lexicon, rules, versions, and preview testing.

**Architecture:** Store conversion configuration in backend database versions. The conversion engine accepts runtime lexicon rules while existing system rules remain available. The frontend exposes a new `转化配置` page for version lifecycle, lexicon/rule editing, and text preview.

**Tech Stack:** FastAPI, SQLAlchemy async, SQLite manual migration, Pydantic v2, Vue 3, TypeScript, ant-design-vue.

## Global Constraints

- Preserve existing ASR conversion evaluation data and APIs.
- Published versions are immutable; users clone or create drafts before editing.
- The first deliverable must be usable without external services.
- Use the existing manual `init_db()` migration pattern.
- Add tests before production code.

---

### Task 1: Backend Config Model And API

**Files:**
- Create: `backend/app/models/conversion_config.py`
- Create: `backend/app/schemas/conversion_config.py`
- Create: `backend/app/routers/conversion_config.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/database.py`
- Test: `backend/tests/test_conversion_config.py`

**Interfaces:**
- Produces API prefix `/api/conversion-config`
- Produces `ensure_default_version(db) -> ConversionConfigVersion`
- Produces version, lexicon, rule CRUD and preview endpoints.

- [x] Write failing API tests for init defaults, clone, publish immutability, and preview.
- [x] Implement SQLAlchemy models and schema objects.
- [x] Implement router functions and idempotent default import.
- [x] Register route and model imports.
- [x] Run focused backend tests.

### Task 2: Runtime Lexicon In Engine

**Files:**
- Modify: `backend/app/services/conversion_engine/__init__.py`
- Modify: `backend/app/services/conversion_engine/medical_term_correct.py`
- Test: `backend/tests/test_conversion_config.py`

**Interfaces:**
- `run_conversion(..., extra_confusion_rules: list[dict] | None = None)`
- `apply_medical_term_correct(..., extra_rules: list[ConfusionRule] | None = None)`

- [x] Write failing test proving preview uses a draft lexicon entry not in hardcoded rules.
- [x] Add optional custom lexicon rules.
- [x] Run focused backend tests.

### Task 3: Frontend Config Workbench

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/components/Layout/index.vue`
- Create: `frontend/src/pages/ConversionConfig/index.vue`

**Interfaces:**
- New route `/conversion-config`
- New API client `conversionConfigApi`

- [x] Add client methods.
- [x] Add menu and route.
- [x] Build page with version selector/actions, lexicon table, rule table, preview tab.
- [x] Run frontend build.

### Task 4: Verification

**Files:**
- No new files.

- [x] Run focused backend tests.
- [x] Run frontend build.
- [x] Report remaining unrelated known test failures only if full suite is run.
