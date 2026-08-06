<template>
  <div class="page-container">
    <div class="page-header"><h2>CLI 执行器</h2></div>

    <a-card>
      <a-space direction="vertical" style="width: 100%" :size="12">
        <!-- 命令输入区 -->
        <div>
          <span style="color: #666">工作目录：</span>
          <a-input
            v-model:value="cwd"
            style="width: 100%; margin-top: 4px"
            placeholder="留空则使用项目默认目录"
            allow-clear
          />
        </div>

        <div>
          <span style="color: #666">执行命令：</span>
          <a-input-group compact style="margin-top: 4px">
            <a-input
              v-model:value="command"
              style="width: calc(100% - 110px)"
              placeholder="输入要执行的命令..."
              :disabled="isRunning"
              @pressEnter="handleExecute"
            />
            <a-button
              type="primary"
              :disabled="!command.trim() || isRunning"
              @click="handleExecute"
              style="width: 110px"
            >
              <PlayCircleOutlined v-if="!isRunning" />
              <LoadingOutlined v-else />
              {{ isRunning ? '运行中...' : '执行' }}
            </a-button>
          </a-input-group>
        </div>

        <!-- 快捷命令 -->
        <div>
          <span style="color: #666">快捷命令：</span>
          <div style="margin-top: 4px">
            <a-tag
              v-for="cmd in quickCommands"
              :key="cmd"
              color="blue"
              style="cursor: pointer; margin-bottom: 4px"
              @click="command = cmd"
            >
              {{ cmd }}
            </a-tag>
          </div>
        </div>

        <!-- 操作按钮 -->
        <a-space>
          <a-button danger :disabled="!isRunning" @click="handleStop">
            <StopOutlined />
            停止
          </a-button>
          <a-button @click="handleClear">
            <ClearOutlined />
            清空日志
          </a-button>
        </a-space>

        <!-- 状态栏 -->
        <div v-if="status" class="status-bar">
          <span :class="['status-text', statusClass]">
            <Badge :status="statusDot" />
            {{ statusText }}
          </span>
          <span v-if="exitCode !== null" style="margin-left: 12px; color: #666">
            退出码：{{ exitCode }}
          </span>
          <span v-if="duration" style="margin-left: 12px; color: #666">
            耗时：{{ duration }}
          </span>
        </div>

        <!-- 终端日志区 -->
        <div ref="terminalRef" class="terminal">
          <div
            v-for="(line, index) in logs"
            :key="index"
            :class="['log-line', line.type === 'stderr' ? 'log-error' : 'log-normal']"
          >
            <span class="log-time">{{ formatTime(line.timestamp) }}</span>
            <span class="log-content">{{ line.content }}</span>
          </div>
          <div v-if="logs.length === 0" class="terminal-empty">
            暂无执行日志...
          </div>
        </div>
      </a-space>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlayCircleOutlined,
  LoadingOutlined,
  StopOutlined,
  ClearOutlined,
} from '@ant-design/icons-vue'

const cwd = ref('')
const command = ref('')
const logs = ref<any[]>([])
const isRunning = ref(false)
const status = ref<'running' | 'completed' | 'failed' | 'stopped' | null>(null)
const exitCode = ref<number | null>(null)
const terminalRef = ref<HTMLElement | null>(null)
const startTime = ref<Date | null>(null)

// 快捷命令
const quickCommands = [
  'ls -la',
  'pwd',
  'git status',
  'git log --oneline -10',
  'npm list',
]

// 计算属性
const statusDot = computed(() => {
  switch (status.value) {
    case 'running': return 'processing'
    case 'completed': return 'success'
    case 'failed': return 'error'
    case 'stopped': return 'warning'
    default: return 'default'
  }
})

const statusText = computed(() => {
  switch (status.value) {
    case 'running': return '运行中...'
    case 'completed': return '已完成'
    case 'failed': return '执行失败'
    case 'stopped': return '已手动停止'
    default: return '就绪'
  }
})

const statusClass = computed(() => {
  switch (status.value) {
    case 'running': return 'text-running'
    case 'completed': return 'text-success'
    case 'failed': return 'text-error'
    case 'stopped': return 'text-warning'
    default: return ''
  }
})

const duration = computed(() => {
  if (!startTime.value || !isRunning.value) return null
  const ms = Date.now() - startTime.value.getTime()
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
})

// 格式化时间
function formatTime(timestamp: string): string {
  if (!timestamp) return ''
  try {
    const d = new Date(timestamp)
    return d.toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ''
  }
}

// 滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (terminalRef.value) {
      terminalRef.value.scrollTop = terminalRef.value.scrollHeight
    }
  })
}

// 执行命令
function handleExecute() {
  if (!command.value.trim()) {
    message.warning('请输入要执行的命令')
    return
  }

  logs.value = []
  isRunning.value = true
  status.value = 'running'
  exitCode.value = null
  startTime.value = new Date()

  const params = new URLSearchParams()
  params.set('command', command.value.trim())
  if (cwd.value.trim()) {
    params.set('cwd', cwd.value.trim())
  }

  const es = new EventSource(`${import.meta.env.VITE_API_BASE || '/api'}/cli/execute/stream?${params.toString()}`)

  es.addEventListener('log', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      logs.value.push(data)
      scrollToBottom()
    } catch { /* ignore */ }
  })

  es.addEventListener('status', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      if (data.status === 'running') {
        status.value = 'running'
      } else {
        isRunning.value = false
        status.value = data.status
        exitCode.value = data.exit_code ?? null
        if (data.error) {
          logs.value.push({ type: 'stderr', content: `\n[错误] ${data.error}`, timestamp: new Date().toISOString() })
        }
        message.info(data.status === 'completed' ? '执行完成' : '执行结束')
      }
      es.close()
    } catch { /* ignore */ }
  })

  es.onerror = () => {
    es.close()
    isRunning.value = false
    if (status.value === 'running') {
      status.value = 'failed'
      message.error('连接中断')
    }
  }
}

// 停止执行
function handleStop() {
  // 简化实现：刷新页面或提示用户
  message.warning('当前版本暂不支持中途停止，请等待执行完成')
}

// 清空日志
function handleClear() {
  logs.value = []
  status.value = null
  exitCode.value = null
  startTime.value = null
}
</script>

<style scoped>
.status-bar {
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 13px;
}

.status-text {
  font-weight: 500;
}

.text-running { color: #1890ff; }
.text-success { color: #52c41a; }
.text-error { color: #ff4d4f; }
.text-warning { color: #faad14; }

.terminal {
  height: 400px;
  background: #1e1e1e;
  border-radius: 4px;
  padding: 12px;
  overflow-y: auto;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.terminal-empty {
  color: #666;
  text-align: center;
  padding-top: 180px;
}

.log-line {
  white-space: pre-wrap;
  word-break: break-all;
}

.log-time {
  color: #888;
  margin-right: 8px;
  user-select: none;
}

.log-content {
  color: #d4d4d4;
}

.log-error .log-content {
  color: #f48771;
}
</style>
