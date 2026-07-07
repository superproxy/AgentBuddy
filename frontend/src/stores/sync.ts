/**
 * 同步状态 store —— 从 config_ui.html L1168-1248 迁移。
 *
 * 含：顶部"同步到 IDE"栏的 ideList（可拖拽排序，localStorage 持久化）、
 * syncTargetIdes（勾选的目标 IDE）、autoSync 开关、syncScopes（同步范围）、
 * syncing 状态。
 *
 * ideList 的 key 与后端 IDE_REGISTRY 完全对齐（驼峰，如 TraeCN/TraeSoloCN）。
 */
import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

export interface IdeItem {
  key: string
  label: string
  desc: string
}

const IDE_ORDER_KEY = 'myagent.ideOrder'
const IDE_SYNC_TARGET_KEY = 'myagent.ideSyncTargets'
const IDE_AUTOSYNC_KEY = 'myagent.autoSync'

// 默认 IDE 列表（与 config_ui.html L1168-1183 一致，key 已对齐后端）
const DEFAULT_IDE_LIST: IdeItem[] = [
  { key: 'Agents', label: 'Agents', desc: '通用 agents 配置' },
  { key: 'Claude', label: 'Claude', desc: '.claude/settings.json + rules' },
  { key: 'Codex', label: 'Codex', desc: '.codex/config.toml + rules' },
  { key: 'Cursor', label: 'Cursor', desc: '.cursor/rules + .cursor/mcp.json' },
  { key: 'IDEA', label: 'IDEA', desc: 'IDEA 配置' },
  { key: 'OpenClaw', label: 'OpenClaw', desc: '.openclaw/rules' },
  { key: 'OpenCode', label: 'OpenCode', desc: 'opencode.json' },
  { key: 'Qoder', label: 'Qoder', desc: '.qoder/rules' },
  { key: 'QoderCN', label: 'Qoder CN', desc: '.qoder-cn/rules' },
  { key: 'Trae', label: 'Trae', desc: '.trae/rules + .trae/mcp.json' },
  { key: 'TraeCN', label: 'Trae CN', desc: '.trae-cn/rules + mcp' },
  { key: 'TraeSoloCN', label: 'Trae Work CN', desc: '.trae-solo-cn/rules' },
  { key: 'WorkBuddy', label: 'WorkBuddy', desc: '.workbuddy/rules + models.json' },
  { key: 'ZCode', label: 'ZCode', desc: '.zcode/zcode.json' },
]

export const useSyncStore = defineStore('sync', () => {
  const ideList = ref<IdeItem[]>(DEFAULT_IDE_LIST.map((i) => ({ ...i })))
  const dragIdeKey = ref('')
  const dragOverIdeKey = ref('')
  const syncScopes = reactive({ llm: true, mcp: true, skill: true, rules: true })

  // 同步目标 IDE（从 localStorage 恢复，默认 Codex）
  const savedTargets = (() => {
    try {
      return JSON.parse(localStorage.getItem(IDE_SYNC_TARGET_KEY) || 'null')
    } catch {
      return null
    }
  })()
  const syncTargetIdes = ref<string[]>(Array.isArray(savedTargets) ? savedTargets : ['Codex'])

  const syncing = ref(false)
  const autoSync = ref(localStorage.getItem(IDE_AUTOSYNC_KEY) === '1')

  // ===== IDE 拖拽排序 + localStorage 持久化 =====
  function saveIdeOrder() {
    try {
      localStorage.setItem(IDE_ORDER_KEY, JSON.stringify(ideList.value.map((i) => i.key)))
    } catch {
      /* ignore */
    }
  }

  function loadIdeOrder() {
    try {
      const saved = localStorage.getItem(IDE_ORDER_KEY)
      if (!saved) return
      const order = JSON.parse(saved)
      if (!Array.isArray(order) || !order.length) return
      const map = new Map(ideList.value.map((i) => [i.key, i]))
      const ordered = order.map((k: string) => map.get(k)).filter(Boolean) as IdeItem[]
      // 追加未保存的新 IDE
      for (const i of ideList.value) {
        if (!order.includes(i.key)) ordered.push(i)
      }
      ideList.value = ordered
    } catch {
      /* ignore */
    }
  }

  function onIdeDragStart(e: DragEvent, key: string) {
    dragIdeKey.value = key
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
  }

  function onIdeDragOver(e: DragEvent, key: string) {
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
    dragOverIdeKey.value = key
  }

  function onIdeDrop(e: DragEvent, key: string) {
    e.preventDefault()
    const fromKey = dragIdeKey.value
    const toKey = key
    if (!fromKey || fromKey === toKey) {
      dragIdeKey.value = ''
      dragOverIdeKey.value = ''
      return
    }
    const list = ideList.value
    const fromIdx = list.findIndex((i) => i.key === fromKey)
    const toIdx = list.findIndex((i) => i.key === toKey)
    if (fromIdx < 0 || toIdx < 0) {
      dragIdeKey.value = ''
      dragOverIdeKey.value = ''
      return
    }
    const [moved] = list.splice(fromIdx, 1)
    list.splice(toIdx, 0, moved)
    saveIdeOrder()
    dragIdeKey.value = ''
    dragOverIdeKey.value = ''
  }

  function onIdeDragEnd() {
    dragIdeKey.value = ''
    dragOverIdeKey.value = ''
  }

  // 初始化时恢复保存的顺序
  loadIdeOrder()

  return {
    ideList,
    dragIdeKey,
    dragOverIdeKey,
    syncScopes,
    syncTargetIdes,
    syncing,
    autoSync,
    saveIdeOrder,
    loadIdeOrder,
    onIdeDragStart,
    onIdeDragOver,
    onIdeDrop,
    onIdeDragEnd,
  }
})
