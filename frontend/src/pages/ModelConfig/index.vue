<template>
  <div class="page-container">
    <div class="page-header"><h2>模型配置</h2></div>

    <a-card title="已配置模型">
      <template #extra>
        <a-space>
          <a-button @click="fetchModels"><ReloadOutlined />刷新</a-button>
          <a-button type="primary" @click="openCreate"><PlusOutlined />新增模型</a-button>
        </a-space>
      </template>

      <a-table row-key="id" :loading="loading" :columns="columns" :data-source="models" :pagination="false" size="middle">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'model_type'">
            <a-tag :color="record.model_type === 'asr' ? 'blue' : 'purple'">
              {{ record.model_type.toUpperCase() }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'provider'">
            <a-tag>{{ record.provider }}</a-tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.status === 'active' ? 'green' : 'default'">
              {{ record.status === 'active' ? '启用' : '停用' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'is_default'">
            <a-tag v-if="record.is_default" color="gold">默认</a-tag>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button size="small" :loading="testing[record.id]" @click="handleTest(record.id)">
                <ApiOutlined />测试
              </a-button>
              <a-button size="small" @click="openEdit(record)">编辑</a-button>
              <a-popconfirm title="确认删除？" @confirm="handleDelete(record.id)">
                <a-button size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      :title="editing ? '编辑模型' : '新增模型'"
      :open="modalOpen"
      @cancel="handleCancel"
      :confirm-loading="saving"
      @ok="handleSubmit"
      :width="600"
    >
      <a-form ref="formRef" :model="form" layout="vertical" @finish="handleSave">
        <a-form-item name="name" label="名称" :rules="[{ required: true, message: '请输入名称' }]">
          <a-input v-model:value="form.name" placeholder="如：本地 FunASR" />
        </a-form-item>
        <a-form-item name="model_type" label="类型" :rules="[{ required: true, message: '请选择类型' }]">
          <a-select v-model:value="form.model_type" placeholder="请选择类型">
            <a-select-option value="asr">ASR（语音转文字）</a-select-option>
            <a-select-option value="llm">LLM（语义理解）</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item name="provider" label="Provider" :rules="[{ required: true, message: '请选择Provider' }]">
          <a-select v-model:value="form.provider" placeholder="请选择Provider">
            <a-select-option value="local">本地</a-select-option>
            <a-select-option value="volcengine">豆包 / 火山引擎</a-select-option>
            <a-select-option value="mimo">MiMo</a-select-option>
            <a-select-option value="iflytek_rtasr_llm">讯飞实时转写大模型</a-select-option>
            <a-select-option value="tencent_speaker_ws">腾讯实时说话人分离</a-select-option>
            <a-select-option value="iflytek">讯飞</a-select-option>
            <a-select-option value="tencent">腾讯</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item name="endpoint" label="Endpoint URL" :rules="[{ required: true, message: '请输入Endpoint' }]">
          <a-input v-model:value="form.endpoint" placeholder="http://172.16.10.142:50000/transcribe" />
        </a-form-item>
        <a-form-item name="model_name" label="模型名称（可选）">
          <a-input v-model:value="form.model_name" placeholder="如：spark-v3.5" />
        </a-form-item>
        <a-card v-if="isMimoAsr" size="small" title="MiMo ASR 专属配置" class="provider-card">
          <a-form-item label="音频读取方式">
            <a-radio-group v-model:value="form.params.audio_input_mode">
              <a-radio value="segments">原始分段</a-radio>
              <a-radio value="grouped">连续分组合并</a-radio>
              <a-radio value="merged">整段合并音频</a-radio>
            </a-radio-group>
            <div class="form-help">当前实测 MiMo 原始分段更稳定；连续分组用于 A/B 测试；整段可能出现截断。</div>
          </a-form-item>
          <a-form-item label="识别语言">
            <a-select v-model:value="form.params.language">
              <a-select-option value="auto">auto（自动识别）</a-select-option>
              <a-select-option value="zh">zh（中文）</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="启用 stream 返回">
            <a-switch v-model:checked="form.params.stream" />
            <div class="form-help">MiMo 的 stream 是“完整音频上传后的响应流式返回”，不是实时麦克风音频流。</div>
          </a-form-item>
          <a-form-item label="连续分组大小">
            <a-input-number v-model:value="form.params.merge_group_size" :min="1" :max="10" style="width: 180px" />
            <div class="form-help">仅在“连续分组合并”模式下使用，表示每几个原始分段合成一个 group 音频。</div>
          </a-form-item>
          <a-form-item label="Base64 上限（MB）">
            <a-input-number v-model:value="form.params.max_base64_mb" :min="1" :max="10" :step="0.1" style="width: 180px" />
          </a-form-item>
        </a-card>
        <a-card v-if="isVolcengineAsr" size="small" title="豆包 ASR 专属配置" class="provider-card">
          <a-form-item label="接口模式">
            <a-radio-group v-model:value="form.params.endpoint_mode">
              <a-radio value="bigmodel_nostream">流式输入 nostream（准确率优先，推荐）</a-radio>
              <a-radio value="bigmodel">双向流式（速度优先）</a-radio>
              <a-radio value="bigmodel_async">双向流式优化版</a-radio>
            </a-radio-group>
            <div class="form-help">
              已有录音转写建议使用 nostream；实时上屏可测试 bigmodel_async。
            </div>
          </a-form-item>
          <a-form-item label="音频读取方式">
            <a-radio-group v-model:value="form.params.audio_input_mode">
              <a-radio value="segments">原始分段</a-radio>
              <a-radio value="grouped">连续分组合并</a-radio>
              <a-radio value="merged">整段合并音频</a-radio>
            </a-radio-group>
          </a-form-item>
          <a-form-item label="结果返回类型">
            <a-select v-model:value="form.params.result_type">
              <a-select-option value="full">full（全量结果，推荐）</a-select-option>
              <a-select-option value="single">single（单次结果）</a-select-option>
            </a-select>
          </a-form-item>
          <a-space class="switch-row" wrap>
            <span>数字规整 enable_itn</span>
            <a-switch v-model:checked="form.params.enable_itn" />
            <span>标点 enable_punc</span>
            <a-switch v-model:checked="form.params.enable_punc" />
            <span>顺滑 enable_ddc</span>
            <a-switch v-model:checked="form.params.enable_ddc" />
            <span>分句 show_utterances</span>
            <a-switch v-model:checked="form.params.show_utterances" />
            <span>二遍识别 enable_nonstream</span>
            <a-switch v-model:checked="form.params.enable_nonstream" />
          </a-space>
          <div class="form-help">
            二遍识别仅 bigmodel_async 支持；顺滑可能提升可读性，但可能合并/删除重复数字，建议默认关闭用于 A/B 测试。
          </div>
          <a-space class="switch-row" wrap>
            <span>判停 end_window_size(ms)</span>
            <a-input-number v-model:value="form.params.end_window_size" :min="200" :max="5000" style="width: 140px" />
            <span>语义切句 vad_segment_duration(ms)</span>
            <a-input-number v-model:value="form.params.vad_segment_duration" :min="200" :max="10000" style="width: 140px" />
            <span>强制语音 force_to_speech_time(ms)</span>
            <a-input-number v-model:value="form.params.force_to_speech_time" :min="1" :max="10000" style="width: 140px" />
          </a-space>
          <a-divider orientation="left">平台词表</a-divider>
          <a-space class="switch-row" wrap>
            <span>启用平台热词</span>
            <a-switch v-model:checked="form.params.use_boosting_table" />
            <span>启用替换词表</span>
            <a-switch v-model:checked="form.params.use_correct_table" />
            <span>启用上下文热词</span>
            <a-switch v-model:checked="form.params.use_context_hotwords" />
          </a-space>
          <a-form-item label="平台热词表 ID">
            <a-input v-model:value="form.params.boosting_table_id" placeholder="自学习平台上设置的热词表 id，优先推荐填 ID" />
          </a-form-item>
          <a-form-item label="平台热词表名称">
            <a-input v-model:value="form.params.boosting_table_name" placeholder="自学习平台上设置的热词表名称，不填 ID 时可用名称" />
          </a-form-item>
          <a-form-item label="平台替换词表 ID">
            <a-input v-model:value="form.params.correct_table_id" placeholder="自学习平台上设置的替换词表 id" />
          </a-form-item>
          <a-form-item label="平台替换词表名称">
            <a-input v-model:value="form.params.correct_table_name" placeholder="自学习平台上设置的替换词表名称" />
          </a-form-item>
          <a-form-item label="热词列表">
            <a-textarea
              v-model:value="hotwordsText"
              :rows="5"
              placeholder="每行一个热词，例如：&#10;卵泡&#10;左卵巢&#10;右卵巢&#10;内膜厚度&#10;C型"
            />
            <div class="form-help">
              保存到模型 params.hotwords；调用豆包 ASR 时按“启用上下文热词”开关写入 request.corpus.context。平台词表字段写入 request.corpus。
            </div>
          </a-form-item>
          <a-form-item label="业务上下文">
            <a-textarea
              v-model:value="form.params.context_text"
              :rows="4"
              placeholder="例如：当前录音为辅助生殖阴道B超卵泡监测，医生会依次口述内膜、左右卵巢大小、左右卵泡尺寸。"
            />
            <div class="form-help">
              当未填写热词列表或关闭热词直传时，可作为 dialog_ctx 业务上下文传入 request.corpus.context。
            </div>
          </a-form-item>
        </a-card>
        <a-form-item name="api_key" :label="apiKeyLabel">
          <a-input-password v-model:value="form.api_key" :placeholder="apiKeyPlaceholder" />
        </a-form-item>
        <a-form-item name="api_secret" :label="apiSecretLabel">
          <a-input-password v-model:value="form.api_secret" />
        </a-form-item>
        <a-form-item name="secret_key" :label="secretKeyLabel">
          <a-input-password v-model:value="form.secret_key" :placeholder="secretKeyPlaceholder" />
        </a-form-item>
        <a-form-item name="is_default" label="设为默认">
          <a-switch v-model:checked="form.is_default" />
        </a-form-item>
        <a-form-item name="status" label="状态">
          <a-select v-model:value="form.status">
            <a-select-option value="active">启用</a-select-option>
            <a-select-option value="inactive">停用</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import type { FormInstance } from 'ant-design-vue'
import {
  PlusOutlined, ReloadOutlined, ApiOutlined,
} from '@ant-design/icons-vue'
import { modelApi } from '@/api/client'
import type { ModelConfig } from '@/types'

const models = ref<ModelConfig[]>([])
const loading = ref(false)
const saving = ref(false)
const modalOpen = ref(false)
const editing = ref<ModelConfig | null>(null)
const testing = ref<Record<number, boolean>>({})
const formRef = ref<FormInstance>()
const hotwordsText = ref('')

const form = reactive({
  name: '',
  model_type: 'asr',
  provider: 'local',
  endpoint: '',
  model_name: '',
  api_key: '',
  api_secret: '',
  secret_key: '',
  params: { audio_input_mode: 'segments' } as Record<string, any>,
  is_default: false,
  status: 'active',
})

const isMimoAsr = computed(() => form.model_type === 'asr' && form.provider === 'mimo')
const isVolcengineAsr = computed(() => form.model_type === 'asr' && form.provider === 'volcengine')

watch(
  () => [form.model_type, form.provider],
  () => {
    if (isMimoAsr.value) {
      form.params = {
        ...defaultParams(form.provider, form.model_type),
        ...(form.params || {}),
      }
    }
    if (isVolcengineAsr.value) {
      form.params = {
        ...defaultParams(form.provider, form.model_type),
        ...(form.params || {}),
      }
      hotwordsText.value = Array.isArray(form.params.hotwords) ? form.params.hotwords.join('\n') : ''
    }
  },
)

const apiKeyLabel = computed(() => {
  if (form.provider === 'iflytek_rtasr_llm') return 'accessKeyId'
  if (form.provider === 'tencent_speaker_ws') return 'SecretId'
  return 'API Key'
})

const apiKeyPlaceholder = computed(() => {
  if (form.provider === 'iflytek_rtasr_llm') return '讯飞 accessKeyId'
  if (form.provider === 'tencent_speaker_ws') return '腾讯云 SecretId'
  return '留空则不设置'
})

const apiSecretLabel = computed(() => {
  if (form.provider === 'iflytek_rtasr_llm') return 'accessKeySecret'
  if (form.provider === 'tencent_speaker_ws') return 'SecretKey'
  return 'API Secret / Access Token（可选）'
})

const secretKeyLabel = computed(() => {
  if (form.provider === 'iflytek_rtasr_llm' || form.provider === 'tencent_speaker_ws') return 'AppID'
  return 'Secret Key（签名密钥，可选）'
})

const secretKeyPlaceholder = computed(() => {
  if (form.provider === 'iflytek_rtasr_llm') return '讯飞 AppID'
  if (form.provider === 'tencent_speaker_ws') return '腾讯云 AppID'
  return '豆包/火山引擎签名用'
})

async function fetchModels() {
  loading.value = true
  try {
    const [asr, llm] = await Promise.all([
      modelApi.list('asr'),
      modelApi.list('llm'),
    ])
    models.value = [...(asr as ModelConfig[]), ...(llm as ModelConfig[])]
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchModels()
  modelApi.initDefaults().catch(() => {})
})

async function handleTest(id: number) {
  testing.value[id] = true
  try {
    const res: any = await modelApi.test(id)
    if (res.success) message.success(`连通 (${res.latency_ms}ms)`)
    else message.error(`不通: ${res.message}`)
  } finally {
    testing.value[id] = false
  }
}

async function handleSave(values: any) {
  saving.value = true
  try {
    const nextParams = { ...(form.params || {}) }
    if (isMimoAsr.value) {
      nextParams.audio_input_mode = nextParams.audio_input_mode || 'segments'
      nextParams.language = nextParams.language || 'auto'
      nextParams.stream = !!nextParams.stream
      nextParams.merge_group_size = Number(nextParams.merge_group_size || 3)
      nextParams.max_base64_mb = Number(nextParams.max_base64_mb || 9.8)
    }
    if (isVolcengineAsr.value) {
      nextParams.audio_input_mode = nextParams.audio_input_mode || 'segments'
      nextParams.endpoint_mode = nextParams.endpoint_mode || 'bigmodel_nostream'
      nextParams.result_type = nextParams.result_type || 'full'
      nextParams.enable_itn = nextParams.enable_itn !== false
      nextParams.enable_punc = nextParams.enable_punc !== false
      nextParams.enable_ddc = !!nextParams.enable_ddc
      nextParams.show_utterances = nextParams.show_utterances === true
      nextParams.enable_nonstream = !!nextParams.enable_nonstream
      nextParams.use_boosting_table = nextParams.use_boosting_table !== false
      nextParams.use_correct_table = nextParams.use_correct_table !== false
      nextParams.use_context_hotwords = nextParams.use_context_hotwords !== false
      const hotwords = hotwordsText.value
        .split(/\r?\n|,|，/)
        .map((word) => word.trim())
        .filter(Boolean)
      if (hotwords.length) nextParams.hotwords = Array.from(new Set(hotwords))
      else delete nextParams.hotwords
      ;['boosting_table_id', 'boosting_table_name', 'correct_table_id', 'correct_table_name', 'context_text'].forEach((key) => {
        if (nextParams[key] === undefined || nextParams[key] === null || String(nextParams[key]).trim() === '') {
          delete nextParams[key]
        } else {
          nextParams[key] = String(nextParams[key]).trim()
        }
      })
      ;['end_window_size', 'vad_segment_duration', 'force_to_speech_time'].forEach((key) => {
        if (nextParams[key] === undefined || nextParams[key] === null || nextParams[key] === '') {
          delete nextParams[key]
        } else {
          nextParams[key] = Number(nextParams[key])
        }
      })
    }
    const nextValues = { ...values }
    if (isVolcengineAsr.value) {
      nextValues.endpoint = volcengineEndpointByMode(nextParams.endpoint_mode)
    }
    const payload = {
      ...nextValues,
      params: nextParams,
    }
    if (editing.value) {
      await modelApi.update(editing.value.id, payload)
      message.success('更新成功')
    } else {
      await modelApi.create(payload)
      message.success('创建成功')
    }
    modalOpen.value = false
    editing.value = null
    await fetchModels()
  } catch {
    // interceptor handles error
  } finally {
    saving.value = false
  }
}

async function handleSubmit() {
  try {
    const values = await formRef.value?.validate()
    if (values) await handleSave(values)
  } catch {
    // validation failed
  }
}

function handleCancel() {
  modalOpen.value = false
  editing.value = null
}

async function handleDelete(id: number) {
  await modelApi.delete(id)
  message.success('删除成功')
  await fetchModels()
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    name: '', model_type: 'asr', provider: 'local', endpoint: '',
    model_name: '', api_key: '', api_secret: '', secret_key: '',
    params: defaultParams('local', 'asr'),
    is_default: false, status: 'active',
  })
  hotwordsText.value = ''
  modalOpen.value = true
}

function openEdit(record: ModelConfig) {
  editing.value = record
  Object.assign(form, {
    ...record,
    params: {
      ...defaultParams(record.provider, record.model_type),
      ...(record.params || {}),
    },
  })
  hotwordsText.value = Array.isArray(form.params.hotwords) ? form.params.hotwords.join('\n') : ''
  modalOpen.value = true
}

function defaultParams(provider: string, modelType: string) {
  if (modelType === 'asr' && provider === 'mimo') {
    return {
      audio_input_mode: 'segments',
      language: 'auto',
      stream: true,
      merge_group_size: 3,
      max_base64_mb: 9.8,
    }
  }
  if (modelType === 'asr' && provider === 'volcengine') {
    return {
      audio_input_mode: 'segments',
      endpoint_mode: 'bigmodel_nostream',
      result_type: 'full',
      enable_itn: true,
      enable_punc: true,
      enable_ddc: false,
      show_utterances: false,
      enable_nonstream: false,
      use_boosting_table: true,
      use_correct_table: true,
      use_context_hotwords: true,
      hotwords: [],
    }
  }
  return {}
}

function volcengineEndpointByMode(mode: string) {
  if (mode === 'bigmodel') return 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel'
  if (mode === 'bigmodel_async') return 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async'
  return 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream'
}

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '类型', dataIndex: 'model_type', key: 'model_type' },
  { title: 'Provider', dataIndex: 'provider', key: 'provider' },
  { title: 'Endpoint', dataIndex: 'endpoint', key: 'endpoint', ellipsis: true },
  { title: '状态', dataIndex: 'status', key: 'status' },
  { title: '默认', dataIndex: 'is_default', key: 'is_default' },
  { title: '操作', key: 'actions' },
]
</script>

<style scoped>
.form-help {
  margin-top: 6px;
  color: #888;
  font-size: 12px;
}
</style>
