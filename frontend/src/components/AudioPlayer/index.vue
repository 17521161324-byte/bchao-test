<template>
  <div class="audio-player">
    <audio
      ref="audioRef"
      @play="isPlaying = true"
      @pause="isPlaying = false"
      @ended="onEnded"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
      style="display: none"
    />

    <div v-if="segs.length === 0" style="padding: 16px; color: #999">无音频</div>

    <template v-else>
      <div class="controls">
        <a-button type="primary" shape="circle" size="large" @click="togglePlay" :disabled="!currentSeg">
          <PauseOutlined v-if="isPlaying" />
          <CaretRightOutlined v-else />
        </a-button>
        <div class="progress-area">
          <span class="time-text">{{ formatTime(currentTime) }} / {{ formatTime(totalDuration) }}</span>
          <a-slider
            v-model:value="seekValue"
            :min="0"
            :max="100"
            :step="0.1"
            :tip-formatter="(v) => formatTime((v / 100) * totalDuration)"
            @change="onSeek"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
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
let isSeeking = false

const currentSeg = computed(() => props.segs[activeIndex.value])

watch(() => props.segs, (newSegs) => {
  if (newSegs.length > 0) {
    const estimated = newSegs.reduce((sum, s) => sum + (s.duration > 0 ? s.duration : 25), 0)
    totalDuration.value = estimated
  }
  activeIndex.value = 0
  loadAndPlay()
}, { immediate: true })

watch(currentSeg, () => {
  loadAndPlay()
})

function loadAndPlay() {
  if (!audioRef.value || !currentSeg.value) return
  audioRef.value.src = `/api/audio/file?path=${encodeURIComponent(currentSeg.value.file_path)}`
  audioRef.value.load()
  if (isPlaying.value) audioRef.value.play()
}

function togglePlay() {
  if (!audioRef.value) return
  if (isPlaying.value) audioRef.value.pause()
  else audioRef.value.play()
}

function onEnded() {
  if (activeIndex.value < props.segs.length - 1) {
    activeIndex.value++
  } else {
    isPlaying.value = false
  }
}

function onTimeUpdate(e: Event) {
  if (isSeeking) return
  const audio = e.currentTarget as HTMLAudioElement
  if (audio.duration) {
    const prevDuration = props.segs.slice(0, activeIndex.value).reduce((sum, s) => sum + (s.duration > 0 ? s.duration : 25), 0)
    const overall = prevDuration + audio.currentTime
    const total = totalDuration.value || overall
    seekValue.value = Math.min((overall / total) * 100, 100)
    currentTime.value = overall
  }
}

function onLoadedMetadata(e: Event) {
  const audio = e.currentTarget as HTMLAudioElement
  if (audio.duration && audio.duration > 0) {
    const prevDuration = props.segs.slice(0, activeIndex.value).reduce((sum, s) => sum + (s.duration > 0 ? s.duration : 25), 0)
    totalDuration.value = prevDuration + audio.duration +
      props.segs.slice(activeIndex.value + 1).reduce((sum, s) => sum + (s.duration > 0 ? s.duration : 25), 0)
  }
}

function onSeek(value: number) {
  isSeeking = true
  const total = totalDuration.value
  const targetTime = (value / 100) * total
  const wasPlaying = isPlaying.value

  let accumulated = 0
  for (let i = 0; i < props.segs.length; i++) {
    const segDuration = props.segs[i].duration > 0 ? props.segs[i].duration : 25
    if (accumulated + segDuration >= targetTime || i === props.segs.length - 1) {
      const segOffset = Math.max(0, Math.min(targetTime - accumulated, segDuration))
      if (activeIndex.value !== i) {
        activeIndex.value = i
        setTimeout(() => {
          if (audioRef.value) {
            audioRef.value.currentTime = segOffset
            if (wasPlaying) audioRef.value.play()
          }
          isSeeking = false
        }, 150)
      } else {
        if (audioRef.value) {
          audioRef.value.currentTime = segOffset
          if (wasPlaying) audioRef.value.play()
        }
        isSeeking = false
      }
      currentTime.value = targetTime
      return
    }
    accumulated += segDuration
  }
  isSeeking = false
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

onMounted(() => {
  if (props.segs.length > 0) loadAndPlay()
})
</script>

<style scoped>
.audio-player { padding: 12px; background: #fafafa; border-radius: 8px; border: 1px solid #f0f0f0; }
.controls { display: flex; align-items: center; gap: 16px; }
.progress-area { flex: 1; }
.time-text { font-size: 12px; color: #666; margin-bottom: 4px; display: block; }
</style>
