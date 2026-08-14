/**
 * 同步状态 store —— 从 config_ui.html L1168-1248 迁移。
 *
 * 含：顶部"同步到 IDE"栏的 ideList（可拖拽排序）、
 * syncTargetIdes（勾选的目标 IDE）、autoSync 开关、syncScopes（同步范围）、
 * syncing 状态。
 *
 * ideList 的 key 与后端 IDE_REGISTRY 完全对齐（驼峰，如 TraeCN/TraeSoloCN）。
 *
 * 持久化：写入后端 config/ui/ui-state.json（通过 /api/ui-state），
 * 不再依赖 localStorage，避免浏览器/webview 重启丢失。
 */
import { defineStore } from 'pinia'
import { ref, reactive, watch } from 'vue'
import { api } from '../api/client'

export interface IdeItem {
  key: string
  label: string
  desc: string
}

// 旧 localStorage 键名（仅用于一次性迁移到后端）
const LEGACY_LS_ORDER = 'myagent.ideOrder'
const LEGACY_LS_TARGETS = 'myagent.ideSyncTargets'
const LEGACY_LS_AUTOSYNC = 'myagent.autoSync'

// 默认 IDE 列表（与 config_ui.html L1168-1183 一致，key 已对齐后端）
const DEFAULT_IDE_LIST: IdeItem[] = [
  { key: 'Agents', label: 'Agents', desc: '通用 agents 配置' },
  { key: 'CherryStudio', label: 'Cherry Studio', desc: 'Data/Skills + agents.db' },
  { key: 'Claude', label: 'Claude', desc: '.claude/settings.json + rules' },
  { key: 'CodeBuddy', label: 'CodeBuddy CN', desc: '~/.codebuddy/mcp.json + models.json' },
  { key: 'Codex', label: 'Codex', desc: '.codex/config.toml + rules' },
  { key: 'Cursor', label: 'Cursor', desc: '.cursor/rules + .cursor/mcp.json' },
  { key: 'IDEA', label: 'IDEA', desc: 'IDEA 配置' },
  { key: 'KimiCLI', label: 'Kimi CLI', desc: '~/.kimi/mcp.json + rules' },
  { key: 'KimiCode', label: 'Kimi Code', desc: '~/.kimi-code/mcp.json + rules' },
  { key: 'KimiWork', label: 'Kimi Work', desc: '~/.kimi-work/mcp.json + rules' },
  { key: 'OpenClaw', label: 'OpenClaw', desc: '.openclaw/rules' },
  { key: 'OpenCode', label: 'OpenCode', desc: '~/.config/opencode/opencode.json' },
  { key: 'OpenWorker', label: 'OpenWorker', desc: '~/.config/coworker/secrets.json + config.toml' },
  { key: 'Qoder', label: 'Qoder', desc: '.qoder/rules' },
  { key: 'QoderCN', label: 'Qoder CN', desc: '.qoder-cn/rules' },
  { key: 'Trae', label: 'Trae', desc: '.trae/rules + .trae/mcp.json' },
  { key: 'TraeCN', label: 'Trae CN', desc: '.trae-cn/rules + mcp' },
  { key: 'TraeSoloCN', label: 'Trae Work CN', desc: '.trae-solo-cn/rules' },
  { key: 'WorkBuddy', label: 'WorkBuddy CN', desc: '.workbuddy/rules + models.json' },
  { key: 'ZCode', label: 'ZCode', desc: '.zcode/zcode.json' },
  { key: 'Hermes', label: 'Hermes', desc: '.ade-hermes/rules + mcp' },
  { key: 'Pi', label: 'Pi', desc: '~/.pi/agent + mcp.json' },
  { key: 'CommandCode', label: 'Command Code', desc: '~/.commandcode/rules + mcp' },
]

/** 从旧 localStorage 读一次（用于首次迁移到后端） */
function readLegacyLs(): {
  ideOrder?: string[]
  ideSyncTargets?: string[]
  autoSync?: boolean
} {
  try {
    const order = JSON.parse(localStorage.getItem(LEGACY_LS_ORDER) || 'null')
    const targets = JSON.parse(localStorage.getItem(LEGACY_LS_TARGETS) || 'null')
    const auto = localStorage.getItem(LEGACY_LS_AUTOSYNC) === '1'
    return {
      ideOrder: Array.isArray(order) ? order : undefined,
      ideSyncTargets: Array.isArray(targets) ? targets : undefined,
      autoSync: auto || undefined,
    }
  } catch {
    return {}
  }
}

/** 清空旧 localStorage（迁移成功后调用，避免后续继续读旧值） */
function clearLegacyLs() {
  try {
    localStorage.removeItem(LEGACY_LS_ORDER)
    localStorage.removeItem(LEGACY_LS_TARGETS)
    localStorage.removeItem(LEGACY_LS_AUTOSYNC)
  } catch {
    /* ignore */
  }
}

export const useSyncStore = defineStore('sync', () => {
  const ideList = ref<IdeItem[]>(DEFAULT_IDE_LIST.map((i) => ({ ...i })))
  const dragIdeKey = ref('')
  const dragOverIdeKey = ref('')
  const syncScopes = reactive({ llm: true, mcp: true, skill: true, rules: true })

  // 默认不选中任何 IDE，由用户显式勾选后记忆
  const syncTargetIdes = ref<string[]>([])
  const syncing = ref(false)
  const autoSync = ref(false)

  // 是否已完成首次加载；加载完成前 watch 不回写后端，避免覆盖
  const loaded = ref(false)
  // 回写防抖 timer
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  /** 合并写入后端 UI 状态（防抖 200ms） */
  function persist(patch: Record<string, unknown>) {
    if (!loaded.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      api<{ ok: boolean }>('/api/ui-state', {
        method: 'POST',
        body: JSON.stringify(patch),
      }).catch(() => {
        /* 静默失败：UI 仍可用，只是没持久化 */
      })
    }, 200)
  }

  watch(
    syncTargetIdes,
    (v) => persist({ ideSyncTargets: v }),
    { deep: true },
  )

  watch(autoSync, (v) => persist({ autoSync: v }))

  // ===== IDE 拖拽排序 + 持久化 =====
  function saveIdeOrder() {
    persist({ ideOrder: ideList.value.map((i) => i.key) })
  }

  function applyIdeOrder(order: string[]) {
    if (!Array.isArray(order) || !order.length) return
    const map = new Map(ideList.value.map((i) => [i.key, i]))
    const ordered = order.map((k: string) => map.get(k)).filter(Boolean) as IdeItem[]
    // 追加未保存的新 IDE
    for (const i of ideList.value) {
      if (!order.includes(i.key)) ordered.push(i)
    }
    ideList.value = ordered
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

  /** 启动时从后端加载 UI 状态；后端为空时尝试从旧 localStorage 迁移一次 */
  async function loadFromBackend() {
    let state: Record<string, any> = {}
    try {
      state = await api<Record<string, any>>('/api/ui-state')
    } catch {
      state = {}
    }
    // 后端无数据 → 尝试从旧 localStorage 一次性迁移
    const backendEmpty =
      !state || !('ideSyncTargets' in state) && !('ideOrder' in state) && !('autoSync' in state)
    if (backendEmpty) {
      const legacy = readLegacyLs()
      if (legacy.ideSyncTargets) state.ideSyncTargets = legacy.ideSyncTargets
      if (legacy.ideOrder) state.ideOrder = legacy.ideOrder
      if (legacy.autoSync !== undefined) state.autoSync = legacy.autoSync
      // 把迁移结果回写到后端
      if (
        Array.isArray(state.ideSyncTargets) ||
        Array.isArray(state.ideOrder) ||
        typeof state.autoSync === 'boolean'
      ) {
        try {
          await api('/api/ui-state', {
            method: 'POST',
            body: JSON.stringify({
              ideSyncTargets: state.ideSyncTargets,
              ideOrder: state.ideOrder,
              autoSync: state.autoSync,
            }),
          })
          clearLegacyLs()
        } catch {
          /* 迁移失败不影响使用 */
        }
      }
    }

    if (Array.isArray(state.ideSyncTargets)) {
      syncTargetIdes.value = state.ideSyncTargets.filter((k: any) => typeof k === 'string')
    }
    if (typeof state.autoSync === 'boolean') {
      autoSync.value = state.autoSync
    }
    if (Array.isArray(state.ideOrder)) {
      applyIdeOrder(state.ideOrder)
    }
    loaded.value = true
  }

  // 异步初始化（不阻塞渲染，加载完成前先用默认值）
  loadFromBackend()

  return {
    ideList,
    dragIdeKey,
    dragOverIdeKey,
    syncScopes,
    syncTargetIdes,
    syncing,
    autoSync,
    saveIdeOrder,
    onIdeDragStart,
    onIdeDragOver,
    onIdeDrop,
    onIdeDragEnd,
    loadFromBackend,
  }
})
