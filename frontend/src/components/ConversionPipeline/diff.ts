/**
 * 文本差异比对工具（词级 LCS）。
 * 从旧 StepInputOutput 提取，供步骤工作台 / 最终结果差异高亮复用。
 * 诚实实现：仅按词级高亮内容差异，不伪造精确逐字 diff。
 */

export interface DiffSegment {
  type: 'same' | 'del' | 'add'
  text: string
}

function tokenize(text: string): string[] {
  return text.match(/\S+|\s+/g) || []
}

/**
 * 按词级（保留空白 token）做 LCS 比对，合并相邻同类段后返回。
 * 纯空白的新增/删除视为噪声丢弃；文本过长时降级为整段并排，不逐词比对。
 */
export function simpleDiff(oldText: string, newText: string): DiffSegment[] {
  if (oldText === newText) return [{ type: 'same', text: oldText }]
  const oldTokens = tokenize(oldText)
  const newTokens = tokenize(newText)
  if (!oldTokens.length || !newTokens.length || oldTokens.length > 500 || newTokens.length > 500) {
    return [
      ...(oldText ? [{ type: 'del' as const, text: oldText }] : []),
      ...(newText ? [{ type: 'add' as const, text: newText }] : []),
    ]
  }

  const n = oldTokens.length
  const m = newTokens.length
  // dp[i][j]：oldTokens[0..i) 与 newTokens[0..j) 的 LCS 长度
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0))
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      dp[i][j] = oldTokens[i - 1] === newTokens[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1])
    }
  }

  const raw: DiffSegment[] = []
  let i = n
  let j = m
  while (i > 0 && j > 0) {
    if (oldTokens[i - 1] === newTokens[j - 1]) {
      raw.push({ type: 'same', text: oldTokens[i - 1] })
      i--
      j--
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      raw.push({ type: 'del', text: oldTokens[i - 1] })
      i--
    } else {
      raw.push({ type: 'add', text: newTokens[j - 1] })
      j--
    }
  }
  while (i > 0) { raw.push({ type: 'del', text: oldTokens[i - 1] }); i-- }
  while (j > 0) { raw.push({ type: 'add', text: newTokens[j - 1] }); j-- }
  raw.reverse()

  // 丢弃纯空白的新增/删除（空白变化视为噪声），再合并相邻同类段
  return mergeSegments(raw)
}

/**
 * 字符级 LCS 比对（标准ASR文本左右差异用）。
 * 中文/医学文本按单字对齐更直观；文本过大时降级为整段并排，不逐字比对。
 */
export function simpleDiffChars(oldText: string, newText: string): DiffSegment[] {
  if (oldText === newText) return [{ type: 'same', text: oldText }]
  const a = Array.from(oldText)
  const b = Array.from(newText)
  if (!a.length || !b.length || a.length * b.length > 4_000_000) {
    return [
      ...(oldText ? [{ type: 'del' as const, text: oldText }] : []),
      ...(newText ? [{ type: 'add' as const, text: newText }] : []),
    ]
  }

  const n = a.length
  const m = b.length
  const width = m + 1
  // dp 展平为一维 Uint32Array：dp[i * width + j] = LCS(a[0..i), b[0..j))
  const dp = new Uint32Array((n + 1) * width)
  for (let i = 1; i <= n; i++) {
    const row = i * width
    const prevRow = (i - 1) * width
    const ai = a[i - 1]
    for (let j = 1; j <= m; j++) {
      dp[row + j] = ai === b[j - 1]
        ? dp[prevRow + j - 1] + 1
        : Math.max(dp[prevRow + j], dp[row + j - 1])
    }
  }

  const raw: DiffSegment[] = []
  let i = n
  let j = m
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      raw.push({ type: 'same', text: a[i - 1] })
      i--
      j--
    } else if (dp[(i - 1) * width + j] >= dp[i * width + j - 1]) {
      raw.push({ type: 'del', text: a[i - 1] })
      i--
    } else {
      raw.push({ type: 'add', text: b[j - 1] })
      j--
    }
  }
  while (i > 0) { raw.push({ type: 'del', text: a[i - 1] }); i-- }
  while (j > 0) { raw.push({ type: 'add', text: b[j - 1] }); j-- }
  raw.reverse()
  return mergeSegments(raw)
}

/** 合并相邻同类段；纯空白的新增/删除视为噪声丢弃 */
function mergeSegments(raw: DiffSegment[]): DiffSegment[] {
  const merged: DiffSegment[] = []
  for (const seg of raw) {
    if ((seg.type === 'del' || seg.type === 'add') && /^\s*$/.test(seg.text)) continue
    const last = merged[merged.length - 1]
    if (last && last.type === seg.type) last.text += seg.text
    else merged.push({ ...seg })
  }
  return merged
}
