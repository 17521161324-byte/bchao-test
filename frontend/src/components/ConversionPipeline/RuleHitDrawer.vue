<template>
  <a-drawer
    :open="open"
    :title="title"
    :width="520"
    @close="emit('close')"
  >
    <!-- 规则命中 -->
    <template v-if="type === 'rules'">
      <a-empty v-if="!records.length" description="无命中规则" />
      <div v-else class="hit-item" v-for="(hit, idx) in records" :key="idx">
        <div class="hit-head">
          <a-tag color="blue">{{ hit.rule_id || '-' }}</a-tag>
          <span v-if="hit.rule_name || hit.name" class="hit-name">{{ hit.rule_name || hit.name }}</span>
          <a-tag :color="actionColor(hit.action)">{{ hit.action || '-' }}</a-tag>
          <a-tag v-if="hit.severity || hit.risk_level" :color="severityColor(hit.severity || hit.risk_level)">
            {{ hit.severity || hit.risk_level }}
          </a-tag>
        </div>
        <a-descriptions size="small" :column="1" bordered class="hit-desc">
          <a-descriptions-item v-if="hit.rule_id" label="规则编号">{{ hit.rule_id }}</a-descriptions-item>
          <a-descriptions-item v-if="hit.rule_name || hit.name" label="规则名称">{{ hit.rule_name || hit.name }}</a-descriptions-item>
          <a-descriptions-item v-if="hasValue(hit.raw) || hasValue(hit.raw_text)" label="原文本">
            {{ formatText(hit.raw ?? hit.raw_text) }}
          </a-descriptions-item>
          <a-descriptions-item v-if="hasValue(hit.converted) || hasValue(hit.replacement) || hasValue(hit.normalized)" label="转换后">
            {{ formatText(hit.converted ?? hit.replacement ?? hit.normalized) }}
          </a-descriptions-item>
          <a-descriptions-item v-if="hit.action" label="动作">{{ actionText(hit.action) }}</a-descriptions-item>
          <a-descriptions-item v-if="hasValue(hit.condition) || hasValue(hit.pattern) || hasValue(hit.description)" label="命中条件">
            {{ formatText(hit.condition ?? hit.pattern ?? hit.description) }}
          </a-descriptions-item>
          <a-descriptions-item v-if="hasValue(hit.message)" label="提示">{{ formatText(hit.message) }}</a-descriptions-item>
          <a-descriptions-item label="规则版本">{{ ruleVersionCode || '-' }}</a-descriptions-item>
          <a-descriptions-item label="所在步骤">{{ stepName || '-' }}</a-descriptions-item>
        </a-descriptions>
        <div class="hit-actions">
          <a-button size="small" type="link" @click="viewRule(hit)">查看规则</a-button>
          <a-tooltip :title="tooltipForEdit">
            <a-button size="small" type="link" @click="editRule(hit)">克隆规则版本后修改</a-button>
          </a-tooltip>
        </div>
      </div>
    </template>

    <!-- 警示 -->
    <template v-else-if="type === 'warnings'">
      <a-empty v-if="!records.length" description="无警示" />
      <div v-else class="warn-list">
        <a-alert
          v-for="(item, idx) in records"
          :key="idx"
          type="warning"
          show-icon
          class="warn-item"
          :message="formatWarning(item)"
        />
      </div>
    </template>

    <!-- 字段变化 -->
    <template v-else>
      <a-empty v-if="!records.length" description="无字段变化" />
      <a-table
        v-else
        size="small"
        row-key="key"
        :columns="fieldColumns"
        :data-source="records"
        :pagination="false"
      />
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps<{
  open: boolean
  type: 'rules' | 'warnings' | 'fields'
  records: Record<string, any>[]
  ruleVersionId?: number | null
  ruleVersionCode?: string
  versionStatus?: string
  stepName?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const router = useRouter()

const title = computed(() => ({
  rules: `命中规则（${props.records.length}）`,
  warnings: `警示（${props.records.length}）`,
  fields: `字段变化（${props.records.length}）`,
}[props.type] || '详情'))

const fieldColumns = [
  { title: '字段', dataIndex: 'label', key: 'label', width: 160 },
  { title: '值', dataIndex: 'value', key: 'value' },
]

const tooltipForEdit = computed(() => {
  if (props.versionStatus === 'published') return '已发布版本只读，请到转化配置中克隆版本后再修改'
  return '跳转到转化配置编辑该规则版本'
})

function hasValue(value: any) {
  return value !== null && value !== undefined && value !== ''
}

function formatText(value: any) {
  return value === null || value === undefined || value === '' ? '-' : String(value)
}

function formatWarning(item: any) {
  if (typeof item === 'string') return item
  if (item && item.message) return item.message
  return JSON.stringify(item)
}

function actionColor(action: string) {
  return ({ AUTO: 'green', CANDIDATE: 'blue', REVIEW: 'orange', BLOCK: 'red' } as any)[action] || 'default'
}

function severityColor(level: string) {
  return ({ low: 'default', medium: 'blue', high: 'orange', highest: 'red' } as any)[level] || 'default'
}

function actionText(action: string) {
  return ({ AUTO: 'AUTO 自动转换', CANDIDATE: 'CANDIDATE 候选', REVIEW: 'REVIEW 需复核', BLOCK: 'BLOCK 阻断' } as any)[action] || action
}

function ruleCodeOf(hit: Record<string, any>) {
  return String(hit.rule_id ?? hit.rule_code ?? '')
}

function viewRule(hit: Record<string, any>) {
  const ruleCode = ruleCodeOf(hit)
  if (!ruleCode) return
  router.push({
    path: '/conversion-config',
    query: {
      version_id: String(props.ruleVersionId ?? ''),
      rule_code: ruleCode,
    },
  })
}

function editRule(hit: Record<string, any>) {
  const ruleCode = ruleCodeOf(hit)
  router.push({
    path: '/conversion-config',
    query: ruleCode
      ? { version_id: String(props.ruleVersionId ?? ''), rule_code: ruleCode }
      : { version_id: String(props.ruleVersionId ?? '') },
  })
}
</script>

<style scoped>
.hit-item {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 10px;
}
.hit-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.hit-name { font-weight: 600; font-size: 13px; }
.hit-desc { margin-bottom: 4px; }
.hit-desc :deep(.ant-descriptions-item-label) {
  width: 90px;
  color: #888;
}
.hit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}
.warn-list { display: grid; gap: 8px; }
.warn-item { margin-bottom: 0; }
</style>
