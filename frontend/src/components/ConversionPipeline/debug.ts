/**
 * ConversionDebug 页面共享类型与纯函数（V14 布局）。
 *
 * 职责：把后端执行响应的 steps 快照（rule_hits / conversions / warnings）
 * 与规则配置（builtin-rules + 版本词库 + 版本运行时规则）合并成 V14 诊断视图所需的数据。
 * called/hit 一律以后端返回为准：后端未提供 called 字段时显示 "-"，前端不自行推断。
 */
import type { PipelineStep } from '@/types/conversionPipeline'

/** 侧栏记录（真实历史 ASR：PatientAsrResult + 检查记录元信息） */
export interface SidebarRecord {
  id: number
  patient_id: number
  record_id: string
  date: string
  asr_model_name: string
  config_hash: string
  full_transcript: string
  status: 'pending' | 'review' | 'confirmed'
}

/** V14 五个业务步骤（technical 为后端技术步骤编码） */
export interface BusinessStepDef {
  code: string
  name: string
  technical: string[]
}

export const BUSINESS_STEPS: BusinessStepDef[] = [
  { code: 'MEDICAL_TERM', name: '医学名词标准化', technical: ['MEDICAL_TERM'] },
  { code: 'BASE_CLEANING', name: '清洗与中文数值预处理', technical: ['BASE_CLEANING'] },
  { code: 'NUMBER_NORMALIZE', name: '数字与尺寸转换', technical: ['NUMBER_NORMALIZE'] },
  { code: 'BUSINESS_SEGMENT', name: '业务片段定位', technical: ['BUSINESS_SEGMENT'] },
  {
    code: 'FIELD_VALIDATE',
    name: '字段解析、校验与分流',
    technical: ['FIELD_PARSE', 'RUNTIME_RULE', 'RISK_INTERCEPT'],
  },
]

export function businessStepByCode(code: string): BusinessStepDef | undefined {
  return BUSINESS_STEPS.find((item) => item.code === code)
}

export function businessStepForTech(stepCode: string): BusinessStepDef | undefined {
  return BUSINESS_STEPS.find((item) => item.technical.includes(stepCode))
}

/** 某业务步骤对应的技术步骤（按 step_order 升序，保证输入取第一步、输出取最后一步） */
export function techStepsOf(steps: PipelineStep[], businessCode: string): PipelineStep[] {
  const def = businessStepByCode(businessCode)
  if (!def) return []
  return (steps || [])
    .filter((step) => def.technical.includes(step.step_code))
    .sort((a, b) => Number(a.step_order || 0) - Number(b.step_order || 0))
}

/** 业务步骤是否已实际执行（任一技术步骤已生成且非 pending） */
export function stepExecuted(technicalSteps: PipelineStep[]): boolean {
  return technicalSteps.some((step) => step && step.status && step.status !== 'pending')
}

/** 步骤生效输出：人工修改优先，其次系统输出 */
export function effectiveOutput(step?: PipelineStep | null): string {
  return step?.effective_output_text || step?.manual_output_text || step?.output_text || ''
}

/** 业务步骤输入文本（取第一个技术步骤的输入） */
export function businessStepInput(technicalSteps: PipelineStep[]): string {
  return technicalSteps[0]?.input_text || ''
}

/** 业务步骤输出文本（取最后一个已执行技术步骤的生效输出） */
export function businessStepOutput(technicalSteps: PipelineStep[]): string {
  const executed = technicalSteps.filter((step) => step.status && step.status !== 'pending')
  const last = executed[executed.length - 1] || technicalSteps[technicalSteps.length - 1]
  return effectiveOutput(last)
}

/** 观察到的规则记录（来自执行快照：rule_hits + conversions，去重取先出现者） */
export interface ObservedRecord {
  rule_id: string
  rule_name: string
  raw: string
  converted: string
  action: string
  message: string
  /** 后端若提供 called 标记则使用，否则前端不推断（显示 "-"） */
  called?: boolean | number | string
  from: 'hit' | 'conv'
}

function str(value: any): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

export function collectObserved(technicalSteps: PipelineStep[]): ObservedRecord[] {
  const seen = new Map<string, ObservedRecord>()
  ;(technicalSteps || []).forEach((step) => {
    const items = [
      ...(step.rule_hits || []).map((item: any) => ({ ...item, _from: 'hit' as const })),
      ...(step.conversions || []).map((item: any) => ({ ...item, _from: 'conv' as const })),
    ]
    items.forEach((item: any) => {
      const id = str(item.rule_id || item.rule_code || '').trim()
      if (!id) return
      if (seen.has(id)) return
      seen.set(id, {
        rule_id: id,
        rule_name: str(item.rule_name || item.name || item.standard_text || '').trim(),
        raw: str(item.raw || item.raw_text || item.text || item.term || item.error_text || ''),
        converted: item.converted === null || item.converted === undefined ? '' : str(item.converted || item.normalized || item.standard || ''),
        action: str(item.action || '').toUpperCase(),
        message: str(item.message || item.notes || item.note || item.evidence || ''),
        called: item.called ?? item.called_count ?? item.rule_called,
        from: item._from,
      })
    })
  })
  return Array.from(seen.values())
}

/** 已配置规则（来自 builtin-rules + 版本词库 + 版本运行时规则） */
export interface ConfigRule {
  rule_id: string
  name: string
}

/** builtin 规则分组 → 业务步骤编码；词库→医学名词标准化；版本运行时规则→字段解析校验 */
export function configStepForRule(rule: any, group?: string): string | '' {
  const explicit = str(rule?.step_code || rule?.step || '').toUpperCase()
  if (explicit && businessStepForTech(explicit)) return businessStepForTech(explicit)!.code
  if (group === 'lexicon') return 'MEDICAL_TERM'
  if (group === 'runtime') return 'FIELD_VALIDATE'
  if (group === 'medical_term') return 'MEDICAL_TERM'
  if (group === 'number_normalize') return 'NUMBER_NORMALIZE'
  if (group === 'business_segment' || group === 'text_switch') return 'BUSINESS_SEGMENT'
  if (group === 'field_extract' || group === 'risk') return 'FIELD_VALIDATE'
  return ''
}

export interface DebugConfigGroups {
  builtin: Record<string, any[]>
  lexicon: any[]
  runtime: any[]
}

export function collectConfigured(config: DebugConfigGroups | null, businessCode: string): ConfigRule[] {
  if (!config) return []
  const seen = new Map<string, ConfigRule>()
  const push = (rule: any, group?: string) => {
    const id = str(rule?.rule_id || rule?.rule_code || rule?.code || '').trim()
    if (!id) return
    const step = configStepForRule(rule, group)
    if (step !== businessCode) return
    if (seen.has(id)) return
    seen.set(id, {
      rule_id: id,
      name: str(rule?.rule_name || rule?.name || rule?.notes || '').trim() || id,
    })
  }
  Object.entries(config.builtin || {}).forEach(([group, rules]) => {
    ;(Array.isArray(rules) ? rules : []).forEach((rule) => push(rule, group))
  })
  ;(config.lexicon || []).forEach((rule) => push(rule, 'lexicon'))
  ;(config.runtime || []).forEach((rule) => push(rule, 'runtime'))
  return Array.from(seen.values())
}

/** 规则诊断表行 */
export interface DiagnosisRow {
  key: string
  rule_id: string
  rule_name: string
  configured: 'yes' | 'no'
  called: 'yes' | 'no' | '-'
  hit: boolean
  /** yes=已配置 / no=未配置 / hit=命中 / miss=未命中 / missing=缺失 */
  status: 'yes' | 'no' | 'hit' | 'miss' | 'missing'
  hit_text: string
  output_change: string
  note: string
  fromConfig: boolean
  fromObserved: boolean
}

export interface DiagnosisStats {
  loaded: number
  called: number | '-'
  hit: number
  missing: number
}

/**
 * 合并已配置规则与观察记录：
 * - 已配置且命中 → 命中（蓝）
 * - 已配置但未命中 → 未命中（橙）
 * - 观察记录但配置缺失 → 缺失规则（红，已配置=否）
 */
export function buildDiagnosis(configured: ConfigRule[], observed: ObservedRecord[]): { rows: DiagnosisRow[]; stats: DiagnosisStats } {
  const rows: DiagnosisRow[] = []
  const observedById = new Map(observed.map((item) => [item.rule_id, item]))

  configured.forEach((rule) => {
    const hit = observedById.get(rule.rule_id)
    rows.push({
      key: `cfg-${rule.rule_id}`,
      rule_id: rule.rule_id,
      rule_name: rule.name,
      configured: 'yes',
      called: hit ? calledValue(hit.called) : '-',
      hit: !!hit,
      status: hit ? 'hit' : 'miss',
      hit_text: hit?.raw ? str(hit.raw) : '-',
      output_change: hit
        ? hit.converted !== '' && hit.converted !== hit.raw
          ? `${hit.raw} → ${hit.converted}`
          : '生成候选/上下文元数据'
        : '-',
      note: hit?.message || rule.name || '-',
      fromConfig: true,
      fromObserved: !!hit,
    })
  })

  observed.forEach((item) => {
    if (rows.some((row) => row.rule_id === item.rule_id)) return
    rows.push({
      key: `obs-${item.rule_id}`,
      rule_id: item.rule_id,
      rule_name: item.rule_name || item.rule_id,
      configured: 'no',
      called: calledValue(item.called),
      hit: true,
      status: 'missing',
      hit_text: item.raw || '-',
      output_change: item.converted !== '' && item.converted !== item.raw
        ? `${item.raw || '-'} → ${item.converted}`
        : '生成候选/上下文元数据',
      note: item.message || '执行产生的记录，未在当前规则配置中找到',
      fromConfig: false,
      fromObserved: true,
    })
  })

  rows.sort((a, b) => String(a.rule_id).localeCompare(String(b.rule_id), 'zh-CN'))

  const calledValues = rows.map((row) => row.called)
  const hasCalledData = calledValues.some((value) => value !== '-')
  const stats: DiagnosisStats = {
    loaded: rows.filter((row) => row.configured === 'yes').length,
    called: hasCalledData ? calledValues.filter((value) => value === 'yes').length : '-',
    hit: rows.filter((row) => row.status === 'hit' || row.status === 'missing').length,
    missing: rows.filter((row) => row.status === 'missing').length,
  }
  return { rows, stats }
}

function calledValue(value: ObservedRecord['called']): 'yes' | 'no' | '-' {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'number') return value > 0 ? 'yes' : 'no'
  const text = String(value).toLowerCase()
  if (['true', '1', 'yes', 'y', '是', '已调用'].includes(text)) return 'yes'
  if (['false', '0', 'no', 'n', '否'].includes(text)) return 'no'
  return '-'
}

/** 业务步骤候选数（需人工复核项）：非 AUTO 动作的记录 + 警示 */
export function candidateCount(observed: ObservedRecord[], warnings: string[]): number {
  const risky = observed.filter((item) => {
    const action = item.action || ''
    return action !== '' && action !== 'AUTO' && action !== 'NONE'
  }).length
  return risky + (warnings || []).length
}

/** 把 GET /result/exam/{id}/b-ultra 的真实 B 超结果映射为数据对比的 truth 字段（与后端 truth_fields 结构一致） */
export function mapTruthFromBUltra(obj: Record<string, any> | null | undefined): Record<string, any> {
  if (!obj) return {}
  const size = (length: any, width: any) => {
    if (length === null || length === undefined || width === null || width === undefined) return null
    const num = (value: any) => {
      const number = Number(value)
      return Number.isFinite(number) && number % 1 === 0 ? String(number) : String(value)
    }
    return `${num(length)}×${num(width)}`
  }
  return {
    endometrium_thickness: obj.endometrium_thickness ?? null,
    endometrium_type: obj.endometrium_type ?? null,
    right_ovary_size: size(obj.right_ovary_length, obj.right_ovary_width),
    right_follicles: obj.right_follicles || [],
    left_ovary_size: size(obj.left_ovary_length, obj.left_ovary_width),
    left_follicles: obj.left_follicles || [],
    remark: obj.remark ?? '',
  }
}

/** 行内语义标注段（第 1/3 步输出）：根据真实转换记录在输出文本中定位标注 */
export interface AnnotationSpan {
  type: 'plain' | 'anchor' | 'standard' | 'candidate' | 'aux' | 'risk'
  text: string
}

const ACTION_CLASS: Record<string, AnnotationSpan['type']> = {
  AUTO: 'standard',
  CANDIDATE: 'candidate',
  REVIEW: 'risk',
  BLOCK: 'risk',
}

/**
 * 把输出文本按观察记录标注为片段序列。
 * 在输出文本中查找 raw（或 converted），命中则标记对应语义类型；
 * 无 converted 的辅助记录（候选元数据）标记为辅助术语（青）。
 */
export function annotateOutput(outputText: string, observed: ObservedRecord[]): AnnotationSpan[] {
  const text = outputText || ''
  if (!text) return []
  const spans: Array<{ start: number; end: number; type: AnnotationSpan['type']; text: string }> = []
  const claimed: Array<[number, number]> = []

  observed.forEach((item) => {
    let type = ACTION_CLASS[item.action] || 'aux'
    const needle = item.converted || item.raw
    if (!needle || item.action === 'AUTO') type = 'standard'
    if (!needle) return
    let idx = text.indexOf(needle)
    while (idx >= 0) {
      const end = idx + needle.length
      const overlap = claimed.some(([s, e]) => idx < e && end > s)
      if (!overlap) break
      idx = text.indexOf(needle, idx + 1)
    }
    if (idx < 0) return
    claimed.push([idx, idx + needle.length])
    spans.push({ start: idx, end: idx + needle.length, type, text: needle })
  })

  spans.sort((a, b) => a.start - b.start)
  const segments: AnnotationSpan[] = []
  let cursor = 0
  spans.forEach((span) => {
    if (span.start > cursor) segments.push({ type: 'plain', text: text.slice(cursor, span.start) })
    if (span.start < cursor) {
      // 重叠（前段更长）：只取未占用部分
      const cutStart = cursor
      if (span.end > cutStart) segments.push({ type: span.type, text: text.slice(cutStart, span.end) })
    } else {
      segments.push({ type: span.type, text: span.text })
    }
    cursor = Math.max(cursor, span.end)
  })
  if (cursor < text.length) segments.push({ type: 'plain', text: text.slice(cursor) })
  return segments
}
