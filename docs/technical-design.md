# 提取规则梳理与转化 - 技术设计

## 当前实现和代码入口

### 后端入口

- 应用注册：`backend/app/main.py` 已注册 `/api/conversion-config`、`/api/text-validation`、`/api/conversion-eval`。
- 数据库初始化：`backend/app/database.py:init_db()` 使用 `Base.metadata.create_all` + `_ensure_column()` 手动补字段。
- 规则配置模型：`backend/app/models/conversion_config.py`
  - `ConversionConfigVersion`：规则版本，支持 draft/testing/published/rolled_back。
  - `ConversionLexiconEntry`：词库条目，当前是一条错词/近似词对应一个标准词。
  - `ConversionRuleEntry`：规则条目，含 `rule_type`、`condition_config`、`system_handler`、`editable`。
- 配置接口：`backend/app/routers/conversion_config.py`
  - 版本、词库、规则 CRUD。
  - `/preview` 调用 `run_conversion()`。
- 规则服务：`backend/app/services/conversion_config.py`
  - `SYSTEM_RULES` 初始化系统规则。
  - `ensure_default_version()` 从硬编码 `CONFUSION_RULES` 导入默认词库。
  - `load_enabled_lexicon_rules()` 给转化引擎提供运行时词库。
- 转化引擎：`backend/app/services/conversion_engine/__init__.py`
  - 当前链路：基础清洗 → 数字标准化 → 医学术语纠错 → 业务片段转化 → 字段解析 → 风险拦截。
- 业务片段定位：`business_segment_locator.py`
  - 已有 `MEDICAL_TERMS`、`LOCATOR_WORDS`、`EXPLICIT_SIDE_LOCATORS`、数值匹配和 source span。
- 字段解析：`field_parser.py`
  - 当前基于状态机解析内膜、卵巢大小、左右卵泡、备注/操作/医嘱。
- 风险拦截：`risk_intercept.py`
  - 已有 R001-R015 规则定义，部分规则仅有基础实现。
- 文本验证：`backend/app/routers/text_validation.py`
  - 支持 LLM 完整纠错或人工覆盖文本，再运行规则提取并与 ground truth 对比。

### 前端入口

- 路由：`frontend/src/router/index.ts`
  - `/conversion-config`：规则配置页。
  - `/text-validation`：文本验证页。
  - `/conversion-eval`：ASR 转化评估页。
- API：`frontend/src/api/client.ts`
  - `conversionConfigApi` 覆盖版本/词库/规则/预览。
  - `textValidationApi` 覆盖验证运行和纠错模板。
- 页面：
  - `frontend/src/pages/ConversionConfig/index.vue`：配置版本、词库、规则、版本测试。
  - `frontend/src/pages/TextValidation/index.vue`：ASR 方案 → LLM 纠错 → 规则提取 → 真实结果对比。

## 首轮开发已完成（工作树未提交）

以下能力已在工作树中实现并通过目标测试（71 passed），本轮无需重复开发：

- 词库管理：`ConversionLexiconEntry` CRUD + 前端按 `standard_text` 分组展示"标准词 + 多近似词" + 一键新增近似词（预填标准词）+ CSV 导出。
- 文本切换：`business_segment_locator.py` 侧别锚点（`MEDICAL_TERMS`、`EXPLICIT_SIDE_LOCATORS`）、换边词（`LOCATOR_WORDS`）、缺失定位词侧别继承窗口（240 字符）、强边界停止（`_before_strong_boundary`：句号/感叹号/问号/换行），输出四类 `segments`（medical_term/locator/medical_data/noise）。
- 数据提取：`field_parser.py` F001-F014（内膜厚度/类型、左右卵巢大小、左右卵泡、超声发现、操作、医嘱、source_spans）；卵泡 2-100mm 保留、>40mm 加 warning（配合 R016）；卵巢 10-100mm 范围检查。
- 警示规则：`risk_intercept.py` R001-R017；R005 左右侧冲突/缺失实逻辑（REVIEW）；R016 卵泡 >40mm（REVIEW 不阻断）；R017 卵巢任一单维 <10mm（REVIEW 不阻断）。
- 版本管理：`ensure_default_version()` 从 `CONFUSION_RULES` 导入默认版本；clone / publish / rollback；版本状态不能绕过发布接口直接写入；系统规则不可编辑。
- 文本验证：`TextValidationRun` 模型 + `/api/text-validation/runs`（LLM 纠错或人工覆盖 → 加载所选规则版本启用词库 → `run_conversion()` → `evaluate_result()` 与 ground truth 对比）；持久化 `conversions/segments/warnings/risk_items`，`_ensure_column()` + NULL→[] 回填兼容历史。
- 前端：`ConversionConfig/index.vue`（版本测试新增警示项、字段解析、业务片段三区块 + 三态风险标签）；`TextValidation/index.vue`（命中规则、业务片段、规则警示、准确率）。
- 回归：目标测试 `tests/test_conversion_config.py / test_business_segment_locator.py / test_conversion_engine.py / test_text_validation.py / test_risk_intercept.py` 71 passed；前端 `npm run build` 成功。

## 本轮实施范围（缺口补全）

以用户确认的界面文字布局为基准，对当前实现逐区块核对（详见任务计划 v3「界面布局逐区块核对」表）：规则配置页顶部工具栏、版本摘要、Tab 栏、Tab1 词库管理、Tab3 版本测试及文本验证页各区块均与确认布局一致；**差异集中在 Tab2 规则管理**（当前为平铺表格、仅 5 条系统规则占位，未按分组展示）。本轮修改点如下：

### 1. R018 取消（需求修正，不实现）

原"医疗名称/换边词等非医疗数据类错误仍生成警示"口径已由用户修正为：**医疗名词识别错误、换边词错误不生成警示**，警示仅由数字等数据异常触发（feature-spec「警示口径修正」变更记录）。R018 **取消，不实现**；当前实现已满足该口径（`medical_term_correct.py` 名词纠错不产生 `risk_items`）。

### 2. 规则管理 tab 分组展示（tab 样式改造）——核心

需求确认"规则管理 tab 内按**文本切换 / 数据提取 / 警示规则**分组展示，系统内置规则只读，参数化规则可编辑"。实施：

- **后端内置清单元数据**：`backend/app/services/conversion_config.py` 新增 `BUILTIN_RULES_META` + `get_builtin_rules()`：
  - `text_switch`：SW001 左右定位词、SW002 换边词切换、SW003 缺失定位词侧别继承（对应 `business_segment_locator.py` 实现）；
  - `field_extract`：F001-F014（名称/说明/范围校验，范围引用 `field_parser.RANGE_CHECKS`）；
  - `risk`：直接序列化 `risk_intercept.RISK_RULES`（R001-R017），与引擎天然同步。
- **新增只读接口**：`GET /api/conversion-config/builtin-rules`（`backend/app/routers/conversion_config.py`），返回三组元数据；`backend/app/schemas/conversion_config.py` 新增 `BuiltinRulesOut`。
- **前端分组渲染**（`frontend/src/pages/ConversionConfig/index.vue`）：规则管理 tab 由平铺表格改为**分组标题 + 分组内表格**：
  - **文本切换规则**（内置只读）、**数据提取规则**（内置 F001-F014 + DB F001）、**警示规则**（内置 R001-R017 + DB R001）、**引擎基础步骤**（DB B001/N001/M001 只读）、**参数化规则**（DB `editable=1`，保留新增/编辑/删除）；
  - 系统内置规则只读（无编辑/删除按钮或禁用），参数化规则保留操作；搜索框对各分组条目过滤。
- `frontend/src/api/client.ts` 新增 `conversionConfigApi.listBuiltinRules()`。

### 3. 现有 5 条系统规则归类

DB 中已入库的 B001/N001/M001/F001/R001（`editable=0`）按 `rule_type` 归入对应分组展示（F001→数据提取、R001→警示规则、B001/N001/M001→引擎基础步骤），不删除、不改变其引擎行为。

### 4. 警示口径验证（名词纠错不产生警示）

补充测试覆盖已确认口径：断言"肉卵巢→右卵巢"等名词纠错、换边词纠错后 `risk_items` 不含名词类警示（`tests/test_conversion_engine.py::TestWarningScope` 已实现，3 用例）。

### 5. UI 交互调整（2026-08-05，用户提出，已实施）

- **词库弹窗重构**：新增/编辑弹窗由"单条多字段"改为**标准词 + 业务场景 + 近似词动态列表**（一次可添加多个近似词，每条含错误词/动作/风险/启用开关，`+ 添加近似词` 动态增行）；编辑模式按标准词整组加载（标准词锁定防错乱），保存时批量更新/创建/删除（复用既有 lexicon CRUD 接口，后端零改动）；`rule_code` 自动生成 `L{ts}{i}`；移除规则编码/ASR模型/置信度/匹配方式/优先级/上下文/备注字段（DB 原值保留，仅界面不再编辑）。
- **规则管理二级 tab**：规则管理 tab 内由"分组标题列表"改为**五个二级 tab**——文本切换规则 / 数据提取规则 / 警示规则 / 引擎基础步骤 / 参数化规则（ant 嵌套 Tabs），各 tab 独立表格；内置组只读、参数化组可编辑；搜索对各 tab 条目过滤。
- 验证：前端构建（vue-tsc + vite）通过；浏览器实际验证批量添加/整组编辑/二级 tab 均正常；后端目标测试 75 passed 无回归。

### 6. 2026-08-06 新增需求（用户提出，已实施）

- **词库表格列精简**：`frontend/src/pages/ConversionConfig/index.vue` 的 `lexiconColumns` 移除 编码/必要上下文/排除上下文/置信度 四列，仅保留 **错误词/标准词/场景/动作/风险/状态/操作** 七列，与弹窗可配置项一致。**仅界面移除，DB 数据保留**（`required_context`/`excluded_context` 仍参与 `medical_term_correct` 引擎匹配，不影响既有纠错行为）。
- **版本管理直观化**：
  - 前端：页面顶部由"版本下拉"改为**版本列表表格**（状态/版本名称/编码/词库数/规则数/更新时间），点击行切换当前操作版本（当前行高亮 `version-row-active`），草稿/测试中版本行提供删除按钮（popconfirm 二次确认）。
  - 后端：新增 `DELETE /api/conversion-config/versions/{id}`（`backend/app/routers/conversion_config.py`）——**仅 draft/testing 可删除**（published/rolled_back 返回 409），删除时级联删除该版本 `ConversionLexiconEntry` 与 `ConversionRuleEntry`（`sqlalchemy.delete` + `db.delete`）；不存在返回 404。
  - `frontend/src/api/client.ts` 新增 `conversionConfigApi.deleteVersion(id)`。
  - 测试：`backend/tests/test_conversion_config.py::test_delete_version_only_allowed_for_draft`（草稿 200 / 已发布 409 / 不存在 404）。
- 兼容性：删除草稿不影响已发布版本与历史验证记录（`text_validation_runs.rule_version_id` 悬空仅影响追溯，`rule_version` 快照字符串保留）。
- 验证：后端目标测试 76 passed、前端构建成功、浏览器验证（版本列表/删除流程/词库 7 列）、接口验证草稿 200/已发布 409。

### 7. 2026-08-06 删除边界修正（已确认，待实施）

用户确认版本删除边界由"仅草稿/测试中可删"调整为**"草稿/测试中 + 已回滚均可删除"**（feature-spec「删除边界修正」变更记录）。实施范围：

- **后端** `backend/app/routers/conversion_config.py` 的 `DELETE /api/conversion-config/versions/{id}`：允许状态由 `("draft", "testing")` 扩为 `("draft", "testing", "rolled_back")`；**published（当前生效）仍返回 409**；409 提示文案同步更新（"仅草稿/测试中/已回滚版本可删除，已发布（当前生效）版本不可删除"）。级联删除词库/规则逻辑不变。
- **前端** `frontend/src/pages/ConversionConfig/index.vue` 版本列表：删除按钮显示条件由 `['draft', 'testing']` 扩为 `['draft', 'testing', 'rolled_back']`；删除确认文案明确"删除后历史规则不可恢复"。
- **测试** `backend/tests/test_conversion_config.py`：扩展删除用例覆盖 rolled_back 可删——发布 V1.0 → 克隆草稿 → 发布草稿（V1.0 自动变 rolled_back）→ `DELETE V1.0` 返回 200；published 删除仍 409。
- 影响：删除已回滚版本后该历史规则不可再"回滚发布"恢复（rollback 失去对象），属预期行为（用户已确认，二次确认提示）。

不新增数据库字段、不把内置规则入库、不改变 `run_conversion()` 返回语义、不改变现有 R001-R017 行为、不改变既有规则 CRUD 接口。

## 影响模块与预计修改文件

本轮实施预计影响（仅规则管理 tab 分组展示）：

- `backend/app/services/conversion_config.py`：新增 `BUILTIN_RULES_META` 内置清单元数据（文本切换 SW / 数据提取 F / 警示 R）与 `get_builtin_rules()`；警示组直接映射 `risk_intercept.RISK_RULES`。
- `backend/app/routers/conversion_config.py`：新增 `GET /builtin-rules` 只读接口。
- `backend/app/schemas/conversion_config.py`：新增 `BuiltinRulesOut` 响应模型（可选，也可直接返回 dict）。
- `frontend/src/api/client.ts`：新增 `conversionConfigApi.listBuiltinRules()`。
- `frontend/src/pages/ConversionConfig/index.vue`：规则管理 tab 按分组渲染（tab 样式改造），内置规则只读。
- 测试：`backend/tests/test_conversion_config.py` 新增 builtin-rules 接口用例；`backend/tests/test_risk_intercept.py`（或 `test_conversion_engine.py`）新增"名词/换边词纠错不产生警示"用例。

不涉及：`field_parser.py`、`risk_intercept.py`、`business_segment_locator.py`、`database.py`、`text_validation.py`、`TextValidation/index.vue`（引擎与验证链路零改动）。

## 数据结构与接口变化

### 兼容优先方案

短期不强制新增表。用现有字段承载：

- “标准词 + 多个近似词”：前端按 `standard_text` 分组展示，后端仍以多条 `ConversionLexiconEntry` 存储，每条一个 `error_text`。
- 定位词：存入 `ConversionLexiconEntry`，`business_scene` 可用“卵泡监测B超/定位词”，`notes` 或 `required_context` 标识用途。
- 文本切换/提取/警示规则：存入 `ConversionRuleEntry`，参数写入 `condition_config`。

### 建议后续补充字段

如需要更清晰的规则管理，可通过 `_ensure_column()` 兼容迁移：

- `conversion_lexicon_entries.term_type VARCHAR(30)`：medical_term / locator / noise / remark。
- `conversion_lexicon_entries.standard_code VARCHAR(80)`：如 right_ovary、left_ovary、side_switch。
- `conversion_rule_entries.severity VARCHAR(30)`：与 risk_level 分离，用于警示展示。

这些字段不是首轮实施阻塞项；首轮可先复用现有字段。

### 接口变化

本轮新增：

- `GET /api/conversion-config/builtin-rules`
  - 返回三组内置规则元数据（只读）：`text_switch`（SW001-SW003）、`field_extract`（F001-F014）、`risk`（R001-R017，直接映射 `risk_intercept.RISK_RULES`）。
  - 用于规则管理 tab 分组展示；不包含 DB 中的参数化规则（仍走现有 `/versions/{id}/rules`）。

既有接口保持不变：

## 前后端职责

### 后端

- 负责规则版本、词库、规则的持久化、发布、回滚。
- 负责将配置词库加载为运行时规则，保证已发布版本可复现。
- 负责业务片段定位、文本转化、字段解析和风险拦截。
- 负责输出可追溯结果：原文、转化后文本、命中规则、source spans、字段、警示项。
- 负责与 `BUltraResult` 对比，保持现有 `evaluate_result()` 口径。

### 前端

- 负责按规则版本展示词库和规则，发布版本只读。
- 负责把同一标准词下的多个近似词分组展示和批量编辑体验。
- 负责预览转化结果、命中规则、业务片段和警示项。
- 负责文本验证工作台中展示原始 ASR、纠错文本、结构化字段、真实结果对比。
- 不在前端实现业务规则判定，只消费后端返回的结构。

## 兼容和迁移要求

- 已发布版本不可直接修改；修改必须克隆草稿后发布。
- 不删除现有 `CONFUSION_RULES`，默认版本初始化仍从硬编码词库导入。
- 不改变 `run_conversion()` 的基本返回语义：`raw_text`、`normalized_text`、`conversions`、`warnings`、`fields`、`source_spans`、`risk_passed`、`risk_blocked`。
- 不改变 ASR/LLM provider 工厂和模型配置协议。
- SQLite 字段新增必须写入 `database.py:init_db()` 的 `_ensure_column()`。
- 现有测试数据和历史 `text_validation_runs` 需兼容 `source_spans` 为空的情况。

## 风险与回滚方案

- 风险：文本切换规则误把缺少定位词的卵泡归入上一侧。
  - 控制：只在最近明确侧别窗口内继承；跨强边界或冲突时警示复核。
- 风险：词库自动替换改变医疗事实。
  - 控制：数字、否定词、决策词、高风险术语默认 REVIEW/BLOCK，不做 AUTO。
- 风险：字段解析规则过拟合当前样本。
  - 控制：新增规则必须配测试样例，配置页预览与文本验证双路径回归。
- 风险：大批量验证性能不足。
  - 控制：首轮实时计算；后续再考虑缓存验证结果，不提前引入新表。
- 回滚：发布错误规则版本时，使用现有 `/versions/{id}/rollback` 将旧版本重新置为 published；必要时禁用草稿词条或规则。

## 测试和回归范围

- 后端单元测试：
  - 词库分组/上下文匹配。
  - 文本切换：显式左右词、换边词、缺失定位词继承、强边界停止继承。
  - 数据提取：内膜、卵巢大小、卵泡 2-40mm、卵巢尺寸 10-100mm。
  - 警示：卵泡 >40mm、卵巢单维 <10mm、左右冲突、数字边界不确定、否定词/决策词；医疗名词/换边词纠错**不产生警示**（验证修正后口径）。
- 后端接口测试：
  - `conversion-config/init-defaults`、clone、publish、preview。
  - `conversion-config/builtin-rules` 返回三组、R001-R017 与 `risk_intercept.RISK_RULES` 一致。
  - `text-validation/runs` 保存历史、source_spans、evaluation。
- 前端验证：
  - `npm run build`。
  - 配置页版本切换、草稿编辑、发布只读、预览展示；规则管理二级 tab（文本切换/数据提取/警示规则/引擎基础步骤只读 + 参数化规则可编辑）；词库弹窗批量添加/整组编辑近似词。
  - 文本验证页可选择规则版本并展示字段对比。
- 回归命令：
  - `cd backend && ./.venv/bin/python -m pytest tests/test_conversion_config.py tests/test_business_segment_locator.py tests/test_conversion_engine.py tests/test_text_validation.py tests/test_risk_intercept.py -v`（76 passed：75 + 版本删除接口用例）
  - `cd frontend && npm run build`（vue-tsc 类型检查 + vite）
