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
      @ok="handleOk"
      :width="600"
    >
      <a-form ref="formRef" :model="form" layout="vertical" @finish="handleSave">
        <a-form-item name="name" label="名称" :rules="[{ required: true, message: '请输入名称' }]">
          <a-input v-model:value="form.name" placeholder="如：本地 FunASR" />
        </a-form-item>
        <a-form-item name="model_type" label="类型" :rules="[{ required: true, message: '请选择类型' }]">
          <a-select v-model:value="form.model_type">
            <a-select-option value="asr">ASR（语音转文字）</a-select-option>
            <a-select-option value="llm">LLM（语义理解）</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item name="provider" label="Provider" :rules="[{ required: true, message: '请选择Provider' }]">
          <a-select v-model:value="form.provider">
            <a-select-option value="local">本地</a-select-option>
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
        <a-form-item name="api_key" label="API Key">
          <a-input-password v-model:value="form.api_key" placeholder="留空则不设置" />
        </a-form-item>
        <a-form-item name="api_secret" label="API Secret（可选）">
          <a-input-password v-model:value="form.api_secret" />
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
import { onMounted, reactive, ref } from 'vue'
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

const form = reactive({
  name: '',
  model_type: 'asr',
  provider: 'local',
  endpoint: '',
  model_name: '',
  api_key: '',
  api_secret: '',
  is_default: false,
  status: 'active',
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
    if (editing.value) {
      await modelApi.update(editing.value.id, values)
      message.success('更新成功')
    } else {
      await modelApi.create(values)
      message.success('创建成功')
    }
    modalOpen.value = false
    editing.value = null
    await fetchModels()
  } catch {
    // 拦截器已处理
  } finally {
    saving.value = false
  }
}

async function handleOk() {
  try {
    await formRef.value?.validate()
    // validate() passes → @finish fires → handleSave runs
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
    model_name: '', api_key: '', api_secret: '', is_default: false, status: 'active',
  })
  modalOpen.value = true
}

function openEdit(record: ModelConfig) {
  editing.value = record
  Object.assign(form, record)
  modalOpen.value = true
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
