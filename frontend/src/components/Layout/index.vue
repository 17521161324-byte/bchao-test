<template>
  <a-layout class="layout">
    <a-layout-sider theme="dark" :width="220" style="position: sticky; top: 0; height: 100vh; overflow: auto">
      <div class="logo">
        <CloudServerOutlined /> B 超语音测试平台
      </div>
      <a-menu theme="dark" mode="inline" :selected-keys="[route.path]" @click="onMenuClick">
        <a-menu-item key="/data"><FolderOutlined />数据管理</a-menu-item>
        <a-menu-item key="/model"><SettingOutlined />模型配置</a-menu-item>
        <a-menu-item key="/test"><PlayCircleOutlined />单条测试</a-menu-item>
        <a-menu-item key="/eval"><AuditOutlined />结果评估</a-menu-item>
        <a-menu-item key="/history"><HistoryOutlined />测试历史</a-menu-item>
        <a-menu-item key="/experiments"><ExperimentOutlined />批量实验</a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="header">
        <a-space>
          <span style="color: #666">数据状态：</span>
          <template v-if="dataStatus">
            <a-badge color="green" /> {{ dataStatus.matched_count }} 已匹配
            <a-badge color="orange" style="margin-left: 8px" /> {{ dataStatus.audio_only_count }} 仅录音
          </template>
          <span v-else>加载中...</span>
        </a-space>
      </a-layout-header>

      <a-layout-content style="background: #f5f5f5; min-height: calc(100vh - 64px)">
        <router-view v-slot="{ Component }">
          <component :is="Component" :key="route.path" />
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores'
import {
  FolderOutlined, SettingOutlined, PlayCircleOutlined,
  AuditOutlined, HistoryOutlined, ExperimentOutlined, CloudServerOutlined,
} from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const dataStatus = computed(() => store.dataStatus)

function onMenuClick({ key }: { key: string }) {
  router.push(key)
}
</script>

<style scoped>
.layout { min-height: 100vh; }
.logo {
  height: 56px; display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 16px; font-weight: 600;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.header {
  background: #fff; padding: 0 24px; display: flex; align-items: center;
  justify-content: space-between; border-bottom: 1px solid #f0f0f0;
}
</style>
