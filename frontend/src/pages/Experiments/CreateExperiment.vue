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
          <a-select-option v-for="d in availableDates" :key="d" :value="t">{{ d }}</a-select-option>
        </a-select>
      </a-form-item>

      <a-form-item label="选择患者">
        <a-select v-model:value="form.selected_patient_ids" mode="multiple" placeholder="留空表示所有患者">
          <a-select-option v-for="p in availablePatients" :key="p" :value="t">{{ p }}</a-select-option>
        </a-select>
      </a-form-item>

      <a-form-item>
        <a-button type="primary" @click="handleCreate" :loading="creating">创建</a-button>
      </a-form-item>
    </a-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { experimentApi } from '@/api/experiment'
import { audioApi } from '@/api/client'

const router = useRouter()
const creating = ref(false)

const form = reactive({
  name: '',
  description: '',
  selected_dates: [] as string[],
  selected_patient_ids: [] as string[],
})

const availableDates = ref<string[]>([])
const availablePatients = ref<string[]>([])

// Load available dates
onMounted(async () => {
  try {
    const res = await audioApi.getBatches()
    availableDates.value = res.data.map((b: any) => b.date)
  } catch (e) {
    // ignore
  }
})

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
</script>
