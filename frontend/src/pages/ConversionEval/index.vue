<template>
  <div class="conversion-page">
    <a-card>
      <template #title>
        <a-space direction="vertical" :size="2">
          <span>ASR 转化评估</span>
          <span class="sub-title">批次评估工作台：按批次组织检查记录，逐条审校转化效果</span>
        </a-space>
      </template>
      <template #extra>
        <a-space>
          <a-button @click="loadBatches" :loading="loading">刷新</a-button>
          <a-button type="primary" @click="openCreateModal">新建批次</a-button>
        </a-space>
      </template>

      <a-table
        row-key="id"
        size="small"
        :columns="columns"
        :data-source="batches"
        :loading="loading"
        :pagination="{ pageSize: 20, showSizeChanger: true }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'dates'">
            {{ (record.selected_dates || []).join(', ') || '-' }}
          </template>
          <template v-else-if="column.key === 'asr_source'">
            <a-tag v-if="record.asr_source_type === 'config_hash'" color="purple">指纹 {{ (record.asr_config_hash || '').slice(0, 8) }}</a-tag>
            <a-tag v-else color="blue">最新成功 ASR</a-tag>
          </template>
          <template v-else-if="column.key === 'accuracy'">
            <a-tag :color="accuracyColor(record.average_accuracy)">{{ percent(record.average_accuracy) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'records'">
            {{ record.reviewed_count || 0 }} / {{ record.record_count || 0 }}
          </template>
          <template v-else-if="column.key === 'status_count'">
            <a-space :size="4">
              <a-tag color="green">成功 {{ record.success_count || 0 }}</a-tag>
              <a-tag :color="record.failed_count ? 'red' : 'default'">失败 {{ record.failed_count || 0 }}</a-tag>
            </a-space>
          </template>
          <template v-else-if="column.key === 'created'">{{ formatTime(record.created_at) }}</template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="enterBatch(record.id)">进入</a-button>
              <a-popconfirm title="确认删除该批次及其评估记录？" @confirm="deleteBatch(record.id)">
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 新建批次弹窗 -->
    <a-modal v-model:open="createModalOpen" title="新建批次" :width="960" :footer="null" :destroy-on-close="true">
      <a-space direction="vertical" style="width: 100%" :size="12">
        <a-input v-model:value="createForm.name" placeholder="批次名称，如 20260622 豆包热词转化评估" />

        <a-row :gutter="12">
          <a-col :span="8">
            <a-select
              v-model:value="createForm.selected_dates"
              mode="multiple"
              allow-clear
              style="width: 100%"
              placeholder="选择日期"
              :options="batchDateOptions"
              @change="loadCandidateRecords"
            />
          </a-col>
          <a-col :span="6">
            <a-radio-group v-model:value="createForm.asr_source_type" @change="loadCandidateRecords">
              <a-radio-button value="latest_success">最新成功 ASR</a-radio-button>
              <a-radio-button value="config_hash">指定优化评估指纹</a-radio-button>
            </a-radio-group>
          </a-col>
          <a-col :span="6" v-if="createForm.asr_source_type === 'config_hash'">
            <a-select
              v-model:value="createForm.asr_config_hash"
              allow-clear
              show-search
              style="width: 100%"
              placeholder="选择历史指纹"
              :options="configHashOptions"
              :filter-option="(input: string, option: any) => option.value.toLowerCase().includes(input.toLowerCase())"
              @change="loadCandidateRecords"
            />
          </a-col>
          <a-col :span="4">
            <a-button type="primary" :disabled="!selectedExamIds.length" :loading="creating" @click="submitBatch">
              创建批次 ({{ selectedExamIds.length }})
            </a-button>
          </a-col>
        </a-row>

        <a-row :gutter="12" align="middle">
          <a-col :span="10">
            <a-input-search v-model:value="candidateSearchKeyword" allow-clear placeholder="搜索病历号" />
          </a-col>
          <a-col :span="6">
            <a-space>
              <a-button size="small" @click="toggleSelectAll">{{ selectedExamIds.length ? '取消全选' : '全选' }}</a-button>
              <span style="color: #888; font-size: 12px">已选 {{ selectedExamIds.length }} / {{ filteredCandidates.length }}</span>
            </a-space>
          </a-col>
        </a-row>

        <a-table
          row-key="id"
          size="small"
          :columns="candidateColumns"
          :data-source="filteredCandidates"
          :loading="loadingCandidates"
          :pagination="{ pageSize: 15, showSizeChanger: true, size: 'small' }"
          :row-selection="{ selectedRowKeys: selectedExamIds, onChange: (keys: number[]) => selectedExamIds = keys }"
          :scroll="{ y: 380 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'has_asr'">
              <a-tag :color="record.has_success_asr ? 'green' : 'red'">{{ record.has_success_asr ? '有' : '无' }}</a-tag>
            </template>
            <template v-else-if="column.key === 'has_reference'">
              <a-tag :color="record.has_reference ? 'green' : 'default'">{{ record.has_reference ? '有' : '无' }}</a-tag>
            </template>
            <template v-else-if="column.key === 'asr_detail'">
              <span v-if="record.has_success_asr" style="font-size: 11px; color: #888">
                {{ record.latest_asr_model || '-' }}
              </span>
              <span v-else style="font-size: 11px; color: #ccc">-</span>
            </template>
          </template>
        </a-table>
      </a-space>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { conversionEvalApi, audioApi, asrOptimizationApi, patientApi } from '@/api/client'

const router = useRouter()
const loading = ref(false)
const batches = ref<any[]>([])

const columns = [
  { title: '批次名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '日期', key: 'dates' },
  { title: 'ASR 来源', key: 'asr_source', width: 180 },
  { title: '规则版本', dataIndex: 'conversion_version', key: 'conversion_version', width: 100 },
  { title: '执行结果', key: 'status_count', width: 190 },
  { title: '已审校/总数', key: 'records', width: 120 },
  { title: '平均准确率', key: 'accuracy', width: 120 },
  { title: '创建时间', key: 'created', width: 170 },
  { title: '操作', key: 'action', fixed: 'right', width: 130 },
]

const candidateColumns = [
  { title: '病历号', dataIndex: 'record_id', key: 'record_id', width: 120 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 110 },
  { title: '成功 ASR', key: 'has_asr', width: 100 },
  { title: 'ASR 模型', key: 'asr_detail', width: 140 },
  { title: '专家标准 ASR', key: 'has_reference', width: 110 },
]

// 新建批次
const createModalOpen = ref(false)
const creating = ref(false)
const loadingCandidates = ref(false)
const batchDateOptions = ref<any[]>([])
const configHashOptions = ref<any[]>([])
const candidateSearchKeyword = ref('')
const candidates = ref<any[]>([])
const selectedExamIds = ref<number[]>([])
const createForm = reactive<any>({
  name: '',
  selected_dates: [],
  asr_source_type: 'latest_success',
  asr_config_hash: undefined,
  conversion_version: 'manual',
})

const filteredCandidates = computed(() => {
  if (!candidateSearchKeyword.value) return candidates.value
  const kw = candidateSearchKeyword.value.toLowerCase()
  return candidates.value.filter((r: any) => (r.record_id || '').toLowerCase().includes(kw))
})

loadBatches()

async function loadBatches() {
  loading.value = true
  try {
    batches.value = await conversionEvalApi.listBatches() as any[]
  } finally {
    loading.value = false
  }
}

async function openCreateModal() {
  createModalOpen.value = true
  Object.assign(createForm, {
    name: '',
    selected_dates: [],
    asr_source_type: 'latest_success',
    asr_config_hash: undefined,
    conversion_version: 'manual',
  })
  candidateSearchKeyword.value = ''
  selectedExamIds.value = []
  candidates.value = []
  // 加载日期选项
  const batches: any[] = await audioApi.getBatches()
  batchDateOptions.value = [
    { label: '全部', value: '__all__' },
    ...batches.map((b: any) => ({ label: `${b.date} (${b.patient_count}条)`, value: b.date })),
  ]
  // 加载指纹选项（历史优化评估方案）
  try {
    const plans: any[] = await asrOptimizationApi.listPlans()
    configHashOptions.value = (plans || []).map((p: any) => ({
      label: `${p.name || p.config_hash}`,
      value: p.config_hash,
    }))
  } catch {
    configHashOptions.value = []
  }
}

async function loadCandidateRecords() {
  let dates = createForm.selected_dates || []
  if (dates.includes('__all__')) {
    const batches: any[] = await audioApi.getBatches()
    dates = batches.map((b: any) => b.date)
    createForm.selected_dates = dates
  }
  if (!dates.length) {
    candidates.value = []
    selectedExamIds.value = []
    return
  }
  loadingCandidates.value = true
  selectedExamIds.value = []
  try {
    const allRecords: any[] = []
    for (const date of dates) {
      const records: any[] = await audioApi.getRecords(date).catch(() => [])
      allRecords.push(...records)
    }
    const examIds = allRecords.map((r: any) => r.id)
    if (!examIds.length) {
      candidates.value = []
      return
    }
    const [asrResultsMap, asrRefsMap] = await Promise.all([
      patientApiListAsrResultsBatch(examIds).catch(() => ({})),
      patientApiListAsrReferencesBatch(examIds).catch(() => ({})),
    ])
    const filterByHash = createForm.asr_source_type === 'config_hash' && !!createForm.asr_config_hash
    candidates.value = allRecords.map((r: any) => {
      const asrList: any[] = (asrResultsMap as any)[String(r.id)] || []
      const successAsr = asrList.find((a: any) => {
        if (a.status !== 'success' || !a.full_transcript) return false
        if (filterByHash) return a.config_hash === createForm.asr_config_hash
        return true
      })
      return {
        ...r,
        has_success_asr: !!successAsr,
        latest_asr_model: successAsr?.asr_model_name || asrList[0]?.asr_model_name || null,
        has_reference: !!((asrRefsMap as any)[String(r.id)]?.length),
      }
    })
  } finally {
    loadingCandidates.value = false
  }
}

// 复用 client 中的批量接口（直接导入避免依赖其他 api 命名）
async function patientApiListAsrResultsBatch(ids: number[]) { return patientApi.listAsrResultsBatch(ids) }
async function patientApiListAsrReferencesBatch(ids: number[]) { return patientApi.listAsrReferencesBatch(ids) }

function toggleSelectAll() {
  const enabledIds = filteredCandidates.value.map((r: any) => r.id)
  if (selectedExamIds.value.length) {
    selectedExamIds.value = []
  } else {
    selectedExamIds.value = enabledIds
  }
}

async function submitBatch() {
  if (!selectedExamIds.value.length) {
    message.warning('请选择检查记录')
    return
  }
  if (!createForm.name.trim()) {
    message.warning('请填写批次名称')
    return
  }
  if (createForm.asr_source_type === 'config_hash' && !createForm.asr_config_hash) {
    message.warning('请选择或输入 ASR 指纹')
    return
  }
  creating.value = true
  try {
    const result: any = await conversionEvalApi.createBatch({
      name: createForm.name,
      selected_dates: createForm.selected_dates,
      exam_record_ids: selectedExamIds.value,
      asr_source_type: createForm.asr_source_type,
      asr_config_hash: createForm.asr_source_type === 'config_hash' ? createForm.asr_config_hash : undefined,
      conversion_version: createForm.conversion_version,
    })
    const msg = `创建 ${result.created_count} 条，跳过 ${result.skipped_count} 条，失败 ${result.failed_count} 条`
    if (result.created_count > 0) {
      message.success(msg)
    } else if (result.skipped_count > 0) {
      message.warning(msg)
    } else {
      message.info(msg)
    }
    createModalOpen.value = false
    await loadBatches()
  } finally {
    creating.value = false
  }
}

async function deleteBatch(id: number) {
  await conversionEvalApi.deleteBatch(id)
  message.success('批次已删除')
  await loadBatches()
}

function enterBatch(id: number) {
  router.push(`/conversion-eval/batches/${id}`)
}

function accuracyColor(value: any) {
  const num = Number(value || 0)
  if (num >= 0.9) return 'green'
  if (num >= 0.7) return 'orange'
  return 'red'
}

function percent(value: any) {
  const num = Number(value || 0)
  return `${(num * 100).toFixed(1)}%`
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}
</script>

<style scoped>
.conversion-page { width: 100%; min-width: 0; }
.sub-title { color: #888; font-size: 12px; font-weight: 400; }
</style>
