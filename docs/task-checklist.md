# 提取规则梳理与转化 - 任务清单

状态图例：
- `[ ]` 待办
- `[x]` 完成
- `[!]` 阻塞 / 待确认

## [IMPLEMENT] 开发实现

- [x] 阅读 `README.md`、`AGENTS.md` 和现有 `docs/` 产品/技术文档。
- [x] 阅读当前任务标题和描述，明确规则库四类需求：词库、文本切换、数据提取、警示规则。
- [x] 阅读相关代码入口：`conversion_config`、`conversion_engine`、`text_validation`、前端路由/API/页面。
- [x] 检查 Git 状态、基础分支和既有差异。
- [x] 更新 `docs/feature-spec.md`，固化需求边界、业务流程、验收标准和待确认事项。
- [x] 更新 `docs/technical-design.md`，固化现有入口、影响模块、接口/数据结构方案、迁移与回归范围。
- [x] 更新 `docs/task-checklist.md`，形成后续实施清单。
- [x] 更新 `docs/AI_HANDOFF.md`，记录交接信息。
- [x] 词库管理：前端按 `standard_text` 分组展示“标准词 + 多近似词”，后端复用多条 `ConversionLexiconEntry`，组头支持一键新增近似词（预填标准词）。
- [x] 文本切换：`business_segment_locator.py` 支持显式左右词、换边词、缺失定位词侧别继承窗口、强边界停止策略，输出 `segments`（medical_term/locator/medical_data/noise 四类）。
- [x] 数据提取：`field_parser.py` 覆盖内膜、卵巢大小、左右卵泡等 F001-F014 字段与 source span；本次补充 >40mm 卵泡“提取并标记警示”而非静默丢弃（2-100mm 保留，>40mm 加 warning）。
- [x] 风险拦截：`risk_intercept.py` 实现 R005 左右侧冲突/缺失实逻辑（模糊“左右”表述、缺侧别触发词→REVIEW），新增 R016 卵泡 >40mm、R017 卵巢单维 <10mm 警示（均 REVIEW 不阻断）。
- [x] 页面展示：规则预览展示命中规则、字段解析、业务片段、警示项（含人工复核建议）与三态风险标签；文本验证页展示命中规则、业务片段、警示项（新增持久化字段）。
- [x] 最终复核修复：文本验证执行时加载所选规则版本的启用词库，避免 `rule_version_id` 只保存快照、不影响实际提取。
- [x] 最终复核修复：限制版本创建/更新接口直接写入 `published/rolled_back` 状态，发布和回滚只能走专用接口，避免绕过版本回滚逻辑。
- [x] 最终复核修复：文本验证保存的业务片段基于规则转化后的文本定位，和规则预览口径一致。

## 本轮缺口补全（2026-08-05 技术规划复核后追加，第三版）

> 背景：以用户确认的界面文字布局为基准逐区块核对后，差异集中在规则管理 tab（当前为平铺表格、仅 5 条系统规则占位）。原 R018（非医疗类错误警示）因需求修正（医疗名词/换边词不警示）**取消**。本轮修改点为规则管理 tab 分组展示（tab 样式改造）+ 现有系统规则归类 + 警示口径测试。

### [IMPLEMENT] 开发实现

- [x] 后端内置清单元数据：`backend/app/services/conversion_config.py` 新增 `BUILTIN_RULES_META` + `get_builtin_rules()`，返回三组：文本切换 SW001-SW003、数据提取 F001-F014（名称/说明/范围校验）、警示规则 R001-R017（直接映射 `risk_intercept.RISK_RULES`，保证与引擎同步）。
- [x] 后端接口：`backend/app/routers/conversion_config.py` 新增 `GET /builtin-rules` 只读接口；`backend/app/schemas/conversion_config.py` 新增 `BuiltinRulesOut`。
- [x] 前端 tab 样式改造：`frontend/src/pages/ConversionConfig/index.vue` 规则管理 tab 由平铺表格改为**分组标题 + 分组内表格**——文本切换规则（内置只读）/ 数据提取规则（内置 F + DB F001）/ 警示规则（内置 R + DB R001）/ 引擎基础步骤（DB B001/N001/M001 只读）/ 参数化规则（DB editable=1，保留新增/编辑/删除）；内置规则只读无操作按钮；搜索对各分组过滤。
- [x] 前端 API：`frontend/src/api/client.ts` 新增 `conversionConfigApi.listBuiltinRules()`。
- [x] 警示口径测试：`backend/tests/test_conversion_engine.py` 新增 `TestWarningScope`（3 用例）——名词纠错（肉卵巢→右卵巢）、换边词纠错（放边→换边）后 `risk_items` 为空；数据异常（卵泡 41.5mm）仍触发 R016。
- [x] 接口测试：`backend/tests/test_conversion_config.py` 新增 `test_builtin_rules_returns_three_groups`（返回三组、R001-R017 与 `risk_intercept.RISK_RULES` 一致）。

### [VERIFY] 构建、测试和回归

- [x] `cd backend && ./.venv/bin/python -m pytest tests/test_conversion_config.py tests/test_business_segment_locator.py tests/test_conversion_engine.py tests/test_text_validation.py tests/test_risk_intercept.py -v`（75 passed：原 71 + builtin-rules 1 + TestWarningScope 3）。
- [x] `cd frontend && npm run build`（成功，仅有既存 chunk 体积告警）。
- [x] 界面手测（浏览器实际验证，以确认文字布局为基准）：规则配置页 3 tab 结构正常；规则管理 tab 分组样式——文本切换规则 3 条 / 数据提取规则 15 条 / 警示规则 18 条 / 引擎基础步骤 3 条 / 参数化规则（含操作列）；内置组只读无操作按钮；文本验证页布局未改动。

### [REVIEW] 最终技术复核

- [x] 确认内置清单仅展示、引擎逻辑零改动（未改 `run_conversion()`、`RISK_RULES`、`field_parser.py`、`business_segment_locator.py`）。
- [x] 确认警示组元数据直接映射 `risk_intercept.RISK_RULES`，不另维护副本（接口测试断言集合一致）。
- [x] 确认已按用户确认的文字布局逐区块核对，规则管理 tab 分组已实现，其余区块无差异。
- [x] 确认未引入新依赖、未新增 DB 字段、未改变既有规则 CRUD 接口。
- [x] 最终复核修复：规则分组增加**未归类系统规则兜底**——`editable=0` 且编码非 B001/N001/M001/F001/R001 的规则并入"引擎基础步骤"组展示，避免分组后漏显示。
- [x] 最终复核修正：`docs/technical-design.md` 回归命令过时数字（71 passed → 75 passed）。

## 2026-08-05 UI 交互调整（用户提出）

### [IMPLEMENT] 开发实现

- [x] 词库弹窗重构：由"单条多字段"改为**标准词 + 业务场景 + 近似词动态列表**——一次可添加多个近似词（每条含错误词/动作/风险/启用开关），`+ 添加近似词` 动态增行；编辑模式整组加载同标准词全部近似词（标准词锁定防错乱），保存时批量更新/创建/删除（复用既有 CRUD 接口）；移除规则编码/ASR模型/置信度/匹配方式/优先级/上下文/备注字段（rule_code 自动生成 `L{ts}{i}`，其余保留后端默认值）。
- [x] 规则管理分组改为**二级 tab**：文本切换规则/数据提取规则/警示规则/引擎基础步骤/参数化规则五个二级 tab（ant 嵌套 Tabs），各 tab 独立表格；内置组只读、参数化组可编辑；搜索对各 tab 条目过滤。

### [VERIFY] 构建、测试和回归

- [x] `cd frontend && npm run build`（vue-tsc 类型检查 + vite 构建成功）。
- [x] 浏览器实际验证：二级 tab 五组渲染正常；词库弹窗批量添加 2 个近似词（标准词"右附件"）成功、组头显示"2 个近似词"、rule_code 自动生成；编辑模式整组加载 2 条；测试数据已清理。
- [x] `cd backend && ./.venv/bin/python -m pytest tests/test_conversion_config.py tests/test_business_segment_locator.py tests/test_conversion_engine.py tests/test_text_validation.py tests/test_risk_intercept.py -q`（75 passed，后端无改动）。

### [REVIEW] 最终技术复核

- [x] 确认后端接口零改动（复用既有 lexicon CRUD 批量调用），无新增 DB 字段。
- [x] 确认移除的弹窗字段不破坏已有数据（DB 中原有字段值保留，仅界面不再编辑）。

## 2026-08-06 新增需求（用户提出）

### [IMPLEMENT] 开发实现

- [x] 版本删除接口：`backend/app/routers/conversion_config.py` 新增 `DELETE /api/conversion-config/versions/{id}`——仅 draft/testing 可删除（published/rolled_back 返回 409），删除时级联删除该版本词库与规则条目（`delete(ConversionLexiconEntry/RuleEntry)` + `db.delete(version)`）。
- [x] 版本列表表格：`frontend/src/pages/ConversionConfig/index.vue` 顶部由"版本下拉"改为**版本列表表格**（状态/版本名称/编码/词库数/规则数/更新时间），点击行切换当前版本（当前行高亮 `version-row-active`），草稿/测试中版本行提供删除按钮（popconfirm 二次确认）。
- [x] 词库表格列精简：`lexiconColumns` 移除 编码/必要上下文/排除上下文/置信度 四列，仅保留 **错误词/标准词/场景/动作/风险/状态/操作** 七列，与弹窗可配置项一致（DB 数据保留，上下文仍参与引擎匹配）。
- [x] 前端 API：`frontend/src/api/client.ts` 新增 `conversionConfigApi.deleteVersion(id)`。
- [x] 接口测试：`backend/tests/test_conversion_config.py` 新增 `test_delete_version_only_allowed_for_draft`（草稿可删 200、已发布 409、不存在 404）。

### [VERIFY] 构建、测试和回归

- [x] `cd backend && ./.venv/bin/python -m pytest tests/test_conversion_config.py tests/test_business_segment_locator.py tests/test_conversion_engine.py tests/test_text_validation.py tests/test_risk_intercept.py -q`（76 passed：75 + 删除接口用例）。
- [x] `cd frontend && npm run build`（vue-tsc + vite 成功）。
- [x] 浏览器实际验证：版本列表表格渲染（草稿行带删除按钮、已发布行无）；词库表格 7 列（无编码/上下文/置信度）；删除流程（点击删除 → 确认弹窗 → 后端生效）；接口验证 DELETE 草稿 200 / 已发布 409。

### [REVIEW] 最终技术复核

- [x] 确认词库列移除仅界面层（DB 保留，不影响引擎上下文匹配行为）。
- [x] 确认删除限制合理（已发布=当前生效规则不可删；已回滚=保留历史可重新发布恢复）。

## 2026-08-06 删除边界修正（用户确认）

> 需求确认：版本删除边界由"仅草稿/测试中可删"调整为**草稿/测试中 + 已回滚均可删除**，已发布（当前生效）不可删（feature-spec「删除边界修正」变更记录）。

### [IMPLEMENT] 开发实现

- [ ] 后端放开 rolled_back 删除：`backend/app/routers/conversion_config.py` 的 `DELETE /versions/{id}` 允许状态 `("draft", "testing", "rolled_back")`，published 仍 409，提示文案更新。
- [ ] 前端删除按钮条件：`frontend/src/pages/ConversionConfig/index.vue` 版本列表删除按钮显示条件扩为 `['draft', 'testing', 'rolled_back']`，确认文案强调"删除后历史规则不可恢复"。
- [ ] 测试扩展：`backend/tests/test_conversion_config.py` 增加 rolled_back 可删用例（发布→克隆→发布→旧版本变 rolled_back→删除 200）。

### [VERIFY] 构建、测试和回归

- [ ] 后端目标测试（76 + 新用例）通过；前端 `npm run build` 成功。
- [ ] 浏览器/接口验证：rolled_back 版本删除 200、published 删除 409。

### [REVIEW] 最终技术复核

- [ ] 确认 published（当前生效）仍不可删除；级联删除与提示文案符合需求。

## [VERIFY] 构建、测试和回归

- [x] 文档自检：四份规划文档主题一致，均面向“提取规则梳理与转化”。
- [x] `cd backend && ./.venv/bin/python -m pytest tests/test_conversion_config.py tests/test_business_segment_locator.py tests/test_conversion_engine.py tests/test_text_validation.py tests/test_risk_intercept.py -v`（最终复核后 71 passed）
- [x] `cd frontend && npm run build`（成功，仅有既存 chunk 体积告警）
- [x] 配置版本初始化、克隆、发布、回滚（`test_conversion_config.py` 覆盖）。
- [x] 配置版本状态不能绕过发布接口（`test_version_status_cannot_bypass_publish_endpoint` 覆盖）。
- [x] 规则预览不改变高风险数字/否定词/医疗决策词（R004/R006/R008/R014 测试覆盖）。
- [x] 文本验证历史保存、source span 高亮、真实结果对比；本次补充 segments/conversions/warnings/risk_items 持久化与历史兼容（NULL→[] 回填），并覆盖所选规则版本词库实际生效。
- [x] 全量后端测试：`cd backend && ./.venv/bin/python -m pytest -q`（206 passed；4 failed 为已知既有失败，见 AI_HANDOFF.md）。

## [REVIEW] 最终技术复核

- [x] 确认本阶段实现复用现有模块、接口和公共能力，未引入主要依赖。
- [x] 确认未提出重新初始化项目、替换技术栈、引入主要依赖升级或无关重构。
- [x] 确认兼容 SQLite 手动迁移方式（新增字段均走 `init_db()` 的 `_ensure_column()` + 回填）。
- [x] 确认已发布版本不可直接修改，修改必须克隆草稿后发布（接口层 409 保护）。
- [x] 开发完成后检查 Git diff：本次改动仅涉及转化引擎、配置/验证接口、验证模型与两个前端页面，未覆盖工作树中的既有无关改动。
- [x] 开发完成后复跑后端目标测试（71 passed）和前端构建（成功）。
- [!] 已知项：完整后端测试套件中 4 个与本需求无关的既有失败（`test_experiment_api`、`test_model_schema`、`test_experiment_runner`、`test_patient_asr_result_model`），涉及模型凭证输出、实验执行器变量、ASR 结果关系懒加载，均位于本次改动范围之外，未修改。
