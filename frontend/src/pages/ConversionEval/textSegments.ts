/** 文本分段渲染工具：转化后 ASR 高亮 + 专家标准 ASR 标记 + 转化片段联动 */

export interface TextSegment {
  text: string
  type?: 'converted' | 'red' | 'orange' | 'green' | 'highlight'
  note?: string
  rawFragment?: string
  detailId?: number
}

/** 转化片段匹配结果 */
export interface FragmentMatchResult {
  detailId?: number
  rawFragment: string
  convertedFragment: string
  matchStatus: 'matched' | 'unmatched' | 'pending'
  matchNote: string
}

// ========== 文本归一化 ==========

const FILLER_WORDS = ['嗯', '啊', '哦', '噢', '呃', '额', '嗯嗯', '啊啊', '哦哦']

/**
 * 用于比较的轻量归一化（不影响原文展示）
 * - 中文数字转阿拉伯数字
 * - 去除无意义标点
 * - 弱化口语词
 */
export function normalizeForAsrCompare(text: string): string {
  let result = String(text || '')

  // 1. 中文数字小数归一化
  const chineseNumberMap: Record<string, string> = {
    '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
    '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
    '幺': '1',
  }

  // 匹配中文数字+点+中文数字 的小数模式
  result = result.replace(
    /([零一二三四五六七八九十幺]+)(点|。)([零一二三四五六七八九十幺]+)/g,
    (_, intPart, dot, decPart) => {
      let intNum = ''
      for (const ch of intPart) {
        intNum += chineseNumberMap[ch] || ch
      }
      let decNum = ''
      for (const ch of decPart) {
        decNum += chineseNumberMap[ch] || ch
      }
      return `${intNum}.${decNum}`
    }
  )

  // 2. 去除无意义标点和空白
  result = result.replace(/[，。、？！\s\n\r\t]/g, '')

  // 3. 弱化常见口语词
  for (const word of FILLER_WORDS) {
    result = result.split(word).join('')
  }

  return result.toLowerCase()
}

// ========== 转化片段匹配判断 ==========

/**
 * 判断单个转化片段是否与专家标准 ASR 匹配
 */
export function judgeFragmentMatch(
  detail: { id?: number; raw_fragment?: string; converted_fragment?: string },
  referenceText: string
): FragmentMatchResult {
  const raw = (detail.raw_fragment || '').trim()
  const converted = (detail.converted_fragment || '').trim()
  const normalizedRef = normalizeForAsrCompare(referenceText)

  // 1. 如果 converted_fragment 在专家标准中可以找到，匹配
  if (converted) {
    const normalizedConverted = normalizeForAsrCompare(converted)
    if (normalizedRef.includes(normalizedConverted)) {
      return {
        detailId: detail.id,
        rawFragment: raw,
        convertedFragment: converted,
        matchStatus: 'matched',
        matchNote: `专家标准中存在「${converted}」`,
      }
    }
  }

  // 2. 如果 converted_fragment 找不到，判断 raw_fragment 是否出现
  if (raw) {
    const normalizedRaw = normalizeForAsrCompare(raw)
    if (normalizedRef.includes(normalizedRaw)) {
      return {
        detailId: detail.id,
        rawFragment: raw,
        convertedFragment: converted,
        matchStatus: 'matched',
        matchNote: `专家标准中存在原始片段「${raw}」`,
      }
    }
  }

  // 3. 都找不到，标记为未匹配
  return {
    detailId: detail.id,
    rawFragment: raw,
    convertedFragment: converted,
    matchStatus: 'unmatched',
    matchNote: '专家标准中未找到对应文本',
  }
}

/**
 * 批量判断转化片段匹配状态
 */
export function judgeAllFragments(
  details: any[],
  referenceText: string
): FragmentMatchResult[] {
  if (!Array.isArray(details) || !referenceText) {
    return (details || []).map(d => ({
      detailId: d.id,
      rawFragment: d.raw_fragment || '',
      convertedFragment: d.converted_fragment || '',
      matchStatus: 'pending' as const,
      matchNote: '无专家标准文本',
    }))
  }

  return details.map(d => judgeFragmentMatch(d, referenceText))
}

// ========== 转化后 ASR 分段 ==========

/**
 * 将 converted_text 按 details 中的 converted_fragment 切分为段落。
 * 命中段标记 type='converted'，用于红色高亮。
 * 转化词后显示原始词：转化词（原：原始词）
 */
export function buildConvertedSegments(
  convertedText: string,
  details?: any[],
  highlightDetailId?: number | null
): TextSegment[] {
  const source = String(convertedText || '')
  if (!source) return []

  const marks: { start: number; end: number; rawFragment: string; detailId: number }[] = []
  if (Array.isArray(details)) {
    let cursor = 0
    for (const detail of details) {
      const fragment = String(detail?.converted_fragment || '').trim()
      if (!fragment) continue
      let idx = source.indexOf(fragment, cursor)
      if (idx === -1) idx = source.indexOf(fragment)
      if (idx === -1) continue
      const end = idx + fragment.length
      if (marks.some((m) => !(end <= m.start || idx >= m.end))) continue
      marks.push({ start: idx, end, rawFragment: detail.raw_fragment || '', detailId: detail.id })
      cursor = end
    }
  }

  if (!marks.length) return [{ text: source }]

  marks.sort((a, b) => a.start - b.start)
  const segments: TextSegment[] = []
  let cursor = 0

  for (const mark of marks) {
    if (mark.start > cursor) {
      segments.push({ text: source.slice(cursor, mark.start) }
      )
    }
    const convertedText = source.slice(mark.start, mark.end)
    const isHighlighted = highlightDetailId != null && mark.detailId === highlightDetailId

    const displayText = mark.rawFragment
      ? `${convertedText}（原：${mark.rawFragment}）`
      : convertedText

    segments.push({
      text: displayText,
      type: isHighlighted ? 'highlight' : 'converted',
      rawFragment: mark.rawFragment,
      detailId: mark.detailId,
    })
    cursor = mark.end
  }

  if (cursor < source.length) {
    segments.push({ text: source.slice(cursor) })
  }

  return segments
}

// ========== 专家标准 ASR 分段 ==========

/**
 * 专家标准 ASR 分段：
 * - 默认只显示 reference_annotations 人工标记
 * - 不做全文 diff 标红
 * - 未匹配的转化片段相关文本标红（可选）
 */
export function buildReferenceSegments(
  referenceText: string,
  annotations?: any[],
  unmatchedFragments?: FragmentMatchResult[]
): TextSegment[] {
  const source = String(referenceText || '')
  if (!source) return []

  const textLength = source.length
  const marks: { start: number; end: number; type: 'red' | 'orange' | 'green'; note: string }[] = []

  // 1. 收集 reference_annotations 标记
  if (Array.isArray(annotations)) {
    for (const ann of annotations) {
      if (!ann || typeof ann !== 'object') continue
      const start = Math.max(0, Math.min(Number(ann.start || 0), textLength))
      const end = Math.max(0, Math.min(Number(ann.end || 0), textLength))
      if (end <= start) continue
      const rawType = String(ann.type || 'red')
      const type: 'red' | 'orange' | 'green' = ['red', 'orange', 'green'].includes(rawType)
        ? (rawType as 'red' | 'orange' | 'green')
        : 'red'
      marks.push({ start, end, type, note: ann.note ? String(ann.note) : '' })
    }
  }

  // 2. 标记未匹配转化片段在专家标准中的位置
  if (Array.isArray(unmatchedFragments)) {
    for (const frag of unmatchedFragments) {
      if (frag.matchStatus !== 'unmatched') continue
      // 尝试在专家标准中找到对应的未匹配文本
      // 这里只标记，不做全文 diff
    }
  }

  if (!marks.length) return [{ text: source }]

  marks.sort((a, b) => a.start - b.start || a.end - b.end)
  const deduped: typeof marks = []
  for (const mark of marks) {
    if (deduped.length && mark.start < deduped[deduped.length - 1].end) continue
    deduped.push(mark)
  }

  const segments: TextSegment[] = []
  let cursor = 0

  for (const mark of deduped) {
    if (mark.start > cursor) {
      segments.push({ text: source.slice(cursor, mark.start) })
    }
    segments.push({ text: source.slice(mark.start, mark.end), type: mark.type, note: mark.note })
    cursor = mark.end
  }

  if (cursor < source.length) {
    segments.push({ text: source.slice(cursor) })
  }

  return segments
}
