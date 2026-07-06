import { ref } from 'vue'

export interface FieldDef {
  key: string
  label: string
  unit?: string
}

export const FIELD_DEFS: FieldDef[] = [
  { key: 'endometrium_thickness', label: '内膜厚度', unit: 'mm' },
  { key: 'endometrium_type', label: '内膜类型' },
  { key: 'right_follicle_total', label: '右卵泡' },
  { key: 'left_follicle_total', label: '左卵泡' },
  { key: 'right_ovary_length', label: '右卵巢长', unit: 'mm' },
  { key: 'right_ovary_width', label: '右卵巢宽', unit: 'mm' },
  { key: 'left_ovary_length', label: '左卵巢长', unit: 'mm' },
  { key: 'left_ovary_width', label: '左卵巢宽', unit: 'mm' },
  { key: 'remark', label: '备注' },
]

export function useFieldCompare() {
  const fieldModal = ref<{ open: boolean; task: any | null; field: string }>({
    open: false,
    task: null,
    field: '',
  })

  function openFieldModal(task: any, field: string) {
    fieldModal.value = { open: true, task, field }
  }

  function closeFieldModal() {
    fieldModal.value = { open: false, task: null, field: '' }
  }

  function fieldEval(task: any, field: string) {
    return task?.evaluation?.fields?.[field] ?? null
  }

  function fieldMatch(task: any, field: string): boolean | null {
    const f = fieldEval(task, field)
    return f ? f.match : null
  }

  function truthValue(task: any, field: string): string {
    const f = fieldEval(task, field)
    return formatVal(f?.truth)
  }

  function identifiedValue(task: any, field: string): string {
    const f = fieldEval(task, field)
    return formatVal(f?.identified)
  }

  function formatVal(v: any): string {
    if (v === null || v === undefined) return '-'
    if (typeof v === 'object') return JSON.stringify(v, null, 2)
    return String(v)
  }

  return {
    fieldModal,
    FIELD_DEFS,
    openFieldModal,
    closeFieldModal,
    fieldEval,
    fieldMatch,
    truthValue,
    identifiedValue,
  }
}
