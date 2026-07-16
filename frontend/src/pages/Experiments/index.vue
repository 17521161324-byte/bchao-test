<template>
  <div class="page-container">
    <div class="page-header">
      <h2>批量实验</h2>
      <a-button type="primary" @click="showCreateModal"><PlusOutlined /> 新建实验</a-button>
    </div>

    <!-- 实验批次列表 -->
    <a-card>
      <a-table
        :data-source="experiments"
        :loading="loading"
        row-key="id"
        :scroll="{ x: 1500 }"
        :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }"
      >
        <a-table-column title="ID" data-index="id" :width="60" />
        <a-table-column title="实验名称" data-index="name" :width="150" />
        <a-table-column title="状态" :width="100">
          <template #default="scope"><a-tag :color="statusColor(scope?.record?.status)">{{ scope?.record?.status }}</a-tag></template>
        </a-table-column>
        <a-table-column title="ASR模型" :width="130">
          <template #default="scope">{{ scope?.record?.asr_model_name || '-' }}</template>
        </a-table-column>
        <a-table-column title="LLM模型" :width="130">
          <template #default="scope">{{ scope?.record?.llm_model_name || '-' }}</template>
        </a-table-column>
        <a-table-column title="提示词模板" :width="140">
          <template #default="scope">{{ scope?.record?.prompt_template_name || '-' }}</template>
        </a-table-column>
        <a-table-column title="日期批次" :width="180">
          <template #default="scope">{{ scope?.record?.selected_dates?.join(', ') || '-' }}</template>
        </a-table-column>
        <a-table-column title="患者数" :width="70">
          <template #default="scope">{{ scope?.record?.patient_count || 0 }}人</template>
        </a-table-column>
        <a-table-column title="右卵泡" :width="80">
          <template #default="scope">{{ formatAcc(scope?.record?.field_accuracy?.right_follicle) }}</template>
        </a-table-column>
        <a-table-column title="左卵泡" :width="80">
          <template #default="scope">{{ formatAcc(scope?.record?.field_accuracy?.left_follicle) }}</template>
        </a-table-column>
        <a-table-column title="内膜厚度" :width="80">
          <template #default="scope">{{ formatAcc(scope?.record?.field_accuracy?.endometrium_thickness) }}</template>
        </a-table-column>
        <a-table-column title="内膜类型" :width="80">
          <template #default="scope">{{ formatAcc(scope?.record?.field_accuracy?.endometrium_type) }}</template>
        </a-table-column>
        <a-table-column title="右卵巢" :width="80">
          <template #default="scope">{{ formatAcc(scope?.record?.field_accuracy?.right_ovary) }}</template>
        </a-table-column>
        <a-table-column title="左卵巢" :width="80">
          <template #default="scope">{{ formatAcc(scope?.record?.field_accuracy?.left_ovary) }}</template>
        </a-table-column>
        <a-table-column title="总任务" data-index="total_tasks" :width="70" />
        <a-table-column title="成功" data-index="success_count" :width="60" />
        <a-table-column title="失败" data-index="failure_count" :width="60" />
        <a-table-column title="操作" :width="120" fixed="right">
          <template #default="scope">
            <router-link v-if="scope?.record?.id" :to="`/experiments/${scope.record.id}`">
              <a-button size="small" type="link">详情</a-button>
            </router-link>
            <a-popconfirm v-if="scope?.record?.id" title="确定删除此实验？" @confirm="handleDelete(scope.record.id)">
              <a-button size="small" type="link" danger>删除</a-button>
            </a-popconfirm>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <!-- 新建实验弹窗（单组合设计）-->
    <a-modal
      v-model:open="createModalOpen"
      title="新建实验"
      width="700px"
      :confirm-loading="creating"
      @ok="handleCreate"
    >
      <a-form layout="vertical" size="small">
        <a-form-item label="实验名称" required>
          <a-input v-model:value="createForm.name" placeholder="输入实验名称" />
        </a-form-item>

        <a-form-item label="描述">
          <a-textarea v-model:value="createForm.description" :rows="2" />
        </a-form-item>

        <a-form-item label="备注">
          <a-textarea v-model:value="createForm.remark" :rows="2" placeholder="可选：补充说明内部可见" />
        </a-form-item>

        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="ASR 模型" required>
              <a-select v-model:value="createForm.asr_model_id" placeholder="选择 ASR 模型" show-search allow-clear>
                <a-select-option v-for="m in asrModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="LLM 模型">
              <a-select v-model:value="createForm.llm_model_id" placeholder="不使用 LLM" allow-clear show-search>
                <a-select-option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="提示词模板">
          <a-select v-model:value="createForm.prompt_template_id" placeholder="选择提示词模板（可选）" allow-clear show-search @change="onPromptTemplateChange">
            <a-select-option v-for="t in promptTemplates" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
          </a-select>
        </a-form-item>

        <a-form-item label="提示词内容">
          <a-textarea v-model:value="createForm.prompt_content" :rows="4" placeholder="提示词内容..." />
        </a-form-item>

        <a-form-item label="热词（每行一个）">
          <a-textarea v-model:value="hotwordsRaw" :rows="2" placeholder="卵泡&#10;内膜&#10;卵巢" />
        </a-form-item>

        <a-form-item label="选择日期批次" required>
          <a-select v-model:value="createForm.selected_dates" mode="multiple" placeholder="选择日期批次">
            <a-select-option v-for="d in availableDates" :key="d.date" :value="d.date">
              {{ d.date }} ({{ d.patient_count }}人)
            </a-select-option>
          </a-select>
        </a-form-item>

        <!-- 选中日期后的患者列表 -->
        <a-card v-if="createForm.selected_dates.length > 0" size="small" style="margin-top: 8px">
          <template #title>
            选择参与实验的患者 ({{ createForm.selected_patient_ids.length }}/{{ availablePatients.length }})
          </template>
          <a-table
            :data-source="availablePatients"
            :loading="loadingPatients"
            size="small"
            :pagination="{ pageSize: 8 }"
            row-key="uid"
          >
            <a-table-column title="选择" :width="60">
              <template #default="scope">
                <a-checkbox :checked="createForm.selected_patient_ids.includes(scope?.record?.uid)" @change="togglePatient(scope?.record?.uid)" />
              </template>
            </a-table-column>
            <a-table-column title="病历号" data-index="record_id" />
            <a-table-column title="日期" data-index="date" :width="120" />
            <a-table-column title="录音" :width="60">
              <template #default="scope">
                <a-tag :color="scope?.record?.has_audio ? 'green' : 'red'" size="small">{{ scope?.record?.has_audio ? '有' : '无' }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column title="结果" :width="60">
              <template #default="scope">
                <a-tag :color="scope?.record?.has_result ? 'green' : 'default'" size="small">{{ scope?.record?.has_result ? '有' : '无' }}</a-tag>
              </template>
            </a-table-column>
          </a-table>
        </a-card>
      </a-form>
    </a-modal>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { experimentApi } from '@/api/experiment'
import { audioApi, modelApi, promptTemplateApi } from '@/api/client'

export default defineComponent({
  name: 'Experiments',
  setup() {
    const loading = ref(false)
    const experiments = ref<any[]>([])
    const availableDates = ref<any[]>([])
    const asrModels = ref<any[]>([])
    const llmModels = ref<any[]>([])
    const promptTemplates = ref<any[]>([])
    const createModalOpen = ref(false)
    const creating = ref(false)
    const loadingPatients = ref(false)
    const availablePatients = ref<any[]>([])
    const hotwordsRaw = ref('')

    const createForm = reactive({
      name: '',
      description: '',
      remark: '',
      asr_model_id: null as number | null,
      llm_model_id: null as number | null,
      prompt_template_id: undefined as number | undefined,
      prompt_name: '',
      prompt_content: '',
      selected_dates: [] as string[],
      selected_patient_ids: [] as string[],
    })

    async function fetchExperiments() {
      loading.value = true
      try {
        const res = await experimentApi.list()
        let data: any[] = []
        if (Array.isArray(res)) {
          data = res
        } else if (res && Array.isArray(res.data)) {
          data = res.data
        }
        experiments.value = data.filter(Boolean).map((e: any) => ({
          ...e,
          field_accuracy: e.field_accuracy || {},
          selected_dates: e.selected_dates || [],
          asr_model_name: e.asr_model_name || '',
          llm_model_name: e.llm_model_name || '',
          prompt_template_name: e.prompt_template_name || '',
          total_tasks: e.total_tasks || 0,
          success_count: e.success_count || 0,
          failure_count: e.failure_count || 0,
          patient_count: e.patient_count || 0,
        }))
      } catch (e) {
        experiments.value = []
      } finally {
        loading.value = false
      }
    }

    async function loadModels() {
      try {
        const [asr, llm] = await Promise.all([modelApi.list('asr'), modelApi.list('llm')])
        asrModels.value = Array.isArray(asr) ? asr : (asr.data || [])
        llmModels.value = Array.isArray(llm) ? llm : (llm.data || [])
      } catch {}
    }

    async function loadPromptTemplates() {
      try {
        const res = await promptTemplateApi.list()
        promptTemplates.value = Array.isArray(res) ? res : (res.data || [])
      } catch {}
    }

    function onPromptTemplateChange(id: number | undefined) {
      if (id == null) {
        createForm.prompt_template_id = undefined
        createForm.prompt_name = ''
        createForm.prompt_content = ''
        return
      }

      createForm.prompt_template_id = id

      const tmpl = promptTemplates.value.find((t: any) => t.id === id)
      if (tmpl) {
        createForm.prompt_name = tmpl.name
        createForm.prompt_content = tmpl.content
      }
    }

    async function fetchBatches() {
      try {
        const res = await audioApi.getBatches()
        const data = (res as any)?.data || res
        availableDates.value = Array.isArray(data) ? data : []
      } catch (e) {
        console.error(e)
        availableDates.value = []
      }
    }

    async function fetchPatientsForDates(dates: string[]) {
      if (!dates.length) {
        availablePatients.value = []
        return
      }
      loadingPatients.value = true
      try {
        const patients: any[] = []
        for (const date of dates) {
          const res = await audioApi.getRecords(date)
          const records = (res as any)?.data || res
          for (const exam of (Array.isArray(records) ? records : [])) {
            const uid = `${date}-${exam.record_id}`
            patients.push({
              uid,
              record_id: exam.record_id,
              date,
              has_audio: exam.has_audio,
              has_result: exam.has_result,
            })
          }
        }
        availablePatients.value = patients
        createForm.selected_patient_ids = patients.map(p => p.uid)
      } finally {
        loadingPatients.value = false
      }
    }

    function showCreateModal() {
      createForm.name = ''
      createForm.description = ''
      createForm.remark = ''
      createForm.asr_model_id = null
      createForm.llm_model_id = null
      createForm.prompt_template_id = undefined
      createForm.prompt_name = ''
      createForm.prompt_content = ''
      createForm.selected_dates = []
      createForm.selected_patient_ids = []
      hotwordsRaw.value = ''
      createModalOpen.value = true
      fetchBatches()
      loadModels()
      loadPromptTemplates()
    }

    function togglePatient(uid: string | undefined) {
      if (!uid) return
      const idx = createForm.selected_patient_ids.indexOf(uid)
      if (idx >= 0) createForm.selected_patient_ids.splice(idx, 1)
      else createForm.selected_patient_ids.push(uid)
    }

    async function handleCreate() {
      if (!createForm.name.trim()) {
        message.error('请输入实验名称')
        return
      }
      if (!createForm.selected_dates.length) {
        message.error('请选择日期批次')
        return
      }
      if (!createForm.asr_model_id) {
        message.error('请选择 ASR 模型')
        return
      }
      // 如果配置了 LLM，必须有提示词
      if (createForm.llm_model_id && !createForm.prompt_content) {
        message.error('请选择提示词模板或填写提示词内容')
        return
      }
      creating.value = true
      try {
        // 提交时把 uid (date-record_id) 还原为 record_id
        const recordIds = [...new Set(createForm.selected_patient_ids.map(uid => uid.split('-').slice(1).join('-')))]
        await experimentApi.create({
          name: createForm.name,
          description: createForm.description,
          remark: createForm.remark,
          selected_dates: createForm.selected_dates,
          selected_patient_ids: recordIds,
          asr_model_id: createForm.asr_model_id,
          llm_model_id: createForm.llm_model_id || null,
          prompt_template_id: createForm.prompt_template_id,
          prompt_name: createForm.prompt_name,
          prompt_template: createForm.prompt_content,
          hotwords: hotwordsRaw.value.split('\n').map((s: string) => s.trim()).filter(Boolean),
        })
        message.success('创建成功')
        createModalOpen.value = false
        fetchExperiments()
      } catch {
        message.error('创建失败')
      } finally {
        creating.value = false
      }
    }

    async function handleDelete(id: number) {
      try {
        await experimentApi.delete(id)
        message.success('删除成功')
        fetchExperiments()
      } catch {
        message.error('删除失败')
      }
    }

    function statusColor(status: string): string {
      const map: Record<string, string> = { pending: 'default', running: 'blue', paused: 'orange', partial: 'purple', completed: 'green', cancelled: 'red' }
      return map[status] || 'default'
    }

    function formatAcc(val: number | undefined): string {
      if (val == null || isNaN(val)) return '-'
      return (val * 100).toFixed(0) + '%'
    }

    watch(() => createForm.selected_dates, fetchPatientsForDates)

    onMounted(() => {
      fetchExperiments()
    })

    return {
      loading, experiments, availableDates, createModalOpen, creating, loadingPatients, availablePatients,
      asrModels, llmModels, promptTemplates, hotwordsRaw,
      createForm, showCreateModal, togglePatient, handleCreate, handleDelete, statusColor, formatAcc,
      onPromptTemplateChange,
      PlusOutlined,
    }
  },
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
