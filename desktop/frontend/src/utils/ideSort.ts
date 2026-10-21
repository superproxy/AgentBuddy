/** AIDE 列表按显示名称字母序（中文 locale，同名称再比 key） */
export function compareIdeLabel(
  a: { key: string; label?: string },
  b: { key: string; label?: string },
): number {
  const la = (a.label || a.key).trim()
  const lb = (b.label || b.key).trim()
  const c = la.localeCompare(lb, 'zh-CN', { sensitivity: 'base' })
  if (c !== 0) return c
  return a.key.localeCompare(b.key, 'en')
}

export function sortByIdeLabel<T extends { key: string; label?: string }>(items: T[]): T[] {
  return [...items].sort(compareIdeLabel)
}

export function compareBrandName(a: string, b: string): number {
  return a.localeCompare(b, 'zh-CN', { sensitivity: 'base' })
}
