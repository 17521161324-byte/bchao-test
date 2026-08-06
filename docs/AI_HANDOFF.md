# AI_HANDOFF - 提取规则梳理与转化

## 当前目标

已确认需求已**全部实施完成**（工作树未提交）：词库管理（标准词+近似词分组展示、弹窗批量添加/整组编辑、表格列精简为七列与弹窗一致）、文本切换规则、数据提取规则、警示规则（R001-R017，名词/换边词纠错不警示）、版本管理（版本列表表格展示 + 删除）、文本验证链路、规则管理二级 tab、内置规则展示。目标测试 **76 passed**、前端构建成功、浏览器验证通过。**本轮待实施**：版本删除边界修正——放开 **rolled_back（已回滚）版本删除**（draft/testing/rolled_back 可删，published 仍不可删），范围小且明确。其余无剩余实施缺口；后续工作为真实样本回归校准侧别继承窗口边界（非阻塞）。

## 已确认决策

- 现有技术栈不变：FastAPI + SQLAlchemy async + SQLite，Vue 3 + TypeScript + ant-design-vue。
- 后端优先复用 `ConversionConfigVersion`、`ConversionLexiconEntry`、`ConversionRuleEntry`。
- “标准词 + 多个近似词”用多条 `ConversionLexiconEntry` 表达，前端按 `standard_text` 分组展示（已实施：组头展示标准词与近似词数量，支持一键新增近似词）。
- 转化链路继续复用 `run_conversion()`：基础清洗 → 数字标准化 → 医学术语纠错 → 业务片段转化 → 字段解析 → 风险拦截。
- 数字、左右侧、否定词和医疗决策不可猜；不确定时输出 REVIEW/BLOCK 警示。
- 已发布版本不可直接编辑，修改必须克隆草稿后发布。

## 本次实施内容

### 风险拦截（`risk_intercept.py`）

- R005 左右侧冲突/缺失从空实现补为实逻辑：出现“左右卵巢/左右侧”模糊表述，或卵巢数据存在但全文缺少左右/换边触发词（如“卵巢大小60×35”被默认归属右侧）时 → REVIEW。
- 新增 R016 卵泡直径 >40mm → REVIEW（不阻断）；R017 卵巢任一单维 <10mm → REVIEW（不阻断）。
- `RISK_RULES` 由 15 条扩为 17 条；`check_risks()` 签名不变。

### 字段解析（`field_parser.py`）

- 卵泡解析从“超出 2-40mm 即丢弃”改为“2-100mm 保留，>40mm 加 warning”，配合 R016 输出警示，避免静默掩盖真实异常或录入问题。

### 接口与持久化

- `POST /api/conversion-config/preview` 返回新增 `segments`（业务片段）与 `risk_items`（结构化警示项）。
- `text_validation_runs` 新增 `conversions` / `segments` / `warnings` / `risk_items` 四个 JSON 列，走 `database.py:init_db()` 的 `_ensure_column()` 并回填 `[]`，兼容历史数据。
- 最终复核修复：`POST /api/text-validation/runs` 现在会加载所选 `rule_version_id` 的启用词库并传入 `run_conversion()`，规则版本选择会真实影响文本提取。
- 最终复核修复：文本验证保存的 `segments` 改为基于 `conversion.normalized_text` 定位，和规则预览接口一致；`corrected_text` 仍保留 LLM/人工纠错原文。
- 最终复核修复：`POST/PUT /api/conversion-config/versions` 不能直接写入 `published/rolled_back`，发布和回滚必须走 `/publish` / `/rollback`，避免绕过 `publish_version()` 的回滚逻辑。

### 前端

- `ConversionConfig/index.vue`：词库按标准词分组展示；版本测试新增警示项、字段解析、业务片段三个区块与三态风险标签。
- `TextValidation/index.vue`：当前结果新增命中规则、业务片段、规则警示三个区块。

## 本轮实施范围（缺口补全）

以用户确认的界面文字布局为基准逐区块核对：差异集中在**规则管理 tab**（当前为平铺表格、仅 5 条系统规则占位）。修改点：

1. **R018 取消（需求修正）**：用户确认医疗名词/换边词识别错误**不生成警示**，警示仅由数字等数据异常触发；当前实现已满足，R018 不实现。
2. **规则管理 tab 分组展示（tab 样式改造，核心）**：
   - 后端：`conversion_config.py` 新增 `BUILTIN_RULES_META` + `get_builtin_rules()`（文本切换 SW001-SW003、数据提取 F001-F014、警示规则直接映射 `risk_intercept.RISK_RULES` R001-R017）；`GET /builtin-rules` 只读接口；schema `BuiltinRulesOut`。
   - 前端：`ConversionConfig/index.vue` 规则管理 tab 改为分组标题 + 分组内表格——文本切换/数据提取/警示规则（内置只读）+ 引擎基础步骤（DB B001/N001/M001 只读）+ 参数化规则（DB editable=1 可编辑）；`client.ts` 新增 `listBuiltinRules`。
3. **现有 5 条系统规则归类**：B001/N001/M001/F001/R001 按 rule_type 归入对应分组展示，不删除、不改引擎行为。
4. **警示口径测试**：新增用例断言名词/换边词纠错后 `risk_items` 不含名词类警示。
5. **引擎零改动**：不改 `run_conversion()`、`RISK_RULES`、`field_parser.py`、`business_segment_locator.py`。

其余首轮开发内容（词库分组、业务片段定位、字段解析、R005/R016/R017、版本管理、文本验证链路、前端两页、迁移回填）已完成，不重复开发。

## 禁止修改内容

- 不重新初始化项目。
- 不替换后端、前端、数据库或部署技术栈。
- 不新增 ASR/LLM provider，不改变模型配置协议。
- 不改真实 B 超结果导入格式。
- 不把高风险数字、左右归属、否定语义或医疗决策词做静默自动修正。
- 不回退或覆盖当前工作树里与本规划无关的既有改动。

## 实施顺序状态

1. [x] 基线确认：复核 `conversion_config`、`conversion_engine`、`text_validation` 当前实现和测试状态。
2. [x] 词库管理：前端按 `standard_text` 分组展示 + 新增近似词预填，后端不改表。
3. [x] 文本切换：`business_segment_locator.py` 侧别锚点、换边词、缺失定位词继承、强边界停止（工作树既有实现，测试通过）。
4. [x] 数据提取：`field_parser.py` 卵泡、卵巢大小、内膜字段提取和 source span；本次补充 >40mm 卵泡保留 + 警示。
5. [x] 警示规则：`risk_intercept.py` R005 实逻辑 + R016 卵泡 >40mm + R017 卵巢单维 <10mm。
6. [x] 页面展示：`ConversionConfig/index.vue` 预览与 `TextValidation/index.vue` 验证结果展示命中规则、业务片段、字段、警示。
7. [x] 测试回归：补齐规则、接口和前端构建验证；最终复核补充规则版本词库生效和版本状态保护测试。
8. [x] 内置规则清单元数据：`conversion_config.py` 新增 `BUILTIN_RULES_META` + `get_builtin_rules()`（SW/F/R 三组，警示组映射 `RISK_RULES`）。
9. [x] 接口：`conversion_config.py` 路由新增 `GET /builtin-rules` + schema `BuiltinRulesOut`；`tests/test_conversion_config.py` 新增接口用例。
10. [x] 前端 tab 样式改造：`ConversionConfig/index.vue` 规则管理 tab 分组渲染（文本切换/数据提取/警示规则内置只读 + 引擎基础步骤 + 参数化规则可编辑）+ `client.ts` 新增 `listBuiltinRules`。
11. [x] 警示口径测试：`test_conversion_engine.py::TestWarningScope` 3 用例（名词/换边词纠错无警示、数据异常仍触发 R016）。
12. [x] 回归：目标测试 75 passed（71+4）、前端构建成功、浏览器界面验证规则管理 tab 分组（文本切换 3 / 数据提取 15 / 警示 18 / 引擎基础 3 / 参数化 0 条，内置只读）。
13. [x] 最终复核修复：规则分组增加未归类系统规则兜底展示（`editable=0` 且非 B001/N001/M001/F001/R001 的规则并入引擎基础步骤组），修复后目标测试 75 passed、前端构建（含 vue-tsc）通过。
14. [x] UI 交互调整（用户提出）：① 词库弹窗重构为标准词+业务场景+近似词动态列表（一次添加多个近似词，编辑整组加载，rule_code 自动生成，移除冗余字段）；② 规则管理分组改为二级 tab（文本切换/数据提取/警示规则/引擎基础步骤/参数化规则）。前端构建通过，浏览器验证批量添加/编辑/二级 tab 均正常，测试数据已清理，后端 75 passed 无回归。
15. [x] 2026-08-06 实施轮复核：`docs/task-checklist.md` 中 [IMPLEMENT]/[VERIFY]/[REVIEW] 事项**全部完成、无未完成事项**；本轮无待实施代码修改。交付状态复核：后端目标测试 75 passed、前端构建（vue-tsc+vite）成功，改动范围确认（需求相关文件 + 既有无关改动未触碰）。
16. [x] 2026-08-06 最终技术复核（全任务）：9 项检查点核对通过——实现完整满足已确认需求、无越界（R018 已取消）、引擎改动为增量向后兼容、text_validation_runs 迁移+回填兼容旧数据、警示组元数据映射 RISK_RULES 无副本、规则分组未归类兜底已修复、测试覆盖核心路径（75 passed/全量 210）、四份文档与代码一致、工作树既有无关改动（conversion_eval batch workbench/model_config/cli_executor/config/llm trust_env）非本任务引入且未触碰。无 BLOCKER、无待修 IMPORTANT。剩余均为 MINOR/非阻塞遗留。
17. [x] 2026-08-06 新增需求实施：① 版本删除接口 `DELETE /versions/{id}`（仅 draft/testing，级联删词库/规则，published/rolled_back 409）；② 版本列表表格（直观展示+点击切换+草稿可删）；③ 词库表格列精简为七列（移除编码/上下文/置信度，DB 保留）。验证：后端 76 passed、前端构建成功、浏览器验证通过（版本列表/删除流程/词库 7 列）、接口验证草稿 200/已发布 409。后端已重启加载新路由（原 uvicorn 无 --reload）。

## 验证结果

```bash
cd backend
./.venv/bin/python -m pytest tests/test_conversion_config.py tests/test_business_segment_locator.py tests/test_conversion_engine.py tests/test_text_validation.py tests/test_risk_intercept.py -v
# 75 passed（原 71 + test_builtin_rules_returns_three_groups + TestWarningScope 3 用例）

./.venv/bin/python -m pytest -q
# 206 passed；4 failed（已知既有失败，见下）

cd frontend
npm run build
# 构建成功，仅有既存 chunk 体积告警

# 界面验证（临时启动 uvicorn + vite dev，验证后已关闭）：
# 规则管理 tab 分组渲染正确：文本切换规则 3 条、数据提取规则 15 条、警示规则 18 条、
# 引擎基础步骤 3 条、参数化规则（含操作列）；内置组只读无操作按钮。
```

## 已知问题和待确认项

- **R018 已取消**：需求修正为"医疗名词/换边词错误不生成警示，警示仅由数据异常触发"，原 R018 方案作废，不实现。
- 完整后端测试套件存在 4 个与本次需求无关的既有失败，均位于本次改动范围之外，未修改：
  - `test_experiment_api.py::test_model_config_out_no_credentials`、`test_model_schema.py::test_model_output_does_not_expose_credentials`：ModelConfig 输出暴露 `api_key`（模型配置 schema 区域）。
  - `test_experiment_runner.py::test_runner_no_audio_raises_with_patient_id`：`asr_source` 变量作用域（实验执行器区域）。
  - `test_patient_asr_result_model.py::test_patient_asr_segments_track_in_place_append`：异步懒加载 MissingGreenlet（ASR 结果关系区域）。
- “卵巢大小数据单边不小于 10 以下”口径已按“任一维 <10mm 即警示”实施（R017，REVIEW 不阻断），如确认为“两维均 <10mm 才警示”需调整 R017 条件。
- 卵泡 >40mm 已按“提取并标记异常，不直接丢弃”实施（R016，REVIEW），前端可人工复核。
- 缺失定位词的侧别继承窗口（240 字符、强边界停止）基于现有样本回归，后续可用更多真实样本校准。

## 2026-08-06 DeepSeek 流水线改造实施进度（中途）

- 已完成（本人实施，全量后端 231 passed / 4 个既有无关失败；前端构建通过）：
  - Task 1-5：conversion_pipeline 包（types/decision_registry/context/span_map/dimension_parser D001-D003）
  - Task 6：医学词规则版本语义（rule_mode builtin/replace/append、priority 排序、CANDIDATE 去文本注入）
  - Task 7：业务片段安全修复（删除"五回声→无回声"硬编码、替换经决策注册表）
  - Task 8：field_parser 状态机（ParserState、禁止默认右侧→unassigned_ovary_sizes、侧别切换、字段锁定、卵泡 n.m 格式、20×19无回声归备注）
  - Task 9：risk_intercept（R005 unassigned、R006 ??×N BLOCK、新增 R019/R020）
  - Task 10：runtime_rule_executor（handler 白名单）+ load_enabled_runtime_rules
  - Task 11：orchestrator.run_pipeline 固定 7 步 + resolve_result_level + run_conversion 兼容（旧字段保留，新增 steps/result_level/config_hash）
  - Task 17-21（前端，子代理 agent-3 产物）：ConversionDebug 页 + 5 组件 + types + conversionPipelineApi + 路由/菜单；npm run build 通过
- 未完成（方案附件文件被清理丢失，原文不可得；后端子代理 agent-2 未产出）：
  - Task 12：build_config_hash 完整实现（orchestrator 已接收 config_hash 参数）
  - Task 13：持久化模型 conversion_pipeline 两张表
  - Task 14-15：Pipeline Schema + /api/conversion-pipeline 5 端点
  - Task 16：现有接口接入（preview/text-validation/conversion-eval 传 runtime_rules/lexicon_mode/steps/result_level）
- 风险：方案原文 .kandev/attachments/.../医疗ASR流水线与规则调试工作台_DeepSeek代码改造实施计划_V1.0.md 已不存在（系统清理）；如需继续 Task 12-16，需用户提供方案备份或按本摘要继续。

## 2026-08-06 DeepSeek 流水线改造实施完成（最终）

- **全部 21 个 Task 已完成**（本人实施 + 前端子代理产物）：
  - Task 1-11：conversion_pipeline 包（types/decision_registry/context/span_map/dimension_parser/runtime_rule_executor/orchestrator）+ 引擎改造（medical_term rule_mode、business_segment 去硬编码、field_parser ParserState 状态机、risk_intercept R005/R006/R019/R020）+ run_conversion 兼容
  - Task 12：build_config_hash（config_snapshot 冻结 + sha256）
  - Task 13：持久化模型 ConversionPipelineExecution/ConversionPipelineStep（两张表，create_all 创建）
  - Task 14-15：Pipeline Schema + /api/conversion-pipeline 5 端点（executions 创建/详情、run-step 单步、fork-from-step、compare）
  - Task 16：preview/text-validation 接入（runtime_rules + lexicon_mode + steps/result_level/config_hash）
  - Task 17-21：前端调试台（ConversionDebug + 5 组件 + conversionPipelineApi + 路由/菜单）+ 文本验证接入 + 规则配置页调整
- **验证**：后端全量 235 passed / 4 个既有无关失败；前端 npm run build 通过；pipeline API 4 测试通过
- **关键修复**：_execution_out 手动构建避免 ORM 异步懒加载 MissingGreenlet；CANDIDATE 去文本注入后同步调整旧测试断言（test_conversion_engine/test_conversion_eval/test_risk_intercept）
- **遗留/未做**：conversion-eval 中 run_conversion 调用点未逐一补 lexicon_mode（方案 21.3 建议统一，但 conversion-eval 为既有模块、默认 builtin 行为不变，未强行改动）；build_config_hash 在 conversion_pipeline/orchestrator.py；前端差异对比为并排显示（方案允许降级）

## 2026-08-06 最终技术复核（DeepSeek 流水线改造）

- 9 项检查点核对：实现完整满足方案（21 Task）、无越界（未重写引擎/未改 LLM 顺序/Provider/真实数据格式）、run_conversion 兼容旧字段、新增表与 API 不破坏旧数据、handler 白名单禁 eval、测试覆盖核心路径、文档一致、无关文件未触碰。
- 修复 1 个 IMPORTANT：流水线步骤持久化的 config_hash 误用不存在的 snapshot["_hash"]（存空串），改为传 execution.config_hash——修复后全量 235 passed / 4 个既有无关失败，无新增回归。
- 剩余 MINOR（不阻塞）：conversion-eval 调用点未逐一补 lexicon_mode（默认 builtin 行为不变）；前端差异对比为并排显示（方案允许降级）；run-step 内部为完整重跑后只暴露下一步（效率可优化，语义正确）。
