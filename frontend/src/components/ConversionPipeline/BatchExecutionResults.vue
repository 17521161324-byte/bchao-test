<template>
  <section class="panel batch-results">
    <div class="batch-head">
      <div>
        <strong>批量执行结果</strong>
        <span class="muted">真实历史 ASR 批量执行，可点击任一结果进入五步诊断</span>
      </div>
      <a-space wrap>
        <a-tag color="green">成功 {{ executions.length }}</a-tag>
        <a-tag v-if="errors.length" color="red">跳过/失败 {{ errors.length }}</a-tag>
      </a-space>
    </div>
    <a-table size="small" row-key="id" :columns="columns" :data-source="executions" :pagination="{ pageSize: 8, showSizeChanger: false }">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'level'">
          <a-tag :color="levelColor(record.result_level)">{{ levelLabel(record.result_level) }}</a-tag>
        </template>
        <template v-else-if="column.key === 'fingerprint'">
          <code>{{ shortHash(record.source_config_hash) }}</code>
        </template>
        <template v-else-if="column.key === 'ops'">
          <a-button size="small" type="link" @click="$emit('open', record)">查看诊断</a-button>
        </template>
      </template>
    </a-table>
    <a-collapse v-if="errors.length" ghost>
      <a-collapse-panel key="errors" :header="`查看 ${errors.length} 条未执行记录`">
        <div v-for="(item, idx) in errors" :key="idx" class="error-row">
          <code>ASR结果ID {{ item.source_id }}</code><span>{{ item.error || item.message || '未执行' }}</span>
        </div>
      </a-collapse-panel>
    </a-collapse>
  </section>
</template>

<script setup lang="ts">
import type { PipelineExecution } from '@/types/conversionPipeline'

defineProps<{
  executions: PipelineExecution[]
  errors: Record<string, any>[]
}>()

defineEmits<{
  (e: 'open', execution: PipelineExecution): void
}>()

const columns = [
  { title: '执行ID', dataIndex: 'id', key: 'id', width: 82 },
  { title: 'ASR结果ID', dataIndex: 'source_id', key: 'source_id', width: 100 },
  { title: '病历号', dataIndex: 'source_record_id', key: 'source_record_id', width: 120 },
  { title: '日期', dataIndex: 'source_date', key: 'source_date', width: 100 },
  { title: '指纹', key: 'fingerprint', width: 150 },
  { title: '结果等级', key: 'level', width: 120 },
  { title: '操作', key: 'ops', width: 100 },
]

function shortHash(value?: string | null) { return value ? (value.length > 16 ? `${value.slice(0, 14)}…` : value) : '-' }
function levelColor(value?: string | null) { return value === 'MANUAL_AUDIO_REVIEW' ? 'red' : value === 'REVIEW_REQUIRED' ? 'orange' : 'green' }
function levelLabel(value?: string | null) { return value === 'MANUAL_AUDIO_REVIEW' ? '需回听' : value === 'REVIEW_REQUIRED' ? '需复核' : value === 'AUTO_ACCEPT' ? '自动接受' : (value || '-') }
</script>

<style scoped>
.batch-results { display: grid; gap: 10px; }
.batch-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.batch-head > div:first-child { display: grid; gap: 3px; }
.muted { color: #8c8c8c; font-size: 12px; }
.error-row { display: flex; gap: 10px; padding: 4px 0; }
</style>
