/**
 * 同步栏「国内版」筛选 — key 与 IDE_REGISTRY / ide.yaml 一致。
 * WorkBuddy CN、DeepSeek Harness 等国内常用 AIDE 归入此类。
 */
export const CN_AIDE_KEYS = new Set([
  'CodeBuddy',
  'QoderCN',
  'TraeCN',
  'TraeSoloCN',
  'WorkBuddy',
  'DeepSeek',
  'ZCode',
])

export function isCnAideKey(key: string): boolean {
  return CN_AIDE_KEYS.has(key)
}
