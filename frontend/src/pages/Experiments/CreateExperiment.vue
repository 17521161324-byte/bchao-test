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
        <a-select v-model:value="form.selected_dates" mode="multiple" placeholder="选择日期批次" @change="onDatesChange">
          <a-select-option v-for="d in availableDates" :key="d.date" :value="d.date">
            {{ d.date }} ({{ d.patient_count }}人)
          </a-select-option>
        </a-select>
      </a-form-item>

      <!-- 选中日期后的统计 -->
      <a-card v-if="form.selected_dates.length > 0" size="small" style="margin-bottom: 16px; background: #fafafa">
        <a-row :gutter="16">
          <a-col :span="8">日期批次数: {{ form.selected_dates.length }}</a-col>
          <a-col :span="8">患者总数: {{ selectedPatientCount }}</a-col>
          <a-col :span="8">预计任务数: {{ estimatedTasks }}</a-col>
        </a-row>
      </a-card>

      <a-form-item>
        <a-button type="primary" @click="handleCreate" :loading="creating">创建</a-button>
      </a-form-item>
    </a-form>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { experimentApi } from '@/api/experiment'
import { audioApi } from '@/api/client'

export default defineComponent({
  name: 'CreateExperiment',
  setup() {
    const router = useRouter()
    const creating = ref(false)

    const form = reactive({
      name: '',
      description: '',
      selected_dates: [] as string[],
      selected_patient_ids: [] as string[],
    })

    const availableDates = ref<{date: string, patient_count: number}[]>([])

    const selectedPatientCount = computed(() => {
      return availableDates.value
        .filter(d => form.selected_dates.includes(d.date))
        .reduce((sum, d) => sum + d.patient_count, 0)
    })

    const estimatedTasks = computed(() => {
      // Will be multiplied by number of combinations (at least 1)
      return selectedPatientCount.value
    })

    async function fetchData() {
      try {
        const res = await audioApi.getBatches()
        availableDates.value = res.data
      } catch (e) {
        // ignore
      }
    }

    function onDatesChange() {
      // Triggered when dates selection changes
    }

    async function handleCreate() {
      if (!form.name.trim()) {
        message.error('请输入实验名称')
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

    onMounted(fetchData)

    return {
      form, availableDates, selectedPatientCount, estimatedTasks,
      handleCreate, onDatesChange, creating,
    }
  },
})
</script>

<style scoped>
</style>
