<template>
  <div class="page-container">
    <div class="page-header"><h2>新建实验</h2></div>

    <a-form layout="vertical">
      <a-form-item label="实验名称">
        <a-input v-model:value="form.name" placeholder="输入实验名称" />
      </a-form-item>

      <a-form-item label="描述">
        <a-textarea v-model:value="form.description" :rows="2" />
      </a-form-item>

      <a-form-item label="选择日期批次">
        <a-select v-model:value="form.selected_dates" mode="multiple" placeholder="选择日期批次">
          <a-select-option v-for="d in availableDates" :key="d.date" :value="d.date">
            {{ d.date }} ({{ d.patient_count }}人)
          </a-select-option>
        </a-select>
      </a-form-item>

      <!-- 选中日期后显示患者列表 -->
      <a-card v-if="form.selected_dates.length > 0" size="small" style="margin-bottom: 16px">
        <template #title>
          选择参与实验的患者
          <a-radio-group v-model:value="patientSelectMode" size="small" style="margin-left: 16px">
            <a-radio-button value="all">全选</a-radio-button>
            <a-radio-button value="none">清空</a-radio-button>
          </a-radio-group>
        </template>

        <a-table
          :data-source="availablePatients"
          :loading="loadingPatients"
          :pagination="{ pageSize: 10, total: availablePatients.length }"
          size="small"
          row-key="record_id"
        >
          <a-table-column title="选择" :width="60">
            <template #default="{ record }">
              <a-checkbox :checked="isPatientSelected(record.record_id)" @change="togglePatient(record.record_id)" />
            </template>
          </a-table-column>
          <a-table-column title="病历号" data-index="record_id" />
          <a-table-column title="日期" data-index="date_folder_str" :width="120" />
          <a-table-column title="有录音" :width="80">
            <template #default="{ record }">
              <a-tag :color="record.has_audio ? 'green' : 'red'">{{ record.has_audio ? '有' : '无' }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="有结果" :width="80">
            <template #default="{ record }">
              <a-tag :color="record.has_result ? 'green' : 'default'">{{ record.has_result ? '有' : '无' }}</a-tag>
            </template>
          </a-table-column>
        </a-table>
      </a-card>

      <a-form-item>
        <a-button type="primary" @click="handleCreate" :loading="creating">创建</a-button>
        <router-link to="/experiments"><a-button style="margin-left: 8px">取消</a-button></router-link>
      </a-form-item>
    </a-form>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { experimentApi } from '@/api/experiment'
import { audioApi } from '@/api/client'

export default defineComponent({
  name: 'CreateExperiment',
  setup() {
    const router = useRouter()
    const creating = ref(false)
    const loadingPatients = ref(false)
    const patientSelectMode = ref('all')

    const form = reactive({
      name: '',
      description: '',
      selected_dates: [] as string[],
      selected_patient_ids: [] as string[],
    })

    const availableDates = ref<{date: string, patient_count: number}[]>([])
    const availablePatients = ref<any[]>([])
    const allPatientIds = ref<string[]>([])

    async function fetchBatches() {
      try {
        const res = await audioApi.getBatches()
        availableDates.value = res.data
      } catch (e) {
        console.error('Failed to fetch batches:', e)
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
          for (const exam of res.data) {
            patients.push({
              record_id: exam.record_id,
              date_folder_str: date,
              has_audio: exam.has_audio,
              has_result: exam.has_result,
            })
          }
        }
        availablePatients.value = patients
        allPatientIds.value = patients.map(p => p.record_id)
        // Default: all selected
        form.selected_patient_ids = [...allPatientIds.value]
      } catch (e) {
        console.error('Failed to fetch patients:', e)
      } finally {
        loadingPatients.value = false
      }
    }

    function isPatientSelected(recordId: string): boolean {
      return form.selected_patient_ids.includes(recordId)
    }

    function togglePatient(recordId: string): void {
      const idx = form.selected_patient_ids.indexOf(recordId)
      if (idx >= 0) {
        form.selected_patient_ids.splice(idx, 1)
      } else {
        form.selected_patient_ids.push(recordId)
      }
    }

    watch(patientSelectMode, (mode) => {
      if (mode === 'all') {
        form.selected_patient_ids = [...allPatientIds.value]
      } else if (mode === 'none') {
        form.selected_patient_ids = []
      }
    })

    watch(() => form.selected_dates, (newDates) => {
      fetchPatientsForDates(newDates)
    })

    async function handleCreate() {
      if (!form.name.trim()) {
        message.error('请输入实验名称')
        return
      }
      if (!form.selected_dates.length) {
        message.error('请选择日期批次')
        return
      }
      creating.value = true
      try {
        const res = await experimentApi.create(form)
        message.success('创建成功')
        router.push(`/experiments/${res.data.id}`)
      } catch {
        message.error('创建失败')
      } finally {
        creating.value = false
      }
    }

    onMounted(fetchBatches)

    return { form, availableDates, availablePatients, loadingPatients, patientSelectMode, isPatientSelected, togglePatient, handleCreate, creating }
  },
})
</script>

<style scoped>
</style>
