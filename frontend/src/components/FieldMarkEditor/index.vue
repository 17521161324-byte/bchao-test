<template>
  <div class="field-mark-editor">
    <!-- 当前标记展示 -->
    <template v-if="currentMark">
      <a-alert :type="currentMark.mark_type === 'exclude' ? 'warning' : 'error'" show-icon style="margin-bottom: 12px">
        <template #message>
          <a-space direction="vertical" style="width: 100%">
            <div>
              <strong>{{ currentMark.mark_type === 'exclude' ? '排除统计' : '异常说明，计入不匹配' }}</strong>
              <a-button type="link" size="small" danger @click="handleClear" :loading="clearing">清除标记</a-button>
            </div>
            <div v-if="currentMark.reason">原因：{{ currentMark.reason }}</div>
            <div v-if="currentMark.note">备注：{{ currentMark.note }}</div>
            <div style="color: #999; font-size: 11px">记录时间：{{ formatMarkTime(currentMark.updated_at || currentMark.created_at) }}</div>
          </a-space>
        </template>
      </a-alert>
    </template>
    <a-empty v-else description="暂无人工标记" style="margin-bottom: 12px" />

    <!-- 编辑表单 -->
    <a-form layout="vertical" size="small">
      <a-form-item label="标记类型">
        <a-select v-model:value="form.markType">
          <a-select-option value="exclude">排除统计</a-select-option>
          <a-select-option value="mismatch_note">异常说明，计入不匹配</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="原因">
        <a-select v-model:value="form.reason" placeholder="选择原因" allow-clear>
          <a-select-option v-for="r in reasonOptions" :key="r" :value="r">{{ r }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="备注">
        <a-textarea v-model:value="form.note" :rows="2" placeholder="可选：补充说明" />
      </a-form-item>
      <a-form-item>
        <a-button type="primary" @click="handleSave" :loading="saving">保存标记</a-button>
      </a-form-item>
    </a-form>
  </div>
</template>

<script lang="ts">
import { defineComponent, reactive, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { audioApi } from '@/api/client'

const EXCLUDE_REASONS = ['收音设备问题', '录音缺失/不完整', '真实 B 超数据疑似错误', '非本次评估范围', '暂时排查', '其他']
const MISMATCH_REASONS = ['ASR 漏识别', 'ASR 错识别', 'LLM 未提取', 'LLM 提取错误', '左右侧混淆', '数量统计错误', '尺寸解析错误', '格式不规范', '其他']

export default defineComponent({
  name: 'FieldMarkEditor',
  props: {
    record: { type: Object, required: true },
    groupKey: { type: String, required: true },
  },
  emits: ['saved', 'cleared'],
  setup(props, { emit }) {
    const saving = ref(false)
    const clearing = ref(false)

    const currentMark = computed(() => {
      const marks = props.record?.field_review_marks || []
      // 优先精确匹配 field_key，其次 field_group
      let mark = marks.find((m: any) => m.field_key === props.groupKey)
      if (!mark) mark = marks.find((m: any) => m.field_group === props.groupKey)
      return mark || null
    })

    const reasonOptions = computed(() =>
      form.markType === 'exclude' ? EXCLUDE_REASONS : MISMATCH_REASONS
    )

    const form = reactive({
      markType: currentMark.value?.mark_type || 'exclude',
      reason: currentMark.value?.reason || '',
      note: currentMark.value?.note || '',
    })

    watch(currentMark, (m) => {
      if (m) {
        form.markType = m.mark_type
        form.reason = m.reason || ''
        form.note = m.note || ''
      }
    })

    function formatMarkTime(t: string | null): string {
      if (!t) return '-'
      try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
    }

    async function handleSave() {
      saving.value = true
      try {
        const res: any = await audioApi.saveFieldReviewMark(props.record.id, {
          field_group: props.groupKey,
          field_key: null,
          mark_type: form.markType,
          reason: form.reason || null,
          note: form.note || null,
        })
        message.success('标记已保存')
        emit('saved', res)
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '保存失败')
      } finally {
        saving.value = false
      }
    }

    async function handleClear() {
      clearing.value = true
      try {
        await audioApi.clearFieldReviewMark(props.record.id, props.groupKey)
        message.success('标记已清除')
        emit('cleared')
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '清除失败')
      } finally {
        clearing.value = false
      }
    }

    return {
      currentMark, form, saving, clearing, reasonOptions,
      handleSave, handleClear, formatMarkTime,
    }
  },
})
</script>

<style scoped>
.field-mark-editor { padding: 8px 0; }
</style>
