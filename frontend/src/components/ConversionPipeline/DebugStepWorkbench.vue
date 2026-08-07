<template>
  <section class="debug-workbench">
    <template v-if="executed">
      <!-- 头：步骤名 + 统计 -->
      <div class="wb-head">
        <div class="wb-title">
          步骤{{ stepIndex }} · {{ def?.name }}
          <span class="wb-tags">
            <span class="wb-tags-label">本步骤可处理：</span>
            <template v-if="processableTags.length">
              <a-tag v-for="tag in processableTags" :key="tag" class="wb-tag" color="purple">{{ tag }}</a-tag>
              <span v-if="processableTagsExtra" class="wb-tags-more">+{{ processableTagsExtra }}</span>
            </template>
            <span v-else class="muted">无</span>
          </span>
          <span class="wb-tags wb-tags-unhandled">
            <span class="wb-tags-label">本步骤不处理：</span>
            <template v-if="unhandledTags.length">
              <a-tag v-for="tag in unhandledTags" :key="tag" class="wb-tag">{{ tag }}</a-tag>
              <span v-if="unhandledTagsExtra" class="wb-tags-more">+{{ unhandledTagsExtra }}</span>
            </template>
            <span v-else class="muted">无</span>
          </span>
        </div>
        <div class="wb-stats">
          <div class="stat-box">
            <div class="stat-num">{{ stats.loaded }}</div>
            <div class="stat-label">加载规则</div>
          </div>
          <div class="stat-box">
            <div class="stat-num">{{ stats.called }}</div>
            <div class="stat-label">实际调用</div>
          </div>
          <div class="stat-box">
            <div class="stat-num stat-hit">{{ stats.hit }}</div>
            <div class="stat-label">命中规则</div>
          </div>
          <div class="stat-box">
            <div class="stat-num stat-missing">{{ stats.missing }}</div>
            <div class="stat-label">缺失规则</div>
          </div>
        </div>
      </div>

      <!-- 输入输出双栏 -->
      <div class="wb-io">
        <div class="io-card">
          <div class="io-title">输入：…</div>
          <pre class="io-text">{{ input || '-' }}</pre>
        </div>
        <div class="io-card">
          <div class="io-title">
            本步输出
            <a-space size="small">
              <span v-if="isAnnotatedStep" class="annotate-legend">
                <span class="lg lg-anchor">医学锚点</span>
                <span class="lg lg-standard">标准结果</span>
                <span class="lg lg-candidate">候选</span>
                <span class="lg lg-aux">辅助术语</span>
              </span>
              <a-button size="small" type="link" @click="copy(output)">复制</a-button>
            </a-space>
          </div>
          <pre v-if="isAnnotatedStep && annotations.length" class="io-text annotate-text"><template v-for="(seg, idx) in annotations" :key="idx"><span :class="`ann-${seg.type}`">{{ seg.text }}</span></template></pre>
          <pre v-else class="io-text">{{ output || '-' }}</pre>
        </div>
      </div>

      <!-- 第4/5步：业务片段卡片 -->
      <div v-if="isSegmentStep" class="wb-segments">
        <DebugSegmentCards
          :segments="segmentSource"
          :fields="segmentFields"
          :risk-items="segmentRisks"
          :show-fields="businessCode === 'FIELD_VALIDATE'"
        />
      </div>

      <!-- 规则执行诊断表 -->
      <div class="wb-diag">
        <div class="diag-head">
          <strong>规则执行诊断</strong>
          <span class="muted">called/hit 以后端执行快照为准，配置状态来自当前规则版本</span>
        </div>
        <a-table
          size="small"
          row-key="key"
          :columns="diagColumns"
          :data-source="rows"
          :pagination="false"
          :row-class-name="rowClass"
          class="diag-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'configured'">
              <span class="pill" :class="record.configured === 'yes' ? 'pill-yes' : 'pill-no'">
                {{ record.configured === 'yes' ? 'yes' : 'no' }}
              </span>
            </template>
            <template v-else-if="column.key === 'called'">
              <span v-if="record.called === '-'" class="pill pill-none">-</span>
              <span v-else :class="record.called === 'yes' ? 'pill-yes' : 'pill-no'" class="pill">
                {{ record.called }}
              </span>
            </template>
            <template v-else-if="column.key === 'hit'">
              <span v-if="record.status === 'hit'" class="pill pill-hit">hit</span>
              <span v-else-if="record.status === 'miss'" class="pill pill-miss">miss</span>
              <span v-else-if="record.status === 'missing'" class="pill pill-missing">missing</span>
              <span v-else class="pill pill-none">-</span>
            </template>
          </template>
        </a-table>

        <!-- 底部结论行 -->
        <div class="diag-conclusion" :class="{ 'has-issue': stats.missing > 0 || misses.length > 0 }">
          <span>
            结论：加载规则 {{ stats.loaded }} 条
            <template v-if="stats.called !== '-'"> · 实际调用 {{ stats.called }}</template>
             · 命中 {{ stats.hit }} 条 · 缺失 {{ stats.missing }} 条
          </span>
          <template v-if="stats.missing > 0">
            <span class="conclusion-issue">· {{ stats.missing }} 条执行记录未在当前规则配置中找到（可能来自内置规则版本差异或配置未同步）</span>
          </template>
          <template v-else-if="misses.length > 0">
            <span class="conclusion-note">· {{ misses.length }} 条已配置规则本次未命中</span>
          </template>
        </div>
      </div>
    </template>

    <!-- 未执行空态 -->
    <a-empty v-else description="该步骤尚未执行。请在右侧点击「执行当前规则」运行完整流水线。" :image-style="{ height: '52px' }" />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { message } from 'ant-design-vue'
import type { PipelineStep } from '@/types/conversionPipeline'
import DebugSegmentCards from './DebugSegmentCards.vue'
import {
  BUSINESS_STEPS,
  annotateOutput,
  buildDiagnosis,
  businessStepByCode,
  businessStepForTech,
  businessStepInput,
  businessStepOutput,
  collectConfigured,
  collectObserved,
  stepExecuted,
  techStepsOf,
  type DebugConfigGroups,
  type DiagnosisRow,
} from './debug'

const props = defineProps<{
  businessCode: string
  steps: PipelineStep[]
  config: DebugConfigGroups | null
}>()

const def = computed(() => businessStepByCode(props.businessCode))
const stepIndex = computed(() => {
  const idx = BUSINESS_STEPS.findIndex((item) => item.code === props.businessCode)
  return idx >= 0 ? idx + 1 : '-'
})

const technical = computed(() => techStepsOf(props.steps || [], props.businessCode))
const executed = computed(() => stepExecuted(technical.value))
const input = computed(() => businessStepInput(technical.value))
const output = computed(() => businessStepOutput(technical.value))
const observed = computed(() => collectObserved(technical.value))
const configured = computed(() => collectConfigured(props.config, props.businessCode))

const diagnosis = computed(() => buildDiagnosis(configured.value, observed.value))
const rows = computed<DiagnosisRow[]>(() => diagnosis.value.rows)
const stats = computed(() => diagnosis.value.stats)
const misses = computed(() => rows.value.filter((row) => row.status === 'miss'))

const isAnnotatedStep = computed(() => ['MEDICAL_TERM', 'NUMBER_NORMALIZE'].includes(props.businessCode))
const isSegmentStep = computed(() => ['BUSINESS_SEGMENT', 'FIELD_VALIDATE'].includes(props.businessCode))

const annotations = computed(() =>
  isAnnotatedStep.value ? annotateOutput(output.value, observed.value) : []
)

// 可处理 / 不处理 tags（真实观察记录）
const processableTags = computed(() => tagList(observed.value.map((item) => item.raw).filter(Boolean)))
const processableTagsExtra = computed(() => processableTagsExtraCount(observed.value.map((item) => item.raw).filter(Boolean)))
const unhandledTags = computed(() => {
  if (!input.value) return []
  const others: string[] = []
  ;(props.steps || []).forEach((step) => {
    const def = businessStepForTech(step.step_code)
    if (!def || def.code === props.businessCode) return
    collectObserved([step]).forEach((item) => {
      if (item.raw && input.value.includes(item.raw)) others.push(item.raw)
    })
  })
  return tagList(others)
})
const unhandledTagsExtra = computed(() => {
  if (!input.value) return 0
  const others: string[] = []
  ;(props.steps || []).forEach((step) => {
    const def = businessStepForTech(step.step_code)
    if (!def || def.code === props.businessCode) return
    collectObserved([step]).forEach((item) => {
      if (item.raw && input.value.includes(item.raw)) others.push(item.raw)
    })
  })
  return processableTagsExtraCount(others)
})

// 第4/5步片段来源
const segmentStep = computed<PipelineStep | null>(() => {
  if (!isSegmentStep.value) return null
  if (props.businessCode === 'BUSINESS_SEGMENT') return technical.value[0] || null
  return (props.steps || []).find((step) => step.step_code === 'FIELD_PARSE') || null
})
const segmentSource = computed(() => segmentStep.value?.rule_hits || [])
const segmentFields = computed(() => {
  if (props.businessCode !== 'FIELD_VALIDATE') return {}
  const fieldStep = (props.steps || []).find((step) => step.step_code === 'FIELD_PARSE')
  return fieldStep?.fields || {}
})
const segmentRisks = computed(() => {
  if (props.businessCode !== 'FIELD_VALIDATE') return []
  return (props.steps || [])
    .filter((step) => ['FIELD_PARSE', 'RUNTIME_RULE', 'RISK_INTERCEPT'].includes(step.step_code))
    .flatMap((step) => [...(step.conversions || []), ...(step.rule_hits || [])])
    .filter((item: any) => ['REVIEW', 'BLOCK', 'CANDIDATE'].includes(String(item.action || '').toUpperCase()))
})

const diagColumns = [
  { title: '规则ID', dataIndex: 'rule_id', key: 'rule_id', width: 110 },
  { title: '规则名称', dataIndex: 'rule_name', key: 'rule_name', width: 180, ellipsis: true },
  { title: '已配置', key: 'configured', width: 76 },
  { title: '已调用', key: 'called', width: 76 },
  { title: '命中', key: 'hit', width: 84 },
  { title: '命中文本', dataIndex: 'hit_text', key: 'hit_text', width: 180, ellipsis: true },
  { title: '输出变化', dataIndex: 'output_change', key: 'output_change', width: 200, ellipsis: true },
  { title: '说明', dataIndex: 'note', key: 'note', ellipsis: true },
]

function tagList(values: string[]): string[] {
  const seen = new Set<string>()
  const list: string[] = []
  values.forEach((value) => {
    const text = String(value).trim()
    if (!text || seen.has(text) || list.length >= 8) return
    seen.add(text)
    list.push(text.length > 14 ? `${text.slice(0, 13)}…` : text)
  })
  return list
}

function processableTagsExtraCount(values: string[]): number {
  const seen = new Set<string>()
  values.forEach((value) => {
    const text = String(value).trim()
    if (text) seen.add(text)
  })
  return Math.max(0, seen.size - 8)
}

function rowClass(record: DiagnosisRow) {
  if (record.status === 'missing') return 'row-missing'
  if (record.status === 'miss') return 'row-miss'
  return ''
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text || '')
    message.success('已复制')
  } catch {
    message.error('复制失败，请手动复制')
  }
}
</script>

<style scoped>
.debug-workbench {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px;
  display: grid;
  gap: 12px;
  min-width: 0;
}
.wb-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.wb-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
  display: grid;
  gap: 6px;
  min-width: 0;
}
.wb-tags {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  font-size: 12px;
  font-weight: 400;
  color: #3d4757;
}
.wb-tags-unhandled { color: #7a8494; }
.wb-tags-label { color: #5c6b7a; flex: none; }
.wb-tag { margin-inline-end: 0; font-size: 11px; }
.wb-tags-more { color: #a0a8b4; font-size: 12px; }
.wb-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(64px, 1fr));
  gap: 8px;
  flex: none;
}
.stat-box {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  text-align: center;
  padding: 6px 8px;
  min-width: 64px;
}
.stat-num { font-size: 18px; font-weight: 700; color: #3d4757; line-height: 1.3; }
.stat-num.stat-hit { color: #409eff; }
.stat-num.stat-missing { color: #d54941; }
.stat-label { font-size: 11px; color: #a0a8b4; }
.wb-io {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.io-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px;
  min-width: 0;
  background: #fbfcfe;
}
.io-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 600;
  font-size: 13px;
  color: #3d4757;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.io-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 126px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
  font-size: 13px;
  color: #3d4757;
}
.annotate-text { background: #fff; border: 1px solid #eef2f6; border-radius: 6px; padding: 8px; }
.annotate-legend { display: inline-flex; gap: 4px; flex-wrap: wrap; }
.lg { font-size: 11px; padding: 0 5px; border-radius: 3px; line-height: 16px; }
.lg-anchor { color: #8b5cf6; background: #f5f0ff; }
.lg-standard { color: #409eff; background: #e8f4fd; }
.lg-candidate { color: #b88230; background: #fdf6ec; border: 1px dashed #e0a44f; }
.lg-aux { color: #0e9f9f; background: #e6fbfb; }
.ann-anchor { color: #8b5cf6; background: #f5f0ff; border-radius: 3px; padding: 0 1px; }
.ann-standard { color: #409eff; background: #e8f4fd; border-radius: 3px; padding: 0 1px; }
.ann-candidate { color: #b88230; background: #fdf6ec; border-bottom: 1px dashed #e0a44f; border-radius: 3px; padding: 0 1px; }
.ann-risk { color: #d54941; background: #fef0f0; border-radius: 3px; padding: 0 1px; }
.ann-aux { color: #0e9f9f; background: #e6fbfb; border-radius: 3px; padding: 0 1px; }
.wb-segments { min-width: 0; }
.wb-diag { display: grid; gap: 8px; }
.diag-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.diag-table :deep(.ant-table-cell) { vertical-align: top; }
.diag-table :deep(.row-miss > td) { background: #fdf8f0 !important; }
.diag-table :deep(.row-missing > td) { background: #fef2f2 !important; }
.pill {
  display: inline-block;
  font-size: 11px;
  line-height: 18px;
  padding: 0 7px;
  border-radius: 9px;
  font-weight: 500;
}
.pill-yes { background: #f0f9eb; color: #529b2e; }
.pill-no { background: #f2f3f5; color: #8a919f; }
.pill-none { background: #f2f3f5; color: #b0b6c0; }
.pill-hit { background: #e8f4fd; color: #409eff; }
.pill-miss { background: #fdf6ec; color: #b88230; }
.pill-missing { background: #fef0f0; color: #d54941; }
.diag-conclusion {
  border-top: 1px solid #f0f2f5;
  padding-top: 8px;
  font-size: 12px;
  color: #5c6b7a;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  line-height: 1.6;
}
.conclusion-issue { color: #d54941; }
.conclusion-note { color: #b88230; }
.muted { color: #a0a8b4; font-size: 12px; }
@media (max-width: 1100px) {
  .wb-io { grid-template-columns: 1fr; }
}
</style>
