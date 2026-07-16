"""最小修复 DataImport: 兼容 currentLlmResult 与 llmResult"""
import re

path = "frontend/src/pages/DataImport/index.vue"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 在 </template> 前插入 loadCurrentLlmResult 函数与 currentLlmResult 声明
# 查找 setup 函数中的 asrResult 声明之后
anchor = "const asrResult = computed(() => {"
if anchor in content:
    insert_after = anchor.split("\n")[0]
    # 找到这个 computed 的结束位置
    idx = content.index(anchor)
    # 找对应的闭合 }
    brace_count = 0
    start = content.index("{", idx)
    for i in range(start, len(content)):
        if content[i] == "{":
            brace_count += 1
        elif content[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                end_pos = i + 1
                break

    new_code = """
    // 加载当前检查记录的 LLM 历史结果
    const currentLlmResult = ref<any>(null)

    async function loadCurrentLlmResult() {
      if (!selectedRecord.value) return
      try {
        const res = await patientApi.getLlmCurrent(selectedRecord.value.id)
        currentLlmResult.value = res || null
      } catch { currentLlmResult.value = null }
    }
"""

    content = content[:end_pos] + new_code + content[end_pos:]

# 在 return 中补充 currentLlmResult 和 loadCurrentLlmResult
content = content.replace(
    "llmModels, llmModelId, llmRunning, llmResult, llmPrompt, runLlm, compareField, formatRawJson,",
    "llmModels, llmModelId, llmRunning, llmResult, currentLlmResult, llmPrompt, runLlm, compareField, formatRawJson, loadCurrentLlmResult,"
)

# onMounted 增加 loadCurrentLlmResult
content = content.replace(
    "onMounted(() => { store.fetchBatches(); store.fetchRecords() })",
    "onMounted(() => { store.fetchBatches(); store.fetchRecords(); loadCurrentLlmResult() })"
)

# watch selectedRecord 时刷新 LLM 结果
watch_block = """watch(selectedRecord, async (rec) => {
      currentAsrResult.value = null
      currentLlmResult.value = null
      asrHistory.value = []"""
content = content.replace(
    """watch(selectedRecord, async (rec) => {
      currentAsrResult.value = null
      asrHistory.value = []""",
    watch_block
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("OK")
