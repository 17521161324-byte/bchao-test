<template>
  <div class="seg-list">
    <a-list :data-source="segs" size="small">
      <template #renderItem="{ item, index }">
        <a-list-item
          :style="{ cursor: 'pointer', background: index === currentSegIndex ? '#e6f4ff' : 'transparent', padding: '8px 12px' }"
          @click="emit('segClick', index)"
        >
          <a-list-item-meta>
            <template #avatar>
              <CheckCircleFilled v-if="getResult(item.seg_index)" style="color: #52c41a" />
              <LoadingOutlined v-else-if="index === currentSegIndex" style="color: #1677ff" />
              <WarningOutlined v-else style="color: #ccc" />
            </template>
            <template #title>
              <span style="font-size: 13px">
                <span style="font-weight: bold">第 {{ item.seg_index }} 段</span>
                <span style="margin-left: 8px; color: #666; font-size: 11px">{{ item.filename }}</span>
                <a-tag v-if="getResult(item.seg_index)" color="success" style="margin-left: 4px">已完成</a-tag>
                <a-tag v-else-if="index === currentSegIndex" color="processing" style="margin-left: 4px">转写中</a-tag>
                <a-tag v-else style="margin-left: 4px">未转写</a-tag>
              </span>
            </template>
            <template #description>
              <span v-if="getResult(item.seg_index)" style="font-size: 12px">{{ getResult(item.seg_index)!.text || '(空)' }}</span>
              <span v-else style="font-size: 12px; color: #999">等待转写...</span>
            </template>
          </a-list-item-meta>
        </a-list-item>
      </template>
    </a-list>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AudioSeg, ASRSegResult } from '@/types'
import { CheckCircleFilled, LoadingOutlined, WarningOutlined } from '@ant-design/icons-vue'

const props = defineProps<{
  segs: AudioSeg[]
  asrResults: ASRSegResult[]
  currentSegIndex?: number
}>()

const emit = defineEmits<{
  (e: 'segClick', index: number): void
}>()

const resultMap = computed(() => {
  const map = new Map<number, ASRSegResult>()
  props.asrResults.forEach((r) => map.set(r.seg_index, r))
  return map
})

function getResult(segIndex: number): ASRSegResult | undefined {
  return resultMap.value.get(segIndex)
}
</script>

<style scoped>
.seg-list { max-height: 400px; overflow-y: auto; }
</style>
