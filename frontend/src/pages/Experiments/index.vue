<template>
  <div class="page-container">
    <div class="page-header">
      <h2>批量实验</h2>
      <a-button type="primary" @click="showCreateModal"><PlusOutlined />新建实验</a-button>
    </div>

    <!-- 实验批次列表 -->
    <a-card>
      <a-table
        :data-source="experiments"
        :loading="loading"
        row-key="id"
        :scroll="{ x: 1600 }"
      >
        <a-table-column title="ID" data-index="id" :width="60" />
        <a-table-column title="实验名称" data-index="name" :width="150" />
        <a-table-column title="状态" :width="100">
          <template #default="{ record }">
            <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="日期批次" :width="180">
          <template #default="{ record }">
            {{ record.selected_dates?.join(', ') || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="患者数" :width="70">
          <template #default="{ record }">{{ record.patient_count || 0 }}人</template>
        </a-table-column>
        <!-- 各字段准确率 -->
        <a-table-column title="内膜厚度" :width="90">
          <template #default="{ record }">{{ formatAcc(record.field_accuracy?.endometrium_thickness) }}</template>
        </a-table-column>
        <a-table-column title="内膜类型" :width="90">
          <template #default="{ record }">{{ formatAcc(record.field_accuracy?.endometrium_type) }}</template>
        </a-table-column>
        <a-table-column title="卵巢" :width="80">
          <template #default="{ record }">{{ formatAcc(record.field_accuracy?.ovary_size) }}</template>
        </a-table-column>
        <a-table-column title="卵泡" :width="80">
          <template #default="{ record }">{{ formatAcc(record.field_accuracy?.follicle) }}</template>
        </a-table-column>
        <a-table-column title="备注" :width="80">
          <template #default="{ record }">{{ formatAcc(record.field_accuracy?.remark) }}</template>
        </a-table-column>
        <!-- 模型信息 -->
        <a-table-column title="ASR模型" :width="120">
          <template #default="{ record }">{{ record.asr_models?.join(', ') || '-' }}</template>
        </a-table-column>
        <a-table-column title="LLM模型" :width="120">
          <template #default="{ record }">{{ record.llm_models?.join(', ') || '-' }}</template>
        </a-table-column>
        <a-table-column title="提示词模板" :width="120">
          <template #default="{ record }">{{ record.prompt_templates?.join(', ') || '-' }}</template>
        </a-table-column>
        <a-table-column title="总任务" data-index="total_tasks" :width="70" />
        <a-table-column title="成功" data-index="success_count" :width="60" />
        <a-table-column title="失败" data-index="failure_count" :width="60" />
        <a-table-column title="创建时间" data-index="created_at" :width="160" />
        <a-table-column title="操作" :width="120" fixed="right">
          <template #default="{ record }">
            <router-link :to="`/experiments/${record.id}`"><a-button size="small" type="link">详情</a-button></router-link>
            <a-popconfirm title="确定删除此实验？" @confirm="handleDelete(record.id)">
              <a-button size="small" type="link" danger>删除</a-button>
            </a-popconfirm>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <!-- 新建实验弹窗 -->
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
            row-key="record_id"
          >
            <a-table-column title="选择" :width="60">
              <template #default="{ record }">
                <a-checkbox :checked="createForm.selected_patient_ids.includes(record.record_id)" @change="togglePatient(record.record_id)" />
              </template>
            </a-table-column>
            <a-table-column title="病历号" data-index="record_id" />
            <a-table-column title="日期" data-index="date" :width="120" />
            <a-table-column title="录音" :width="60">
              <template #default="{ record }">
                <a-tag :color="record.has_audio ? 'green' : 'red'" size="small">{{ record.has_audio ? '有' : '无' }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column title="结果" :width="60">
              <template #default="{ record }">
                <a-tag :color="record.has_result ? 'green' : 'default'" size="small">{{ record.has_result ? '有' : '无' }}</a-tag>
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
import { audioApi } from '@/api/client'

export default defineComponent({
  name: 'Experiments',
  setup() {
    const loading = ref(false)
    const experiments = ref<any[]>([])
    const availableDates = ref<any[]>([])
    const createModalOpen = ref(false)
    const creating = ref(false)
    const loadingPatients = ref(false)
    const availablePatients = ref<any[]>([])

    const createForm = reactive({
      name: '',
      description: '',
      remark: '',
      selected_dates: [] as string[],
      selected_patient_ids: [] as string[],
    })

    async function fetchExperiments() {
      loading.value = true
      try {
        const res = await experimentApi.list()
        // 处理多种可能的响应格式
        if (Array.isArray(res)) {
          experiments.value = res
        } else if (res && Array.isArray(res.data)) {
          experiments.value = res.data
        } else {
          experiments.value = []
        }
      } catch (e) {
        experiments.value = []
      } finally {
        loading.value = false
      }
    }

    async function fetchBatches() {
      try {
        const res = await audioApi.getBatches()
        availableDates.value = res
      } catch (e) {
        console.error(e)
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
          for (const exam of res) {
            patients.push({
              record_id: exam.record_id,
              date,
              has_audio: exam.has_audio,
              has_result: exam.has_result,
            })
          }
        }
        availablePatients.value = patients
        createForm.selected_patient_ids = patients.map(p => p.record_id)
      } finally {
        loadingPatients.value = false
      }
    }

    function showCreateModal() {
      createForm.name = ''
      createForm.description = ''
      createForm.remark = ''
      createForm.selected_dates = []
      createForm.selected_patient_ids = []
      createModalOpen.value = true
      fetchBatches()
    }

    function togglePatient(recordId: string) {
      const idx = createForm.selected_patient_ids.indexOf(recordId)
      if (idx >= 0) createForm.selected_patient_ids.splice(idx, 1)
      else createForm.selected_patient_ids.push(recordId)
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
      creating.value = true
      try {
        await experimentApi.create(createForm)
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
      createForm, showCreateModal, togglePatient, handleCreate, handleDelete, statusColor, formatAcc,
      PlusOutlined,
    }
  },
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
