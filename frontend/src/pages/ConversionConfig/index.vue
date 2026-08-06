<template>
  <div class="conversion-config-page">
    <div class="toolbar">
      <div class="toolbar-title">
        <span class="label">配置版本</span>
        <span class="muted">点击版本行可切换当前操作版本</span>
      </div>
      <a-space>
        <a-button @click="refreshAll">刷新</a-button>
        <a-button @click="openVersionModal">新建草稿</a-button>
        <a-button :disabled="!currentVersion" @click="openCloneModal">克隆</a-button>
        <a-popconfirm title="发布后会替换当前发布版本，确认发布？" @confirm="publishCurrent">
          <a-button type="primary" :disabled="!currentVersion || currentVersion.status === 'published'">发布</a-button>
        </a-popconfirm>
      </a-space>
    </div>

    <div class="version-list">
      <a-table
        size="small"
        row-key="id"
        :columns="versionColumns"
        :data-source="versions"
        :pagination="false"
        :row-class-name="versionRowClass"
        :loading="loading"
        @row-click="selectVersionRow"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusText(record.status) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'operate'">
            <a-popconfirm
              v-if="['draft', 'testing'].includes(record.status)"
              title="确认删除该版本？删除后不可恢复"
              @confirm="removeVersion(record)"
            >
              <a-button size="small" danger @click.stop>删除</a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </div>

    <div v-if="currentVersion" class="version-summary">
      <div>
        <div class="version-name">{{ currentVersion.version_name }}</div>
        <div class="muted">{{ currentVersion.version_code }} · {{ currentVersion.description || '无说明' }}</div>
      </div>
      <a-alert
        v-if="isPublished"
        type="info"
        show-icon
        message="当前是已发布版本，只能查看和预览；修改请先克隆为草稿。"
      />
    </div>

    <a-tabs v-model:activeKey="activeTab" class="main-tabs">
      <a-tab-pane key="lexicon" tab="词库管理">
        <div class="tab-actions">
          <a-input-search v-model:value="lexiconKeyword" placeholder="搜索错误词/标准词/规则编码" allow-clear class="search" />
          <a-space>
            <a-button @click="exportLexicon">导出词库 CSV</a-button>
            <a-button type="primary" :disabled="isPublished || !currentVersion" @click="openLexiconModal()">新增词条</a-button>
          </a-space>
        </div>
        <a-empty v-if="!lexiconGroups.length" description="暂无词条" />
        <div v-for="group in lexiconGroups" :key="group.key" class="lexicon-group">
          <div class="group-header">
            <span class="group-standard">{{ group.standard_text }}</span>
            <span class="group-count">{{ group.entries.length }} 个近似词</span>
            <a-button size="small" type="link" :disabled="isPublished" @click="openLexiconModal(undefined, group.standard_text)">新增近似词</a-button>
          </div>
          <a-table
            size="small"
            row-key="id"
            :loading="loading"
            :columns="lexiconColumns"
            :data-source="group.entries"
            :pagination="false"
            :scroll="{ x: 1500 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'enabled'">
                <a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-tag :color="actionColor(record.action)">{{ record.action }}</a-tag>
              </template>
              <template v-else-if="column.key === 'operate'">
                <a-space>
                  <a-button size="small" :disabled="isPublished" @click="openLexiconModal(record)">编辑</a-button>
                  <a-popconfirm title="确认删除该词条？" @confirm="removeLexicon(record.id)">
                    <a-button size="small" danger :disabled="isPublished">删除</a-button>
                  </a-popconfirm>
                </a-space>
              </template>
            </template>
          </a-table>
        </div>
      </a-tab-pane>

      <a-tab-pane key="rules" tab="规则管理">
        <div class="tab-actions">
          <a-input-search v-model:value="ruleKeyword" placeholder="搜索规则编码/名称/说明" allow-clear class="search" />
          <a-button type="primary" :disabled="isPublished || !currentVersion" @click="openRuleModal()">新增参数规则</a-button>
        </div>
        <a-tabs v-model:activeKey="ruleGroupTab" class="inner-tabs" size="small">
          <a-tab-pane v-for="group in ruleGroupDefs" :key="group.key" :tab="group.title" force-render>
            <a-table
              size="small"
              row-key="rgk"
              :loading="loading"
              :columns="group.editable ? ruleColumns : builtinRuleColumns"
              :data-source="ruleGroupRows[group.key] || []"
              :pagination="false"
              :scroll="{ x: 1100 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'action'">
                  <a-tag v-if="record.action || record.severity" :color="actionColor(record.action)">{{ record.action || record.severity }}</a-tag>
                  <span v-else class="muted">-</span>
                </template>
                <template v-else-if="column.key === 'risk'">
                  <a-tag v-if="record.risk_level || record.severity" :color="riskLevelColor(record.risk_level || record.severity)">{{ record.risk_level || record.severity }}</a-tag>
                  <span v-else class="muted">-</span>
                </template>
                <template v-else-if="column.key === 'enabled'">
                  <a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag>
                </template>
                <template v-else-if="column.key === 'editable'">
                  <a-tag :color="record.editable ? 'blue' : 'default'">{{ record.editable ? '可编辑' : '系统规则' }}</a-tag>
                </template>
                <template v-else-if="column.key === 'operate'">
                  <a-space>
                    <a-button size="small" :disabled="isPublished || !record.editable" @click="openRuleModal(record)">编辑</a-button>
                    <a-popconfirm title="确认删除该规则？" @confirm="removeRule(record.id)">
                      <a-button size="small" danger :disabled="isPublished || !record.editable">删除</a-button>
                    </a-popconfirm>
                  </a-space>
                </template>
              </template>
            </a-table>
          </a-tab-pane>
        </a-tabs>
      </a-tab-pane>

      <a-tab-pane key="preview" tab="版本测试">
        <div class="preview-grid">
          <div class="preview-panel">
            <div class="panel-title">输入 ASR 文本</div>
            <a-textarea v-model:value="previewText" :rows="10" placeholder="粘贴一段 ASR 原文，测试当前版本的词库和规则" />
            <div class="preview-actions">
              <a-input v-model:value="previewScene" placeholder="业务场景，可为空自动推断" />
              <a-button type="primary" :loading="previewing" :disabled="!previewText || !currentVersion" @click="runPreview">
                预览转化
              </a-button>
            </div>
          </div>
          <div class="preview-panel">
            <div class="panel-title">转化结果</div>
            <a-textarea :value="previewResult?.converted_text || ''" :rows="10" readonly placeholder="预览后显示转化结果" />
            <a-space wrap class="preview-tags">
              <a-tag v-if="previewResult" :color="previewResult.risk_blocked ? 'red' : previewResult.risk_passed ? 'green' : 'orange'">
                {{ previewResult.risk_blocked ? '风险阻断' : previewResult.risk_passed ? '风险通过' : '有警示待复核' }}
              </a-tag>
              <a-tag v-if="previewResult">{{ previewResult.conversions.length }} 次命中</a-tag>
              <a-tag v-if="previewResult">{{ Object.keys(previewResult.fields || {}).length }} 个字段</a-tag>
              <a-tag v-if="previewResult">{{ (previewResult.segments || []).length }} 个业务片段</a-tag>
              <a-tag v-if="previewResult" :color="previewResult.risk_items?.length ? 'orange' : 'default'">{{ previewResult.risk_items?.length || 0 }} 条警示</a-tag>
            </a-space>
          </div>
        </div>
        <a-table
          v-if="previewResult"
          class="preview-table"
          size="small"
          row-key="idx"
          :columns="previewColumns"
          :data-source="previewRows"
          :pagination="false"
        />
        <template v-if="previewResult">
          <a-divider orientation="left">警示项（人工复核建议）</a-divider>
          <a-alert
            v-if="!previewResult.risk_items?.length && !previewResult.warnings?.length"
            type="success"
            show-icon
            message="未命中警示规则"
          />
          <template v-else>
            <a-table
              class="preview-table"
              size="small"
              row-key="risk_key"
              :columns="riskColumns"
              :data-source="previewRiskRows"
              :pagination="false"
            />
            <a-alert
              v-if="previewResult.warnings?.length"
              class="warnings-alert"
              type="warning"
              show-icon
              :message="`规则警示文本 ${previewResult.warnings.length} 条`"
              :description="previewResult.warnings.join('；')"
            />
          </template>

          <a-divider orientation="left">字段解析结果</a-divider>
          <a-table
            v-if="previewFieldRows.length"
            class="preview-table"
            size="small"
            row-key="key"
            :columns="fieldColumns"
            :data-source="previewFieldRows"
            :pagination="false"
          />
          <a-empty v-else description="未解析出字段" :image-style="{ height: '48px' }" />

          <a-divider orientation="left">业务片段</a-divider>
          <a-table
            v-if="previewSegmentRows.length"
            class="preview-table"
            size="small"
            row-key="seg_key"
            :columns="segmentColumns"
            :data-source="previewSegmentRows"
            :pagination="false"
          />
          <a-empty v-else description="未定位到业务片段" :image-style="{ height: '48px' }" />

          <template v-if="previewResult.steps?.length">
            <a-divider orientation="left">处理步骤（{{ previewResult.steps.length }}）</a-divider>
            <a-collapse class="preview-steps" :bordered="false">
              <a-collapse-panel v-for="(step, idx) in previewResult.steps" :key="`pstep-${idx}`">
                <template #header>
                  <span>{{ step.step_order }}. {{ step.step_name }}</span>
                  <a-tag :color="stepStatusColor(step.status)" class="step-status-tag">{{ step.status }}</a-tag>
                  <span v-if="step.duration_ms != null" class="muted">{{ step.duration_ms }}ms</span>
                  <span v-if="step.conversions?.length" class="muted">{{ step.conversions.length }} 次命中</span>
                </template>
                <div class="step-box">
                  <div class="step-box-title">输入</div>
                  <pre>{{ step.input_text || '-' }}</pre>
                  <div class="step-box-title">输出</div>
                  <pre>{{ step.output_text || '-' }}</pre>
                </div>
              </a-collapse-panel>
            </a-collapse>
          </template>
        </template>
      </a-tab-pane>
    </a-tabs>

    <a-modal v-model:open="versionModalOpen" :title="versionMode === 'clone' ? '克隆为草稿' : '新建草稿版本'" @ok="saveVersion">
      <a-form layout="vertical">
        <a-form-item label="版本名称"><a-input v-model:value="versionForm.version_name" /></a-form-item>
        <a-form-item label="版本编码"><a-input v-model:value="versionForm.version_code" /></a-form-item>
        <a-form-item label="说明"><a-textarea v-model:value="versionForm.description" :rows="3" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="lexiconModalOpen"
      :title="editingLexiconId ? '编辑词库（标准词 + 近似词）' : '新增词库（标准词 + 近似词）'"
      width="720px"
      @ok="saveLexicon"
    >
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="14">
            <a-form-item label="标准词（医学名词 / 定位词）" required>
              <a-input v-model:value="lexiconForm.standard_text" placeholder="如：右卵巢、内膜" :disabled="!!editingLexiconId" />
            </a-form-item>
          </a-col>
          <a-col :span="10">
            <a-form-item label="业务场景">
              <a-input v-model:value="lexiconForm.business_scene" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-divider orientation="left">近似词（ASR 识别出的错词 / 同义词，可添加多个）</a-divider>
        <div v-for="(row, idx) in lexiconRows" :key="row.rowKey" class="lexicon-row">
          <a-input v-model:value="row.error_text" placeholder="ASR 近似词 / 错词" class="lexicon-row-error" />
          <a-select v-model:value="row.action" :options="actionOptions" class="lexicon-row-action" />
          <a-select v-model:value="row.risk_level" :options="riskOptions" class="lexicon-row-risk" />
          <a-switch v-model:checked="row.enabled" checked-children="启用" un-checked-children="停用" />
          <a-button type="text" danger @click="removeLexiconRow(idx)">删除</a-button>
        </div>
        <a-button type="dashed" block @click="addLexiconRow">+ 添加近似词</a-button>
      </a-form>
    </a-modal>

    <a-modal v-model:open="ruleModalOpen" title="参数规则" width="760px" @ok="saveRule">
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="8"><a-form-item label="规则编码" required><a-input v-model:value="ruleForm.rule_code" placeholder="如 P001" /></a-form-item></a-col>
          <a-col :span="8">
            <a-form-item label="处理器类型" required>
              <a-select
                v-model:value="ruleForm.system_handler"
                placeholder="选择处理器类型"
                :options="handlerOptions"
                @change="onHandlerChange"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8"><a-form-item label="风险"><a-select v-model:value="ruleForm.risk_level" :options="riskOptions" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="名称"><a-input v-model:value="ruleForm.name" /></a-form-item>
        <a-form-item label="说明"><a-textarea v-model:value="ruleForm.description" :rows="2" /></a-form-item>

        <!-- 文本正则替换 regex_replace -->
        <template v-if="ruleForm.system_handler === 'regex_replace'">
          <a-row :gutter="12">
            <a-col :span="12"><a-form-item label="正则表达式" required><a-input v-model:value="handlerFields.pattern" placeholder="如：放边" /></a-form-item></a-col>
            <a-col :span="12"><a-form-item label="替换值" required><a-input v-model:value="handlerFields.replacement" placeholder="如：换边" /></a-form-item></a-col>
          </a-row>
          <a-row :gutter="12">
            <a-col :span="12"><a-form-item label="必要上下文"><a-select v-model:value="handlerFields.required_terms" mode="tags" :options="[]" placeholder="命中任一即执行，回车添加" /></a-form-item></a-col>
            <a-col :span="12"><a-form-item label="排除上下文"><a-select v-model:value="handlerFields.excluded_terms" mode="tags" :options="[]" placeholder="命中任一即跳过，回车添加" /></a-form-item></a-col>
          </a-row>
        </template>

        <!-- 字段阈值校验 field_threshold -->
        <template v-else-if="ruleForm.system_handler === 'field_threshold'">
          <a-row :gutter="12">
            <a-col :span="12"><a-form-item label="目标字段" required><a-select v-model:value="handlerFields.field_codes" mode="multiple" :options="fieldCodeOptions" placeholder="选择或输入字段编码" /></a-form-item></a-col>
            <a-col :span="12"><a-form-item label="比较方式"><a-select v-model:value="handlerFields.operator" :options="operatorOptions" /></a-form-item></a-col>
          </a-row>
          <a-row :gutter="12">
            <a-col :span="12"><a-form-item label="阈值"><a-input-number v-model:value="handlerFields.threshold" class="full" /></a-form-item></a-col>
            <a-col :span="12"><a-form-item label="警示编码"><a-input v-model:value="handlerFields.warning_code" placeholder="如 OVARY_SIZE_BELOW_10" /></a-form-item></a-col>
          </a-row>
        </template>

        <!-- 字段格式校验 field_format -->
        <template v-else-if="ruleForm.system_handler === 'field_format'">
          <a-row :gutter="12">
            <a-col :span="12"><a-form-item label="目标字段" required><a-select v-model:value="handlerFields.field_codes" mode="multiple" :options="fieldCodeOptions" placeholder="选择或输入字段编码" /></a-form-item></a-col>
            <a-col :span="12"><a-form-item label="格式正则" required><a-input v-model:value="handlerFields.pattern" placeholder="如 ^\d{1,2}\.\d$" /></a-form-item></a-col>
          </a-row>
          <a-form-item label="警示编码"><a-input v-model:value="handlerFields.warning_code" placeholder="如 FOLLICLE_FORMAT_INVALID" /></a-form-item>
        </template>

        <!-- 字段重新归类 field_reclassify -->
        <template v-else-if="ruleForm.system_handler === 'field_reclassify'">
          <a-row :gutter="12">
            <a-col :span="12"><a-form-item label="来源字段" required><a-input v-model:value="handlerFields.source_field" placeholder="如 unassigned_ovary_sizes" /></a-form-item></a-col>
            <a-col :span="12"><a-form-item label="目标字段" required><a-input v-model:value="handlerFields.target_field" placeholder="如 ultrasound_findings" /></a-form-item></a-col>
          </a-row>
          <a-form-item label="必要后缀"><a-select v-model:value="handlerFields.required_suffixes" mode="tags" :options="[]" placeholder="如：无回声，回车添加" /></a-form-item>
        </template>

        <a-alert
          v-if="!ruleForm.system_handler"
          type="info"
          show-icon
          message="请先选择处理器类型，系统将按类型展示对应配置字段"
          class="handler-hint"
        />

        <a-row :gutter="12">
          <a-col :span="6"><a-form-item label="动作"><a-select v-model:value="ruleForm.action" :options="actionOptions" /></a-form-item></a-col>
          <a-col :span="6"><a-form-item label="优先级"><a-input-number v-model:value="ruleForm.priority" class="full" /></a-form-item></a-col>
          <a-col :span="6"><a-form-item label="启用"><a-switch v-model:checked="ruleEnabled" /></a-form-item></a-col>
          <a-col :span="6"><a-form-item label="可编辑"><a-switch v-model:checked="ruleEditable" /></a-form-item></a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="示例输入"><a-textarea v-model:value="ruleForm.example_input" :rows="2" /></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="示例输出"><a-textarea v-model:value="ruleForm.example_output" :rows="2" /></a-form-item></a-col>
        </a-row>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import { conversionConfigApi } from '@/api/client'

const route = useRoute()

const loading = ref(false)
const previewing = ref(false)
const activeTab = ref('lexicon')
const versions = ref<any[]>([])
const selectedVersionId = ref<number>()
const lexicon = ref<any[]>([])
const rules = ref<any[]>([])
const builtinRules = ref<any>({ text_switch: [], field_extract: [], risk: [] })
const lexiconKeyword = ref('')
const ruleKeyword = ref('')
const previewText = ref('')
const previewScene = ref('卵泡监测B超')
const previewResult = ref<any>()

const versionModalOpen = ref(false)
const versionMode = ref<'create' | 'clone'>('create')
const versionForm = reactive({ version_name: '', version_code: '', description: '' })

const lexiconModalOpen = ref(false)
const editingLexiconId = ref<number>()
const lexiconForm = reactive<any>({ standard_text: '', business_scene: '卵泡监测B超' })
const lexiconRows = ref<any[]>([])
let lexiconRowSeq = 0

const ruleModalOpen = ref(false)
const editingRuleId = ref<number>()
const ruleEnabled = ref(true)
const ruleEditable = ref(true)
const ruleForm = reactive<any>(defaultRule())

/** 受控处理器类型 → 规则类型映射（与后端 ALLOWED_HANDLERS 白名单一致） */
const ruleHandlerDefs: Record<string, { label: string; rule_type: string }> = {
  regex_replace: { label: '文本正则替换', rule_type: 'text_replace' },
  field_threshold: { label: '字段阈值校验', rule_type: 'field_validation' },
  field_format: { label: '字段格式校验', rule_type: 'field_validation' },
  field_reclassify: { label: '字段重新归类', rule_type: 'field_reclassify' },
}

const handlerOptions = Object.entries(ruleHandlerDefs).map(([value, def]) => ({ value, label: def.label }))

const operatorOptions = [
  { value: 'lt', label: '小于 <' },
  { value: 'lte', label: '小于等于 ≤' },
  { value: 'gt', label: '大于 >' },
  { value: 'gte', label: '大于等于 ≥' },
  { value: 'eq', label: '等于 =' },
]

const fieldCodeOptions = computed(() => Array.from(new Set([
  ...Object.keys(fieldLabels),
  'right_ovary_length', 'right_ovary_width', 'left_ovary_length', 'left_ovary_width',
  'right_follicle_total', 'left_follicle_total',
])).map(value => ({ value, label: `${fieldLabels[value] || value} (${value})` })))

/** handler 专属字段（保存时由 saveRule 组装成 condition_config，不要求用户手写 JSON） */
const handlerFields = reactive({
  pattern: '',
  replacement: '',
  required_terms: [] as string[],
  excluded_terms: [] as string[],
  field_codes: [] as string[],
  operator: 'lt',
  threshold: undefined as number | undefined,
  warning_code: '',
  source_field: '',
  target_field: '',
  required_suffixes: [] as string[],
})

function resetHandlerFields() {
  handlerFields.pattern = ''
  handlerFields.replacement = ''
  handlerFields.required_terms = []
  handlerFields.excluded_terms = []
  handlerFields.field_codes = []
  handlerFields.operator = 'lt'
  handlerFields.threshold = undefined
  handlerFields.warning_code = ''
  handlerFields.source_field = ''
  handlerFields.target_field = ''
  handlerFields.required_suffixes = []
}

function onHandlerChange() {
  // 切换处理器时保留已填内容，避免误删；仅控制字段显隐
}

const currentVersion = computed(() => versions.value.find(item => item.id === selectedVersionId.value))
const isPublished = computed(() => currentVersion.value?.status === 'published')

const versionColumns = [
  { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
  { title: '版本名称', dataIndex: 'version_name', key: 'version_name' },
  { title: '版本编码', dataIndex: 'version_code', key: 'version_code', width: 160 },
  { title: '词库', dataIndex: 'lexicon_count', key: 'lexicon_count', width: 70 },
  { title: '规则', dataIndex: 'rule_count', key: 'rule_count', width: 70 },
  { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 180 },
  { title: '操作', key: 'operate', width: 90 },
]

function versionRowClass(record: any) {
  return record.id === selectedVersionId.value ? 'version-row-active' : ''
}

function selectVersionRow(record: any) {
  if (record.id === selectedVersionId.value) return
  selectedVersionId.value = record.id
  loadVersionData()
}

async function removeVersion(record: any) {
  await conversionConfigApi.deleteVersion(record.id)
  message.success('版本删除成功')
  await refreshAll()
}

const filteredLexicon = computed(() => {
  const kw = lexiconKeyword.value.trim()
  if (!kw) return lexicon.value
  return lexicon.value.filter(item => [item.rule_code, item.error_text, item.standard_text, item.business_scene, item.notes].some(v => String(v || '').includes(kw)))
})

// 按标准词分组展示“标准词 + 多近似词”
const lexiconGroups = computed(() => {
  const groups = new Map<string, any[]>()
  for (const item of filteredLexicon.value) {
    const key = String(item.standard_text || '').trim() || '（未设置标准词）'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(item)
  }
  return Array.from(groups.entries()).map(([standard_text, entries]) => ({
    key: `group-${standard_text}`,
    standard_text,
    entries,
  }))
})

// 规则管理二级 tab：文本切换 / 数据提取 / 警示规则 / 引擎基础步骤 / 参数化规则
const ruleGroupTab = ref('text_switch')

const ruleGroupDefs = [
  { key: 'text_switch', title: '文本切换规则', editable: false },
  { key: 'field_extract', title: '数据提取规则', editable: false },
  { key: 'risk', title: '警示规则', editable: false },
  { key: 'engine_base', title: '引擎基础步骤', editable: false },
  { key: 'custom', title: '参数化规则', editable: true },
]

const ruleGroupRows = computed<Record<string, any[]>>(() => {
  const kw = ruleKeyword.value.trim()
  const match = (item: any) =>
    !kw || [item.rule_code, item.name, item.description, item.rule_type].some(v => String(v || '').includes(kw))
  const sysByCode = new Map<string, any>()
  const custom: any[] = []
  for (const item of rules.value) {
    if (item.editable) custom.push(item)
    else sysByCode.set(item.rule_code, item)
  }
  // 已归类的系统规则编码（分别展示于数据提取/警示/引擎基础步骤组）
  const classifiedCodes = new Set(['B001', 'N001', 'M001', 'F001', 'R001'])
  const ungroupedSystem = rules.value.filter(item => !item.editable && !classifiedCodes.has(item.rule_code))
  const withKey = (rows: any[], prefix: string) => rows.filter(match).map((item: any, idx: number) => ({ ...item, rgk: `${prefix}-${idx}` }))
  return {
    text_switch: withKey(builtinRules.value.text_switch || [], 'sw'),
    field_extract: withKey(
      [...(builtinRules.value.field_extract || []), ...(sysByCode.get('F001') ? [sysByCode.get('F001')] : [])],
      'fe',
    ),
    risk: withKey(
      [...(builtinRules.value.risk || []), ...(sysByCode.get('R001') ? [sysByCode.get('R001')] : [])],
      'rk',
    ),
    engine_base: withKey(
      [...['B001', 'N001', 'M001'].map(code => sysByCode.get(code)).filter(Boolean), ...ungroupedSystem],
      'eb',
    ),
    custom: withKey(custom, 'cu'),
  }
})

const previewRows = computed(() => (previewResult.value?.conversions || []).map((item: any, idx: number) => ({ ...item, idx: idx + 1 })))
const previewRiskRows = computed(() => (previewResult.value?.risk_items || []).map((item: any, idx: number) => ({ ...item, risk_key: `risk-${idx}` })))
const previewSegmentRows = computed(() => (previewResult.value?.segments || []).map((item: any, idx: number) => ({ ...item, seg_key: `seg-${idx}` })))
const previewFieldRows = computed(() =>
  Object.entries(previewResult.value?.fields || {}).map(([key, value]: [string, any]) => ({
    key,
    label: fieldLabels[key] || key,
    value: formatFieldValue(value),
  })),
)

const fieldLabels: Record<string, string> = {
  endometrium_thickness: '内膜厚度',
  endometrium_type: '内膜类型',
  right_ovary_size: '右卵巢大小',
  left_ovary_size: '左卵巢大小',
  right_follicles: '右卵泡明细',
  left_follicles: '左卵泡明细',
  current_side: '当前侧别',
  ultrasound_findings: '超声发现',
  procedure_info: '操作信息',
  followup_orders: '随访医嘱',
  mentioned_count: '提及数量',
  noise_segment: '噪声片段',
  remark: '备注',
}

function formatFieldValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.map((item: any) => (typeof item === 'object' ? JSON.stringify(item) : item)).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const actionOptions = ['AUTO', 'CANDIDATE', 'REVIEW', 'BLOCK'].map(value => ({ label: value, value }))
const riskOptions = ['low', 'medium', 'high', 'highest'].map(value => ({ label: value, value }))
const matchOptions = ['exact', 'phonetic', 'phrase'].map(value => ({ label: value, value }))

const lexiconColumns = [
  { title: '错误词', dataIndex: 'error_text', key: 'error_text', width: 160 },
  { title: '标准词', dataIndex: 'standard_text', key: 'standard_text', width: 160 },
  { title: '场景', dataIndex: 'business_scene', key: 'business_scene', width: 130 },
  { title: '动作', dataIndex: 'action', key: 'action', width: 100 },
  { title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 90 },
  { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80 },
  { title: '操作', key: 'operate', fixed: 'right', width: 150 },
]

const ruleColumns = [
  { title: '编码', dataIndex: 'rule_code', key: 'rule_code', width: 90 },
  { title: '类型', dataIndex: 'rule_type', key: 'rule_type', width: 130 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 180 },
  { title: '说明', dataIndex: 'description', key: 'description', width: 260 },
  { title: '处理器', dataIndex: 'system_handler', key: 'system_handler', width: 160 },
  { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80 },
  { title: '属性', dataIndex: 'editable', key: 'editable', width: 90 },
  { title: '操作', key: 'operate', fixed: 'right', width: 150 },
]

// 内置规则组（文本切换/数据提取/警示规则）只读列：兼容内置元数据与 DB 系统规则条目
const builtinRuleColumns = [
  { title: '编码', dataIndex: 'rule_code', key: 'rule_code', width: 90 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 160 },
  { title: '说明', dataIndex: 'description', key: 'description' },
  { title: '动作', key: 'action', width: 100 },
  { title: '风险', key: 'risk', width: 90 },
]

const previewColumns = [
  { title: '#', dataIndex: 'idx', key: 'idx', width: 60 },
  { title: '规则', dataIndex: 'rule_id', key: 'rule_id', width: 110 },
  { title: '原文', dataIndex: 'raw', key: 'raw' },
  { title: '转化', dataIndex: 'converted', key: 'converted' },
  { title: '动作', dataIndex: 'action', key: 'action', width: 110 },
  { title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 100 },
]

const riskColumns = [
  { title: '规则', dataIndex: 'rule_id', key: 'rule_id', width: 90 },
  { title: '动作', dataIndex: 'action', key: 'action', width: 100 },
  { title: '严重度', dataIndex: 'severity', key: 'severity', width: 100 },
  { title: '提示', dataIndex: 'message', key: 'message' },
]

const fieldColumns = [
  { title: '字段', dataIndex: 'label', key: 'label', width: 200 },
  { title: '值', dataIndex: 'value', key: 'value' },
]

const segmentColumns = [
  { title: '类型', dataIndex: 'segment_type', key: 'segment_type', width: 110 },
  { title: '字段', dataIndex: 'field_code', key: 'field_code', width: 170 },
  { title: '侧别', dataIndex: 'side', key: 'side', width: 80 },
  { title: '原文', dataIndex: 'text', key: 'text', width: 150 },
  { title: '归一', dataIndex: 'normalized', key: 'normalized', width: 130 },
  { title: '说明', dataIndex: 'note', key: 'note' },
]

onMounted(async () => {
  await refreshAll()
  await applyRuleQuery()
})

async function refreshAll() {
  loading.value = true
  try {
    const [builtin] = await Promise.all([conversionConfigApi.listBuiltinRules()])
    builtinRules.value = builtin || { text_switch: [], field_extract: [], risk: [] }
    let list: any[] = await conversionConfigApi.listVersions()
    if (!list.length) {
      await conversionConfigApi.initDefaults()
      list = await conversionConfigApi.listVersions()
    }
    versions.value = list
    if (!selectedVersionId.value || !list.some(item => item.id === selectedVersionId.value)) {
      selectedVersionId.value = list.find(item => item.status === 'published')?.id || list[0]?.id
    }
    await loadVersionData()
  } finally {
    loading.value = false
  }
}

async function loadVersionData() {
  if (!selectedVersionId.value) return
  loading.value = true
  try {
    const [lexiconRows, ruleRows] = await Promise.all([
      conversionConfigApi.listLexicon(selectedVersionId.value),
      conversionConfigApi.listRules(selectedVersionId.value),
    ])
    lexicon.value = lexiconRows as any[]
    rules.value = ruleRows as any[]
    previewResult.value = undefined
  } finally {
    loading.value = false
  }
}

function openVersionModal() {
  versionMode.value = 'create'
  Object.assign(versionForm, {
    version_name: `转化规则草稿 ${new Date().toISOString().slice(0, 10)}`,
    version_code: `draft-${Date.now()}`,
    description: '',
  })
  versionModalOpen.value = true
}

function openCloneModal() {
  if (!currentVersion.value) return
  versionMode.value = 'clone'
  Object.assign(versionForm, {
    version_name: `${currentVersion.value.version_name} 副本`,
    version_code: `${currentVersion.value.version_code}-draft-${Date.now().toString().slice(-5)}`,
    description: `从 ${currentVersion.value.version_code} 克隆`,
  })
  versionModalOpen.value = true
}

async function saveVersion() {
  if (versionMode.value === 'clone' && currentVersion.value) {
    const created: any = await conversionConfigApi.cloneVersion(currentVersion.value.id, versionForm)
    selectedVersionId.value = created.id
  } else {
    const created: any = await conversionConfigApi.createVersion({ ...versionForm, status: 'draft' })
    selectedVersionId.value = created.id
  }
  versionModalOpen.value = false
  await refreshAll()
}

async function publishCurrent() {
  if (!currentVersion.value) return
  const published: any = await conversionConfigApi.publishVersion(currentVersion.value.id)
  message.success('发布成功')
  selectedVersionId.value = published.id
  await refreshAll()
}

function newLexiconRow() {
  lexiconRowSeq += 1
  return {
    rowKey: `lr-${lexiconRowSeq}-${Date.now()}`,
    id: undefined,
    error_text: '',
    action: 'AUTO',
    risk_level: 'medium',
    enabled: true,
  }
}

function openLexiconModal(row?: any, standardText?: string) {
  editingLexiconId.value = row?.id || undefined
  if (row) {
    // 编辑模式：加载该标准词下的全部近似词，支持整组批量编辑
    const std = row.standard_text || ''
    Object.assign(lexiconForm, { standard_text: std, business_scene: row.business_scene || '卵泡监测B超' })
    lexiconRows.value = lexicon.value
      .filter(item => (item.standard_text || '') === std)
      .map(item => ({
        rowKey: `lr-edit-${item.id}`,
        id: item.id,
        error_text: item.error_text,
        action: item.action || 'AUTO',
        risk_level: item.risk_level || 'medium',
        enabled: Boolean(item.enabled),
      }))
  } else {
    Object.assign(lexiconForm, { standard_text: standardText || '', business_scene: '卵泡监测B超' })
    lexiconRows.value = [newLexiconRow()]
  }
  lexiconModalOpen.value = true
}

function addLexiconRow() {
  lexiconRows.value.push(newLexiconRow())
}

function removeLexiconRow(idx: number) {
  lexiconRows.value.splice(idx, 1)
}

async function saveLexicon() {
  if (!selectedVersionId.value) return
  const std = (lexiconForm.standard_text || '').trim()
  if (!std) {
    message.warning('请填写标准词')
    return
  }
  const rows = lexiconRows.value.filter(r => (r.error_text || '').trim())
  if (!rows.length) {
    message.warning('请至少填写一个近似词')
    return
  }
  const scene = lexiconForm.business_scene || '卵泡监测B超'
  if (!editingLexiconId.value) {
    // 新增模式：批量创建
    for (let i = 0; i < rows.length; i++) {
      await conversionConfigApi.createLexicon(selectedVersionId.value, {
        rule_code: `L${Date.now()}${i}`,
        error_text: rows[i].error_text.trim(),
        standard_text: std,
        business_scene: scene,
        action: rows[i].action || 'AUTO',
        risk_level: rows[i].risk_level || 'medium',
        enabled: rows[i].enabled ? 1 : 0,
      })
    }
  } else {
    // 编辑模式：更新保留条目、创建新增行、删除被移除的原组条目
    const keepIds = new Set(rows.filter(r => r.id).map(r => r.id))
    const original = lexicon.value.filter(item => (item.standard_text || '') === std)
    for (const item of original) {
      if (!keepIds.has(item.id)) {
        await conversionConfigApi.deleteLexicon(item.id)
      }
    }
    let seq = 0
    for (const row of rows) {
      const payload = {
        error_text: row.error_text.trim(),
        standard_text: std,
        business_scene: scene,
        action: row.action || 'AUTO',
        risk_level: row.risk_level || 'medium',
        enabled: row.enabled ? 1 : 0,
      }
      if (row.id) {
        await conversionConfigApi.updateLexicon(row.id, payload)
      } else {
        await conversionConfigApi.createLexicon(selectedVersionId.value, {
          rule_code: `L${Date.now()}${seq}`,
          ...payload,
        })
        seq += 1
      }
    }
  }
  lexiconModalOpen.value = false
  await refreshAll()
}

async function removeLexicon(id: number) {
  await conversionConfigApi.deleteLexicon(id)
  await refreshAll()
}

function openRuleModal(row?: any) {
  editingRuleId.value = row?.id
  Object.assign(ruleForm, row ? { ...row } : defaultRule())
  ruleEnabled.value = row ? Boolean(row.enabled) : true
  ruleEditable.value = row ? Boolean(row.editable) : true
  resetHandlerFields()
  if (row) {
    const condition = row.condition_config || {}
    let handler = row.system_handler || ''
    // 兼容历史规则：无 system_handler 但配置了 pattern/replacement 的旧文本规则按 regex_replace 处理
    if (!handler && (row.pattern || row.replacement) && !String(row.rule_type || '').startsWith('field_')) {
      handler = 'regex_replace'
    }
    ruleForm.system_handler = handler
    handlerFields.pattern = String(condition.pattern ?? row.pattern ?? '')
    handlerFields.replacement = String(condition.replacement ?? row.replacement ?? '')
    handlerFields.required_terms = Array.isArray(condition.required_terms) ? [...condition.required_terms] : []
    handlerFields.excluded_terms = Array.isArray(condition.excluded_terms) ? [...condition.excluded_terms] : []
    handlerFields.field_codes = Array.isArray(condition.field_codes) ? [...condition.field_codes] : []
    handlerFields.operator = condition.operator || 'lt'
    handlerFields.threshold = condition.threshold
    handlerFields.warning_code = condition.warning_code || ''
    handlerFields.source_field = condition.source_field || ''
    handlerFields.target_field = condition.target_field || ''
    handlerFields.required_suffixes = Array.isArray(condition.required_suffixes) ? [...condition.required_suffixes] : []
  } else {
    ruleForm.system_handler = ''
  }
  ruleModalOpen.value = true
}

async function saveRule() {
  if (!selectedVersionId.value) return
  const handler = ruleForm.system_handler || ''
  if (!handler || !ruleHandlerDefs[handler]) {
    message.warning('请选择处理器类型')
    return
  }
  const payload: any = {
    ...ruleForm,
    rule_type: ruleHandlerDefs[handler].rule_type,
    system_handler: handler,
    pattern: '',
    replacement: '',
    condition_config: {},
    enabled: ruleEnabled.value ? 1 : 0,
    editable: ruleEditable.value ? 1 : 0,
  }
  // 按 handler 组装 condition_config，用户无需手写 JSON
  if (handler === 'regex_replace') {
    if (!handlerFields.pattern || !handlerFields.replacement) {
      message.warning('请填写正则表达式和替换值')
      return
    }
    payload.pattern = handlerFields.pattern
    payload.replacement = handlerFields.replacement
    payload.condition_config = {
      required_terms: handlerFields.required_terms,
      excluded_terms: handlerFields.excluded_terms,
    }
  } else if (handler === 'field_threshold') {
    if (!handlerFields.field_codes.length || handlerFields.threshold === undefined || handlerFields.threshold === null) {
      message.warning('请填写目标字段和阈值')
      return
    }
    payload.condition_config = {
      field_codes: handlerFields.field_codes,
      operator: handlerFields.operator,
      threshold: handlerFields.threshold,
      warning_code: handlerFields.warning_code,
    }
  } else if (handler === 'field_format') {
    if (!handlerFields.field_codes.length || !handlerFields.pattern) {
      message.warning('请填写目标字段和格式正则')
      return
    }
    payload.condition_config = {
      field_codes: handlerFields.field_codes,
      pattern: handlerFields.pattern,
      warning_code: handlerFields.warning_code,
    }
  } else if (handler === 'field_reclassify') {
    if (!handlerFields.source_field || !handlerFields.target_field) {
      message.warning('请填写来源字段和目标字段')
      return
    }
    payload.condition_config = {
      source_field: handlerFields.source_field,
      target_field: handlerFields.target_field,
      required_suffixes: handlerFields.required_suffixes,
    }
  }
  if (editingRuleId.value) {
    await conversionConfigApi.updateRule(editingRuleId.value, payload)
  } else {
    await conversionConfigApi.createRule(selectedVersionId.value, payload)
  }
  ruleModalOpen.value = false
  await refreshAll()
}

async function removeRule(id: number) {
  await conversionConfigApi.deleteRule(id)
  await refreshAll()
}

async function runPreview() {
  if (!currentVersion.value) return
  previewing.value = true
  try {
    previewResult.value = await conversionConfigApi.preview({
      version_id: currentVersion.value.id,
      text: previewText.value,
      scene: previewScene.value,
    })
  } finally {
    previewing.value = false
  }
}

function exportLexicon() {
  const headers = ['rule_code', 'error_text', 'standard_text', 'business_scene', 'required_context', 'excluded_context', 'action', 'risk_level', 'confidence', 'enabled', 'notes']
  const rows = [headers.join(',')].concat(filteredLexicon.value.map(row => headers.map(key => csvCell(row[key])).join(',')))
  const blob = new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${currentVersion.value?.version_code || 'conversion'}-lexicon.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function csvCell(value: any) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`
}

function defaultRule() {
  return {
    rule_code: '',
    rule_type: 'custom',
    name: '',
    description: '',
    pattern: '',
    replacement: '',
    condition_config: {},
    example_input: '',
    example_output: '',
    action: 'AUTO',
    risk_level: 'medium',
    priority: 100,
    enabled: 1,
    editable: 1,
    system_handler: '',
    notes: '',
  }
}

function statusText(status: string) {
  return ({ draft: '草稿', testing: '测试中', published: '已发布', rolled_back: '已回滚' } as any)[status] || status
}

function statusColor(status: string) {
  return ({ draft: 'blue', testing: 'orange', published: 'green', rolled_back: 'default' } as any)[status] || 'default'
}

function actionColor(action: string) {
  return ({ AUTO: 'green', CANDIDATE: 'blue', REVIEW: 'orange', BLOCK: 'red' } as any)[action] || 'default'
}

function riskLevelColor(level: string) {
  return ({ low: 'default', medium: 'blue', high: 'orange', highest: 'red' } as any)[level] || 'default'
}

function stepStatusColor(status: string) {
  return ({ success: 'green', failed: 'red', running: 'processing', pending: 'default' } as any)[status] || 'default'
}

/**
 * 处理调试台“查看规则”跳转（/conversion-config?version_id=&rule_code=）：
 * 自动选择版本、切到规则管理，并用规则编码过滤定位对应规则。
 */
async function applyRuleQuery() {
  const versionId = route.query.version_id
  const ruleCode = route.query.rule_code
  if (versionId) {
    const id = Number(versionId)
    if (Number.isFinite(id) && versions.value.some(item => item.id === id)) {
      selectedVersionId.value = id
      await loadVersionData()
    }
  }
  if (ruleCode) {
    activeTab.value = 'rules'
    ruleKeyword.value = String(ruleCode)
  }
}
</script>

<style scoped>
.conversion-config-page {
  width: 100%;
  padding: 16px;
}

.toolbar,
.version-summary,
.tab-actions,
.preview-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.toolbar,
.version-summary,
.main-tabs {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}

.version-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.toolbar-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.version-list {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 12px;
}

.version-list :deep(.version-row-active) {
  background: #e6f4ff;
}

.version-list :deep(.version-row-active:hover > td) {
  background: #bae0ff !important;
}

.label {
  color: #666;
  white-space: nowrap;
}

.version-select {
  width: 320px;
}

.version-name {
  font-size: 16px;
  font-weight: 600;
}

.muted {
  color: #888;
  font-size: 12px;
  margin-top: 4px;
}

.search {
  width: 360px;
}

.preview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.preview-panel {
  min-width: 0;
}

.panel-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.preview-actions {
  margin-top: 8px;
}

.preview-tags {
  margin-top: 8px;
}

.preview-table {
  margin-top: 12px;
}

.warnings-alert {
  margin-top: 8px;
}

.handler-hint {
  margin-bottom: 12px;
}

.preview-steps {
  margin-top: 4px;
  background: #fff;
}

.preview-steps :deep(.ant-collapse-content-box) {
  display: grid;
  gap: 10px;
}

.step-status-tag {
  margin-left: 6px;
}

.step-box {
  display: grid;
  gap: 6px;
}

.step-box-title {
  color: #666;
  font-size: 12px;
  font-weight: 600;
}

.step-box pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 180px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
  background: #fafafa;
  border-radius: 4px;
  padding: 8px;
}

.lexicon-group {
  margin-bottom: 14px;
}

.lexicon-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.lexicon-row-error {
  flex: 1;
}

.lexicon-row-action {
  width: 110px;
}

.lexicon-row-risk {
  width: 110px;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-bottom: none;
  border-radius: 4px 4px 0 0;
}

.group-standard {
  font-weight: 600;
  color: #0958d9;
}

.group-count {
  color: #888;
  font-size: 12px;
}

.full {
  width: 100%;
}

@media (max-width: 1100px) {
  .toolbar,
  .version-summary,
  .tab-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .version-select,
  .search {
    width: 100%;
  }

  .preview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
