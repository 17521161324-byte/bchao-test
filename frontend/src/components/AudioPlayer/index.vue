<template>
  <div class="audio-player">
    <audio
      ref="audioRef"
      @play="isPlaying = true"
      @pause="isPlaying = false"
      @ended="onEnded"
      @timeupdate="onTimeUpdate"
      style="display: none"
    />

    <div v-if="segs.length === 0" style="padding: 16px; color: #999">无音频</div>

    <template v-else>
      <div class="info">
        <a-space>
          <a-tag color="blue">第 {{ activeIndex + 1 }} / {{ segs.length }} 段</a-tag>
          <span style="color: #666; font-size: 12px">{{ currentSeg?.filename }}</span>
        </a-space>
        <a-tag v-if="highlightSegIndex !== undefined && highlightSegIndex !== activeIndex" color="processing">
          正在转写第 {{ highlightSegIndex + 1 }} 段...
        </a-tag>
      </div>

      <a-slider v-model:value="progress" :tip-formatter="null" />

      <div class="controls">
        <a-space size="large">
          <a-button :disabled="activeIndex === 0" @click="goToSeg(activeIndex - 1)">
            <StepBackwardOutlined />
          </a-button>
          <a-button type="primary" shape="circle" size="large" @click="togglePlay">
            <PauseOutlined v-if="isPlaying" />
            <CaretRightOutlined v-else />
          </a-button>
          <a-button :disabled="activeIndex === segs.length - 1" @click="goToSeg(activeIndex + 1)">
            <StepForwardOutlined />
          </a-button>
        </a-space>
      </div>

      <div class="seg-list">
        <a-button
          v-for="(seg, idx) in segs"
          :key="seg.id"
          size="small"
          :type="idx === activeIndex ? 'primary' : (idx === highlightSegIndex ? 'dashed' : 'default')"
          @click="goToSeg(idx)"
        >
          {{ idx + 1 }}
        </a-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import type { AudioSeg } from '@/types'
import {
  CaretRightOutlined, PauseOutlined,
  StepBackwardOutlined, StepForwardOutlined,
} from '@ant-design/icons-vue'

const props = defineProps<{
  segs: AudioSeg[]
  currentSegIndex?: number
  highlightSegIndex?: number
}>()

const emit = defineEmits<{
  (e: 'segChange', index: number): void
}>()

const audioRef = ref<HTMLAudioElement | null>(null)
const activeIndex = ref(0)
const isPlaying = ref(false)
const progress = ref(0)
let userControlled = false

const currentSeg = computed(() => props.segs[activeIndex.value])

watch(() => props.currentSegIndex, (val) => {
  if (val !== undefined && !userControlled) {
    activeIndex.value = val
    userControlled = true
    loadAndPlay()
  }
})

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

function goToSeg(index: number) {
  if (index < 0 || index >= props.segs.length) return
  activeIndex.value = index
  emit('segChange', index)
  isPlaying.value = true
}

function onEnded() {
  if (activeIndex.value < props.segs.length - 1) {
    goToSeg(activeIndex.value + 1)
  } else {
    isPlaying.value = false
  }
}

function onTimeUpdate(e: Event) {
  const audio = e.currentTarget as HTMLAudioElement
  if (audio.duration) {
    progress.value = (audio.currentTime / audio.duration) * 100
  }
}

onMounted(() => {
  if (props.segs.length > 0) loadAndPlay()
})
</script>

<style scoped>
.audio-player { padding: 16px; background: #fafafa; border-radius: 8px; border: 1px solid #f0f0f0; }
.info { margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
.controls { text-align: center; margin-top: 8px; }
.seg-list { margin-top: 12px; display: flex; gap: 4px; flex-wrap: wrap; }
</style>
