<template>
  <div class="audio-player">
    <audio
      ref="audioRef"
      @play="isPlaying = true"
      @pause="onPause"
      @ended="onEnded"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
      @canplay="onCanPlay"
      style="display: none"
    />

    <div v-if="segs.length === 0" style="padding: 16px; color: #999">无音频</div>

    <template v-else>
      <div class="waveform-toolbar">
        <span>录音分段：{{ segs.length }} 段</span>
        <a-space size="small">
          <span v-if="waveformLoading">完整波形加载中 {{ waveformLoadedCount }} / {{ segs.length }}</span>
          <span v-else-if="waveformError" class="waveform-error">{{ waveformError }}</span>
          <a-button v-if="!waveformVisible" size="small" @click="loadCombinedWaveform" :loading="waveformLoading">
            加载完整波形
          </a-button>
          <a-button v-else size="small" @click="hideWaveform">隐藏波形</a-button>
        </a-space>
      </div>

      <div
        v-show="waveformVisible"
        ref="waveformContainerRef"
        class="waveform-container"
        :class="{ disabled: waveformLoading || !waveformPeaks.length }"
        @click="onWaveformClick"
      >
        <canvas ref="waveformCanvasRef" class="waveform-canvas" />
      </div>

      <div class="controls">
        <a-button type="primary" shape="circle" size="large" @click="togglePlay" :disabled="!currentSeg">
          <PauseOutlined v-if="isPlaying" />
          <CaretRightOutlined v-else />
        </a-button>
        <div class="progress-area">
          <span class="time-text">
            {{ formatTime(currentTime) }} / {{ formatTime(totalDuration) }}
            <span class="seg-text">第 {{ activeIndex + 1 }} / {{ segs.length }} 段</span>
          </span>
          <a-slider
            v-model:value="seekValue"
            :min="0"
            :max="100"
            :step="0.1"
            :tip-formatter="formatSeekTip"
            @change="onSeek"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import type { AudioSeg } from '@/types'
import { CaretRightOutlined, PauseOutlined } from '@ant-design/icons-vue'

const props = defineProps<{
  segs: AudioSeg[]
}>()

const audioRef = ref<HTMLAudioElement | null>(null)
const activeIndex = ref(0)
const isPlaying = ref(false)
const currentTime = ref(0)
const totalDuration = ref(0)
const seekValue = ref(0)
const waveformContainerRef = ref<HTMLDivElement | null>(null)
const waveformCanvasRef = ref<HTMLCanvasElement | null>(null)
const waveformPeaks = ref<number[]>([])
const waveformVisible = ref(false)
const waveformLoading = ref(false)
const waveformError = ref('')
const waveformLoadedCount = ref(0)

let isSeeking = false
let pendingAutoPlay = false
let waveformAbortController: AbortController | null = null
let resizeObserver: ResizeObserver | null = null

const currentSeg = computed(() => props.segs[activeIndex.value])
const currentAudioUrl = computed(() => getAudioUrl(currentSeg.value))

watch(() => props.segs, (newSegs) => {
  totalDuration.value = newSegs.reduce((sum, s) => sum + getSegDuration(s), 0)
  activeIndex.value = 0
  currentTime.value = 0
  seekValue.value = 0
  resetWaveform()
  loadCurrentSeg(false)
}, { immediate: true })

watch(currentSeg, () => {
  loadCurrentSeg(pendingAutoPlay)
})

function getAudioUrl(seg?: AudioSeg): string {
  if (!seg) return ''
  // 生产环境仍可能运行旧后端，旧后端只支持 ?path= 方式；
  // 优先使用 file_path 可保证新旧后端都能播放，缺失时再回退到 seg_id。
  if (seg.file_path) return `/api/audio/file?path=${encodeURIComponent(seg.file_path)}`
  if (seg.id) return `/api/audio/file/${seg.id}`
  return ''
}

function getSegDuration(seg?: AudioSeg): number {
  return seg && seg.duration > 0 ? seg.duration : 25
}

function getPrevDuration(index = activeIndex.value): number {
  return props.segs.slice(0, index).reduce((sum, seg) => sum + getSegDuration(seg), 0)
}

function loadCurrentSeg(autoPlay: boolean) {
  if (!audioRef.value || !currentSeg.value || !currentAudioUrl.value) return
  pendingAutoPlay = autoPlay
  audioRef.value.src = currentAudioUrl.value
  audioRef.value.load()
}

function onCanPlay() {
  if (!audioRef.value || !pendingAutoPlay) return
  pendingAutoPlay = false
  audioRef.value.play().catch(() => {
    isPlaying.value = false
  })
}

function togglePlay() {
  if (!audioRef.value || !currentSeg.value) return
  if (isPlaying.value) {
    pendingAutoPlay = false
    audioRef.value.pause()
  } else {
    audioRef.value.play().catch(() => {
      isPlaying.value = false
    })
  }
}

function onPause() {
  if (!pendingAutoPlay) isPlaying.value = false
}

function onEnded() {
  if (activeIndex.value < props.segs.length - 1) {
    pendingAutoPlay = true
    activeIndex.value += 1
  } else {
    pendingAutoPlay = false
    isPlaying.value = false
    currentTime.value = totalDuration.value
    seekValue.value = 100
    drawWaveform(1)
  }
}

function onTimeUpdate(e: Event) {
  if (isSeeking) return
  const audio = e.currentTarget as HTMLAudioElement
  if (audio.duration) {
    const overall = getPrevDuration() + audio.currentTime
    const total = totalDuration.value || overall
    seekValue.value = Math.min((overall / total) * 100, 100)
    currentTime.value = overall
    drawWaveform(total ? overall / total : 0)
  }
}

function onLoadedMetadata(e: Event) {
  const audio = e.currentTarget as HTMLAudioElement
  if (audio.duration && audio.duration > 0) {
    const durations = props.segs.map((seg, index) => index === activeIndex.value ? audio.duration : getSegDuration(seg))
    totalDuration.value = durations.reduce((sum, duration) => sum + duration, 0)
  }
}

function onSeek(value: number) {
  seekToOverallTime(((value || 0) / 100) * totalDuration.value, isPlaying.value)
}

function seekToOverallTime(targetTime: number, shouldPlayAfterSeek: boolean) {
  isSeeking = true
  const safeTarget = Math.max(0, Math.min(targetTime, totalDuration.value || 0))

  let accumulated = 0
  for (let i = 0; i < props.segs.length; i++) {
    const segDuration = getSegDuration(props.segs[i])
    if (accumulated + segDuration >= safeTarget || i === props.segs.length - 1) {
      const segOffset = Math.max(0, Math.min(safeTarget - accumulated, segDuration))
      const applyOffset = () => {
        if (audioRef.value) {
          audioRef.value.currentTime = segOffset
          if (shouldPlayAfterSeek) {
            pendingAutoPlay = false
            audioRef.value.play().catch(() => {
              isPlaying.value = false
            })
          }
        }
        isSeeking = false
      }

      if (activeIndex.value !== i) {
        pendingAutoPlay = shouldPlayAfterSeek
        activeIndex.value = i
        setTimeout(applyOffset, 180)
      } else {
        applyOffset()
      }

      currentTime.value = safeTarget
      seekValue.value = totalDuration.value ? Math.min((safeTarget / totalDuration.value) * 100, 100) : 0
      drawWaveform(totalDuration.value ? safeTarget / totalDuration.value : 0)
      return
    }
    accumulated += segDuration
  }

  isSeeking = false
}

async function loadCombinedWaveform() {
  if (waveformLoading.value) return
  waveformVisible.value = true
  waveformError.value = ''
  waveformLoading.value = true
  waveformLoadedCount.value = 0
  waveformPeaks.value = []

  waveformAbortController?.abort()
  const abortController = new AbortController()
  waveformAbortController = abortController

  try {
    await nextTick()
    const peaksBySeg: number[][] = []
    let failedCount = 0
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
    if (!AudioContextClass) throw new Error('浏览器不支持音频波形解析')

    for (const seg of props.segs) {
      if (abortController.signal.aborted) return
      try {
        const peaks = await loadSegPeaks(seg, AudioContextClass, abortController.signal)
        peaksBySeg.push(peaks)
      } catch (error: any) {
        if (error?.name === 'AbortError') return
        failedCount += 1
        peaksBySeg.push(buildSilentPeaks(seg))
      } finally {
        waveformLoadedCount.value += 1
      }
    }

    waveformPeaks.value = normalizePeaks(peaksBySeg.flat())
    waveformLoading.value = false
    waveformError.value = failedCount ? `${failedCount} 段波形解析失败，已用空白段占位` : ''
    drawWaveform(totalDuration.value ? currentTime.value / totalDuration.value : 0)
  } catch (error: any) {
    if (error?.name === 'AbortError') return
    waveformLoading.value = false
    waveformError.value = '完整波形加载失败'
    drawWaveform(0)
  }
}

async function loadSegPeaks(seg: AudioSeg, AudioContextClass: typeof AudioContext, signal: AbortSignal): Promise<number[]> {
  const response = await fetch(getAudioUrl(seg), { signal })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const arrayBuffer = await response.arrayBuffer()
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError')

  const audioContext = new AudioContextClass()
  try {
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0))
    return buildPeaks(audioBuffer, getSegDuration(seg))
  } finally {
    await audioContext.close()
  }
}

function buildPeaks(audioBuffer: AudioBuffer, segDuration: number): number[] {
  const peaksPerSecond = 24
  const peakCount = Math.max(40, Math.floor(segDuration * peaksPerSecond))
  const channelData = audioBuffer.getChannelData(0)
  const samplesPerPeak = Math.max(1, Math.floor(channelData.length / peakCount))
  const peaks: number[] = []

  for (let i = 0; i < peakCount; i++) {
    const start = i * samplesPerPeak
    const end = Math.min(start + samplesPerPeak, channelData.length)
    let peak = 0
    for (let j = start; j < end; j++) {
      peak = Math.max(peak, Math.abs(channelData[j]))
    }
    peaks.push(peak)
  }

  return peaks
}

function buildSilentPeaks(seg: AudioSeg): number[] {
  return Array.from({ length: Math.max(40, Math.floor(getSegDuration(seg) * 24)) }, () => 0)
}

function normalizePeaks(peaks: number[]): number[] {
  const maxPeak = peaks.reduce((max, peak) => Math.max(max, peak), 0)
  return maxPeak > 0 ? peaks.map((peak) => peak / maxPeak) : peaks
}

function hideWaveform() {
  waveformVisible.value = false
}

function resetWaveform() {
  waveformAbortController?.abort()
  waveformAbortController = null
  waveformVisible.value = false
  waveformLoading.value = false
  waveformError.value = ''
  waveformLoadedCount.value = 0
  waveformPeaks.value = []
}

function drawWaveform(progress = 0) {
  if (!waveformVisible.value) return
  const canvas = waveformCanvasRef.value
  const container = waveformContainerRef.value
  if (!canvas || !container) return

  const rect = container.getBoundingClientRect()
  const width = Math.max(1, Math.floor(rect.width))
  const height = 96
  const pixelRatio = window.devicePixelRatio || 1
  canvas.width = width * pixelRatio
  canvas.height = height * pixelRatio
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
  ctx.clearRect(0, 0, width, height)

  const peaks = waveformPeaks.value
  if (!peaks.length) {
    drawWaveformPlaceholder(ctx, width, height)
    return
  }

  const centerY = height / 2
  const clampedProgress = Math.max(0, Math.min(progress, 1))
  const progressX = width * clampedProgress
  const barWidth = 2
  const gap = 1
  const step = barWidth + gap
  const visibleBars = Math.floor(width / step)
  const sampleStep = Math.max(1, Math.floor(peaks.length / visibleBars))

  for (let i = 0; i < visibleBars; i++) {
    const peak = peaks[Math.min(peaks.length - 1, i * sampleStep)] || 0
    const barHeight = Math.max(3, peak * (height - 20))
    const x = i * step
    const y = centerY - barHeight / 2
    ctx.fillStyle = x <= progressX ? '#1677ff' : '#d9d9d9'
    roundRect(ctx, x, y, barWidth, barHeight, 1)
    ctx.fill()
  }

  drawSegmentBoundaries(ctx, width, height)

  ctx.strokeStyle = '#ff4d4f'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(progressX, 8)
  ctx.lineTo(progressX, height - 8)
  ctx.stroke()
}

function drawSegmentBoundaries(ctx: CanvasRenderingContext2D, width: number, height: number) {
  if (props.segs.length <= 1 || !totalDuration.value) return
  ctx.strokeStyle = 'rgba(0, 0, 0, 0.12)'
  ctx.lineWidth = 1
  let accumulated = 0
  for (let i = 0; i < props.segs.length - 1; i++) {
    accumulated += getSegDuration(props.segs[i])
    const x = (accumulated / totalDuration.value) * width
    ctx.beginPath()
    ctx.moveTo(x, 12)
    ctx.lineTo(x, height - 12)
    ctx.stroke()
  }
}

function drawWaveformPlaceholder(ctx: CanvasRenderingContext2D, width: number, height: number) {
  const centerY = height / 2
  ctx.strokeStyle = '#e8e8e8'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(0, centerY)
  ctx.lineTo(width, centerY)
  ctx.stroke()
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.lineTo(x + width - radius, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius)
  ctx.lineTo(x + width, y + height - radius)
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
  ctx.lineTo(x + radius, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius)
  ctx.lineTo(x, y + radius)
  ctx.quadraticCurveTo(x, y, x + radius, y)
  ctx.closePath()
}

function onWaveformClick(event: MouseEvent) {
  if (!waveformPeaks.value.length || waveformLoading.value) return
  const rect = waveformContainerRef.value?.getBoundingClientRect()
  if (!rect || !totalDuration.value) return
  const ratio = Math.max(0, Math.min((event.clientX - rect.left) / rect.width, 1))
  seekToOverallTime(ratio * totalDuration.value, isPlaying.value)
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSeekTip(value?: number): string {
  const percent = typeof value === 'number' ? value : 0
  return formatTime((percent / 100) * totalDuration.value)
}

onMounted(() => {
  if (props.segs.length > 0) loadCurrentSeg(false)
  if (waveformContainerRef.value && 'ResizeObserver' in window) {
    resizeObserver = new ResizeObserver(() => {
      drawWaveform(totalDuration.value ? currentTime.value / totalDuration.value : 0)
    })
    resizeObserver.observe(waveformContainerRef.value)
  }
})

onBeforeUnmount(() => {
  waveformAbortController?.abort()
  resizeObserver?.disconnect()
})
</script>

<style scoped>
.audio-player { padding: 12px; background: #fafafa; border-radius: 8px; border: 1px solid #f0f0f0; }
.waveform-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; color: #666; font-size: 12px; }
.waveform-error { color: #ff4d4f; }
.waveform-container { height: 96px; margin-bottom: 12px; padding: 0 4px; background: #fff; border: 1px solid #f0f0f0; border-radius: 8px; cursor: pointer; overflow: hidden; }
.waveform-container.disabled { cursor: default; }
.waveform-canvas { display: block; width: 100%; height: 96px; }
.controls { display: flex; align-items: center; gap: 16px; }
.progress-area { flex: 1; }
.time-text { font-size: 12px; color: #666; margin-bottom: 4px; display: block; }
.seg-text { margin-left: 8px; color: #999; }
</style>
