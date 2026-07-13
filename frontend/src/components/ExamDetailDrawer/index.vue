<template>
  <a-drawer :open="visible" title="检查记录详情" placement="right" width="90vw" @close="onClose">
    <template v-if="data">
      <!-- 基础信息 -->
      <a-descriptions :column="4" bordered size="small" style="margin-bottom: 16px">
        <a-descriptions-item label="病历号">{{ data.record_id }}</a-descriptions-item>
        <a-descriptions-item label="检查日期">{{ data.date }}</a-descriptions-item>
        <a-descriptions-item label="录音分段">{{ data.segs_count }} 段</a-descriptions-item>
        <a-descriptions-item label="B 超结果">
          <a-tag :color="data.has_ground_truth ? 'green' : 'default'">{{ data.has_ground_truth ? '有' : '无' }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item v-if="data.experiment" label="实验名称" :span="2">{{ data.experiment.batch_name }}</a-descriptions-item>
        <a-descriptions-item v-if="data.experiment" label="任务状态">
          <a-tag :color="statusColor(data.experiment.task_status)">{{ data.experiment.task_status }}</a-tag>
        </a-descriptions-item>
      </a-descriptions>

      <!-- 错误提示 -->
      <a-alert v-if="data.llm.error_message" type="error" :message="data.llm.error_message" show-icon style="margin-bottom: 16px" />

      <!-- ASR + LLM 并行布局 -->
      <a-row :gutter="16" style="margin-bottom: 16px">
        <!-- 左侧：ASR -->
        <a-col :span="12">
          <a-card size="small" style="height: 100%">
            <template #title>
              <span>语音转写 (ASR)</span>
              <a-tag v-if="data.asr.model_name" color="blue" style="margin-left: 8px">{{ data.asr.model_name }}</a-tag>
            </template>
            <template #extra>
              <a-tag v-if="data.asr.asr_source === 'reused'" color="blue">复用</a-tag>
              <a-tag v-else-if="data.asr.asr_source === 'generated'" color="green">新生成</a-tag>
              <a-tag v-else-if="data.asr.asr_source === 'failed'" color="red">失败</a-tag>
              <a-tag v-else color="default">{{ data.asr.status || 'pending' }}</a-tag>
            </template>
            <div class="text-box">{{ data.asr.full_transcript || '(无转写结果)' }}</div>
          </a-card>
        </a-col>
        <!-- 右侧：LLM -->
        <a-col :span="12">
          <a-card size="small" style="height: 100%">
            <template #title>
              <span>LLM 结构化提取</span>
              <a-tag v-if="data.llm.model_name" color="purple" style="margin-left: 8px">{{ data.llm.model_name }}</a-tag>
            </template>
            <template #extra>
              <a-tag v-if="data.llm.accuracy != null" :color="data.llm.accuracy >= 0.8 ? 'green' : 'orange'">
                {{ (data.llm.accuracy * 100).toFixed(0) }}%
              </a-tag>
              <a-tag :color="statusColor(data.llm.status)">{{ data.llm.status }}</a-tag>
            </template>
            <template v-if="data.llm.status === 'success'">
              <div v-if="data.llm.summary_text" style="margin-bottom: 12px">
                <div style="font-weight: 600; margin-bottom: 4px">总结</div>
                <div class="text-box small">{{ data.llm.summary_text }}</div>
              </div>
              <div v-if="data.llm.structured_result && typeof data.llm.structured_result === 'object'">
                <div style="font-weight: 600; margin-bottom: 4px">结构化结果</div>
                <pre class="code-box small">{{ JSON.stringify(data.llm.structured_result, null, 2) }}</pre>
              </div>
              <a-empty v-else description="无结构化结果" />
            </template>
            <a-empty v-else :description="data.llm.error_message || 'LLM 未执行或执行失败'" />
          </a-card>
        </a-col>
      </a-row>

      <!-- 卵泡明细 + B 超并行对比 -->
      <a-divider>结果对比</a-divider>
      <a-row :gutter="16" style="margin-bottom: 16px">
        <!-- 左侧：LLM 提取 -->
        <a-col :span="12">
          <a-card size="small" title="LLM 提取结果">
            <a-row :gutter="12" style="margin-bottom: 12px">
              <a-col :span="12">
                <a-card size="small" title="右侧卵泡" style="margin-bottom: 8px">
                  <div class="highlight-num">
                    {{ data.llm.structured_result?.right_follicle_total ?? '-' }}
                    <CheckCircleOutlined v-if="getFieldResult('right_follicle_total') === 'match'" style="color: #52c41a; margin-left: 4px" />
                    <CloseCircleOutlined v-else-if="getFieldResult('right_follicle_total') === 'mismatch'" style="color: #ff4d4f; margin-left: 4px" />
                  </div>
                  <div class="follicle-list">
                    <span v-for="(f, i) in rightFollicleCompare" :key="'r'+i" class="follicle-item" :class="'status-' + f.status">
                      {{ f.size }}×{{ f.count }}
                    </span>
                    <span v-if="!rightFollicleCompare.length" class="muted">-</span>
                  </div>
                </a-card>
              </a-col>
              <a-col :span="12">
                <a-card size="small" title="左侧卵泡" style="margin-bottom: 8px">
                  <div class="highlight-num">
                    {{ data.llm.structured_result?.left_follicle_total ?? '-' }}
                    <CheckCircleOutlined v-if="getFieldResult('left_follicle_total') === 'match'" style="color: #52c41a; margin-left: 4px" />
                    <CloseCircleOutlined v-else-if="getFieldResult('left_follicle_total') === 'mismatch'" style="color: #ff4d4f; margin-left: 4px" />
                  </div>
                  <div class="follicle-list">
                    <span v-for="(f, i) in leftFollicleCompare" :key="'l'+i" class="follicle-item" :class="'status-' + f.status">
                      {{ f.size }}×{{ f.count }}
                    </span>
                    <span v-if="!leftFollicleCompare.length" class="muted">-</span>
                  </div>
                </a-card>
              </a-col>
            </a-row>
            <a-descriptions :column="2" size="small">
              <a-descriptions-item label="内膜厚度">
                <span :style="{ color: getFieldResult('endometrium_thickness') === 'mismatch' ? '#ff4d4f' : '#333' }">
                  {{ displayVal(data.llm.structured_result?.endometrium_thickness) }}
                </span>
              </a-descriptions-item>
              <a-descriptions-item label="内膜类型">
                <span :style="{ color: getFieldResult('endometrium_type') === 'mismatch' ? '#ff4d4f' : '#333' }">
                  {{ displayVal(data.llm.structured_result?.endometrium_type) }}
                </span>
              </a-descriptions-item>
              <a-descriptions-item label="右卵巢">{{ fmtOvary(data.llm.structured_result?.right_ovary_length, data.llm.structured_result?.right_ovary_width) }}</a-descriptions-item>
              <a-descriptions-item label="左卵巢">{{ fmtOvary(data.llm.structured_result?.left_ovary_length, data.llm.structured_result?.left_ovary_width) }}</a-descriptions-item>
              <a-descriptions-item label="备注" :span="2">{{ displayVal(data.llm.structured_result?.remark) }}</a-descriptions-item>
            </a-descriptions>
          </a-card>
        </a-col>
        <!-- 右侧：真实 B 超 -->
        <a-col :span="12">
          <a-card v-if="data.has_ground_truth" size="small" title="B 超检查结果">
            <a-row :gutter="12" style="margin-bottom: 12px">
              <a-col :span="12">
                <a-card size="small" title="右侧卵泡" style="margin-bottom: 8px">
                  <div class="highlight-num">{{ data.ground_truth.right_follicle_total ?? '-' }}</div>
                  <div class="follicle-list">
                    <span v-for="(f, i) in rightGtFollicles" :key="'rg'+i" class="follicle-item" :class="rightFollicleStatus(f.size)">
                      {{ f.size }}×{{ f.count }}
                    </span>
                    <span v-if="!rightGtFollicles.length" class="muted">-</span>
                  </div>
                </a-card>
              </a-col>
              <a-col :span="12">
                <a-card size="small" title="左侧卵泡" style="margin-bottom: 8px">
                  <div class="highlight-num">{{ data.ground_truth.left_follicle_total ?? '-' }}</div>
                  <div class="follicle-list">
                    <span v-for="(f, i) in leftGtFollicles" :key="'lg'+i" class="follicle-item" :class="leftFollicleStatus(f.size)">
                      {{ f.size }}×{{ f.count }}
                    </span>
                    <span v-if="!leftGtFollicles.length" class="muted">-</span>
                  </div>
                </a-card>
              </a-col>
            </a-row>
            <a-descriptions :column="2" size="small">
              <a-descriptions-item label="内膜厚度">{{ displayVal(data.ground_truth.endometrium_thickness) }}</a-descriptions-item>
              <a-descriptions-item label="内膜类型">{{ displayVal(data.ground_truth.endometrium_type) }}</a-descriptions-item>
              <a-descriptions-item label="右卵巢">{{ fmtOvary(data.ground_truth.right_ovary_length, data.ground_truth.right_ovary_width) }}</a-descriptions-item>
              <a-descriptions-item label="左卵巢">{{ fmtOvary(data.ground_truth.left_ovary_length, data.ground_truth.left_ovary_width) }}</a-descriptions-item>
              <a-descriptions-item label="备注" :span="2">{{ displayVal(data.ground_truth.remark) }}</a-descriptions-item>
            </a-descriptions>
          </a-card>
          <a-card v-else size="small">
            <a-empty description="该检查记录无 B 超结果" />
          </a-card>
        </a-col>
      </a-row>

      <!-- 字段对比表 -->
      <a-divider>字段对比</a-divider>
      <a-table :data-source="fieldCompare" size="small" row-key="field" :pagination="false" bordered>
        <a-table-column title="字段" data-index="field" />
        <a-table-column title="真实值" data-index="truth" />
        <a-table-column title="LLM 提取值" data-index="extracted" />
        <a-table-column title="结果" :width="100" align="center">
          <template #default="scope">
            <a-tag v-if="scope?.record?.result === 'match'" color="green">✓</a-tag>
            <a-tag v-else-if="scope?.record?.result === 'mismatch'" color="red">✗</a-tag>
            <a-tag v-else color="default">-</a-tag>
          </template>
        </a-table-column>
      </a-table>

      <!-- 缺失字段提示 -->
      <a-alert v-if="data.llm.missing_fields && data.llm.missing_fields.length" type="warning" :message="`LLM 返回缺少目标字段: ${data.llm.missing_fields.join(', ')}`" show-icon style="margin-top: 16px" />

      <!-- LLM 原始返回（调试用，可折叠） -->
      <a-collapse style="margin-top: 16px" v-if="data.llm.raw_output">
        <a-collapse-panel key="raw" header="LLM 原始返回">
          <pre class="code-box">{{ data.llm.raw_output }}</pre>
        </a-collapse-panel>
      </a-collapse>
    </template>
  </a-drawer>
</template>

<script lang="ts">
import { computed } from 'vue'
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'

export interface ExamDetailData {
  record_id: string
  date: string
  segs_count: number
  has_ground_truth: boolean
  asr: {
    model_name: string
    full_transcript: string
    status: string
    asr_source: string
  }
  llm: {
    model_name: string
    summary_text: string
    structured_result: any
    raw_output: string
    prompt_template_name: string
    accuracy: number | null
    status: string
    error_message: string
    missing_fields: string[]
  }
  ground_truth: any
  experiment?: {
    batch_name: string
    task_status: string
  }
}

const TARGET_FIELDS = [
  'right_follicle_total', 'left_follicle_total',
  'endometrium_thickness', 'endometrium_type',
  'right_ovary_length', 'right_ovary_width',
  'left_ovary_length', 'left_ovary_width',
]

function compareField(realValue: any, extractedValue: any): 'match' | 'mismatch' | 'empty' {
  if (realValue == null && extractedValue == null) return 'empty'
  if (realValue == null || extractedValue == null) return 'empty'
  const a = String(realValue).trim()
  const b = String(extractedValue).trim()
  if (a === '' && b === '') return 'empty'
  if (a === '' || b === '') return 'empty'
  return a === b ? 'match' : 'mismatch'
}

function formatFollicles(follicles: any): string {
  if (!follicles || !Array.isArray(follicles) || !follicles.length) return '-'
  return follicles.map((f: any) => `${f.size ?? '?'}×${f.count ?? '?'}`).join('  ')
}

// 对比单个卵泡：返回 { size, count, status: 'match' | 'mismatch' | 'missing' }
function compareFollicles(llmFollicles: any[], gtFollicles: any[]): { size: string; count: number; status: string; llm: boolean; gt: boolean }[] {
  const result: { size: string; count: number; status: string; llm: boolean; gt: boolean }[] = []
  if (!Array.isArray(llmFollicles) && !Array.isArray(gtFollicles)) return result

  const llmList: any[] = Array.isArray(llmFollicles) ? llmFollicles : []
  const gtList: any[] = Array.isArray(gtFollicles) ? gtFollicles : []

  // 按 size 建立 ground truth 的查找映射
  const gtBySize: Record<string, number> = {}
  for (const f of gtList) {
    const s = String(f.size).trim()
    gtBySize[s] = (gtBySize[s] || 0) + (f.count || 1)
  }
  const gtUsed: Record<string, number> = {}

  // 检查每个 LLM 卵泡
  for (const f of llmList) {
    const s = String(f.size).trim()
    const c = f.count || 1
    const gtCount = gtBySize[s] || 0
    const used = gtUsed[s] || 0
    let status = 'mismatch'
    if (gtCount === c) {
      status = 'match'
    } else if (gtCount > used) {
      status = 'partial'
    }
    gtUsed[s] = used + c
    result.push({ size: s, count: c, status, llm: true, gt: gtCount > 0 })
  }

  // 检查 ground truth 中未匹配的卵泡
  for (const f of gtList) {
    const s = String(f.size).trim()
    const c = f.count || 1
    const matched = result.filter((r) => r.size === s && r.status === 'match').length
    if (matched === 0) {
      result.push({ size: s, count: c, status: 'missing', llm: false, gt: true })
    }
  }

  return result
}

export default {
  name: 'ExamDetailDrawer',
  components: { CheckCircleOutlined, CloseCircleOutlined },
  props: {
    visible: { type: Boolean, default: false },
    data: { type: Object as () => ExamDetailData | null, default: null },
  },
  emits: ['close'],
  setup(props, { emit }) {
    function onClose() { emit('close') }

    function statusColor(status: string): string {
      if (status === 'success' || status === 'reused' || status === 'generated') return 'green'
      if (status === 'failed' || status === 'error') return 'red'
      if (status === 'running') return 'blue'
      return 'default'
    }

    function displayVal(v: any): string {
      if (v == null) return '-'
      return String(v)
    }

    function fmtOvary(len: any, wid: any): string {
      if (len == null && wid == null) return '-'
      return `${len ?? '-'} × ${wid ?? '-'}`
    }

    function getFieldResult(field: string): string {
      const d = props.data
      if (!d) return 'empty'
      const real = d.ground_truth?.[field]
      const extracted = d.llm?.structured_result?.[field]
      return compareField(real, extracted)
    }

    const fieldCompare = computed(() => {
      const d = props.data
      if (!d) return []
      return TARGET_FIELDS.map((field) => {
        const real = d.ground_truth?.[field]
        const extracted = d.llm?.structured_result?.[field]
        const fieldLabels: Record<string, string> = {
          right_follicle_total: '右卵泡',
          left_follicle_total: '左卵泡',
          endometrium_thickness: '内膜厚度',
          endometrium_type: '内膜类型',
          right_ovary_length: '右卵巢长',
          right_ovary_width: '右卵巢宽',
          left_ovary_length: '左卵巢长',
          left_ovary_width: '左卵巢宽',
        }
        return {
          field: fieldLabels[field] || field,
          truth: real != null ? String(real) : '-',
          extracted: extracted != null ? String(extracted) : '-',
          result: compareField(real, extracted),
        }
      })
    })

    const rightFollicleCompare = computed(() => {
      if (!props.data) return []
      return compareFollicles(props.data.llm?.structured_result?.right_follicles, props.data.ground_truth?.right_follicles)
    })

    const leftFollicleCompare = computed(() => {
      if (!props.data) return []
      return compareFollicles(props.data.llm?.structured_result?.left_follicles, props.data.ground_truth?.left_follicles)
    })

    const rightGtFollicles = computed(() => {
      const gt = props.data?.ground_truth?.right_follicles
      return Array.isArray(gt) ? gt : []
    })

    const leftGtFollicles = computed(() => {
      const gt = props.data?.ground_truth?.left_follicles
      return Array.isArray(gt) ? gt : []
    })

    // 用于 ground truth 侧的卵泡颜色
    function rightFollicleStatus(size: string): string {
      if (!props.data) return ''
      const llmList: any[] = props.data.llm?.structured_result?.right_follicles || []
      const found = llmList.find((f: any) => String(f.size).trim() === String(size).trim())
      return found ? 'status-match' : 'status-mismatch'
    }

    function leftFollicleStatus(size: string): string {
      if (!props.data) return ''
      const llmList: any[] = props.data.llm?.structured_result?.left_follicles || []
      const found = llmList.find((f: any) => String(f.size).trim() === String(size).trim())
      return found ? 'status-match' : 'status-mismatch'
    }

    return { onClose, statusColor, displayVal, fmtOvary, formatFollicles, getFieldResult, fieldCompare, rightFollicleCompare, leftFollicleCompare, rightGtFollicles, leftGtFollicles, rightFollicleStatus, leftFollicleStatus }
  },
}
</script>

<style scoped>
.text-box { background: #f5f5f5; padding: 12px; border-radius: 6px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; font-size: 13px; line-height: 1.7; }
.text-box.small { max-height: 200px; font-size: 12px; }
.code-box { background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; }
.code-box.small { max-height: 200px; font-size: 11px; }
.highlight-num { font-size: 22px; font-weight: bold; }
.muted { color: #666; font-size: 12px; margin-top: 4px; }
.follicle-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.follicle-item {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  background: #f5f5f5;
  border: 1px solid #d9d9d9;
}
.follicle-item.status-match {
  color: #52c41a;
  background: #f6ffed;
  border-color: #b7eb8f;
}
.follicle-item.status-mismatch {
  color: #ff4d4f;
  background: #fff2f0;
  border-color: #ffccc7;
}
.follicle-item.status-partial {
  color: #faad14;
  background: #fffbe6;
  border-color: #ffe58f;
}
.follicle-item.status-missing {
  color: #ff4d4f;
  background: #fff2f0;
  border-color: #ffccc7;
  text-decoration: line-through;
}
</style>
