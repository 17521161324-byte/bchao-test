<template>
  <div class="page-container">
    <div class="page-header"><h2>数据管理</h2></div>

    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="6">
        <a-card><a-statistic title="日期数" :value="dataStatus?.total_dates ?? 0" /></a-card>
      </a-col>
      <a-col :span="6">
        <a-card><a-statistic title="总病历数" :value="dataStatus?.total_patients ?? 0" /></a-card>
      </a-col>
      <a-col :span="6">
        <a-card>
          <a-statistic title="已匹配" :value="dataStatus?.matched_count ?? 0" :value-style="{ color: '#52c41a' }" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card>
          <a-statistic title="仅录音" :value="dataStatus?.audio_only_count ?? 0" :value-style="{ color: '#faad14' }" />
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="16">
      <a-col :span="16">
        <a-card title="录音文件树" :extra="null">
          <template #extra>
            <a-button @click="handleScan"><ScanOutlined />扫描目录</a-button>
          </template>
          <a-spin v-if="loadingTree" />
          <a-empty v-else-if="audioTree.length === 0" description="暂无数据" />
          <a-tree v-else :tree-data="treeData" show-icon default-expand-all>
            <template #title="{ dataRef }">
              <span>{{ dataRef.title }}</span>
            </template>
            <template #icon="{ key }">
              <FolderOutlined v-if="String(key).startsWith('date-')" />
              <CustomerServiceOutlined v-else />
            </template>
          </a-tree>
        </a-card>
      </a-col>

      <a-col :span="8">
        <a-card title="导入 B 超结果">
          <a-upload-dragger
            accept=".xlsx,.xls"
            :before-upload="handleUpload"
            :show-upload-list="false"
            :disabled="uploading"
          >
            <p class="ant-upload-drag-icon"><CloudUploadOutlined style="font-size: 32px; color: #1677ff" /></p>
            <p>点击或拖拽 xlsx 文件到此处上传</p>
            <p style="color: #999; font-size: 12px">支持 .xlsx / .xls</p>
          </a-upload-dragger>

          <div style="margin-top: 16px">
            <h4>操作说明：</h4>
            <ol style="padding-left: 20px; color: #666; font-size: 13px">
              <li>点击"扫描目录"同步录音文件结构</li>
              <li>上传 B 超结果 xlsx，按病历号自动匹配</li>
              <li>匹配成功后即可进入"单条测试"</li>
            </ol>
          </div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { DataNode } from 'ant-design-vue/es/tree'
import {
  FolderOutlined, CustomerServiceOutlined, CloudUploadOutlined, ScanOutlined,
} from '@ant-design/icons-vue'
import { useAppStore } from '@/stores'
import { resultApi } from '@/api/client'

const store = useAppStore()
const { audioTree, dataStatus, loadingTree } = store

const uploading = ref(false)

onMounted(() => {
  store.fetchAudioTree()
  store.fetchDataStatus()
})

async function handleUpload(file: File) {
  uploading.value = true
  try {
    const res: any = await resultApi.upload(file)
    message.success(`导入成功，共 ${res.imported} 条`)
    await store.fetchAudioTree()
    await store.fetchDataStatus()
  } finally {
    uploading.value = false
  }
  return false
}

async function handleScan() {
  message.info('正在扫描录音目录...')
  await store.scanRecordings()
  message.success('扫描完成')
}

interface TreeDataNode extends DataNode {
  children?: TreeDataNode[]
}

const treeData = computed<TreeDataNode[]>(() => {
  return audioTree.value.map((folder) => ({
    title: `${folder.date} (${folder.patient_count} 例)`,
    key: `date-${folder.id}`,
    children: folder.patients.map((patient) => ({
      title: `${patient.record_id} - ${patient.segs.length} 段 ${patient.has_result ? '✅' : '⚠️'}`,
      key: `patient-${patient.id}`,
      isLeaf: true,
    })),
  }))
})
</script>
