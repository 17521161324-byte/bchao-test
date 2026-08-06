<template>
  <div class="step-rule-list">
    <div v-if="ruleRows.length" class="rule-item" v-for="(hit, idx) in ruleRows" :key="idx">
      <div class="rule-head">
        <a-tag color="blue">{{ hit.rule_id }}</a-tag>
        <a-tag :color="actionColor(hit.action)">{{ hit.action || '-' }}</a-tag>
        <a-tag v-if="hit.risk_level || hit.severity" :color="riskLevelColor(hit.risk_level || hit.severity)">
          {{ hit.risk_level || hit.severity }}
        </a-tag>
        <a-space class="rule-actions">
          <a-button size="small" type="link" @click="viewRule(hit)">查看规则</a-button>
          <a-button size="small" type="link" @click="copyRuleVersion">复制规则版本</a-button>
        </a-space>
      </div>
      <div class="rule-detail">
        <div v-if="hit.raw !== undefined || hit.raw_text !== undefined" class="rule-line">
          <span class="muted">原始值：</span>{{ formatText(hit.raw ?? hit.raw_text) }}
        </div>
        <div v-if="hit.converted !== undefined || hit.replacement !== undefined" class="rule-line">
          <span class="muted">建议值：</span>{{ formatText(hit.converted ?? hit.replacement) }}
        </div>
        <div v-if="hit.message" class="rule-line"><span class="muted">提示：</span>{{ hit.message }}</div>
      </div>
    </div>
    <span v-else class="muted">本步骤无命中规则</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import type { PipelineStep } from '@/types/conversionPipeline'

const props = defineProps<{
  step: PipelineStep
  ruleVersionId?: number | null
  ruleVersionCode?: string
}>()

const router = useRouter()

const ruleRows = computed(() => props.step.rule_hits || [])

function viewRule(hit: Record<string, any>) {
  const ruleCode = String(hit.rule_id ?? hit.rule_code ?? '')
  if (!ruleCode) {
    message.warning('该命中记录没有规则编号')
    return
  }
  router.push({
    path: '/conversion-config',
    query: {
      version_id: String(props.ruleVersionId ?? ''),
      rule_code: ruleCode,
    },
  })
}

async function copyRuleVersion() {
  const code = props.ruleVersionCode
  if (!code) {
    message.warning('暂无规则版本编码')
    return
  }
  try {
    await navigator.clipboard.writeText(code)
    message.success(`已复制规则版本 ${code}`)
  } catch {
    message.error('复制失败，请手动复制')
  }
}

function actionColor(action: string) {
  return ({ AUTO: 'green', CANDIDATE: 'blue', REVIEW: 'orange', BLOCK: 'red' } as any)[action] || 'default'
}

function riskLevelColor(level: string) {
  return ({ low: 'default', medium: 'blue', high: 'orange', highest: 'red' } as any)[level] || 'default'
}

function formatText(value: any) {
  return value === null || value === undefined || value === '' ? '-' : String(value)
}
</script>

<style scoped>
.step-rule-list {
  display: grid;
  gap: 10px;
}
.rule-item {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 8px 10px;
}
.rule-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.rule-actions {
  margin-left: auto;
}
.rule-detail {
  display: grid;
  gap: 2px;
}
.rule-line {
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}
.muted { color: #888; font-size: 12px; }
</style>
