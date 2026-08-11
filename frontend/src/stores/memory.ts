import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import { downloadFile } from '../api/download'
import { useUiStore } from './ui'

/** 记忆类型：用户记忆 / 技能记忆，各固定一条 */
export type MemoryType = 'user' | 'skill'

export const MEMORY_TYPES: { value: MemoryType; label: string }[] = [
  { value: 'user', label: '用户记忆' },
  { value: 'skill', label: '技能记忆' },
]

export const MEMORY_TYPE_DESC: Record<MemoryType, string> = {
  user: '个人偏好、身份、习惯、语言偏好等，跨项目生效',
  skill: '编码风格、技术栈约定、工作流程等技能性记忆，指导 AI 协作方式',
}

export interface MemoryItem {
  id: string
  name: string
  type: MemoryType
  content: string
  enabled: boolean
}

export interface MemoryConfig {
  description?: string
  memories: MemoryItem[]
}

/**
 * 归一化记忆配置：固定为「用户记忆 + 技能记忆」各一条。
 * 旧版（user/project/global 可多条）自动合并：
 *   - type === user  → 并入用户记忆
 *   - type === skill → 并入技能记忆
 *   - 其他旧类型（project/global）→ 并入技能记忆
 * 返回 migrated=true 表示内容与旧格式不一致，提示用户保存迁移结果。
 */
function normalizeMemory(data: MemoryConfig): { data: MemoryConfig; migrated: boolean } {
  const src = Array.isArray(data.memories) ? data.memories : []
  const userParts: string[] = []
  const skillParts: string[] = []
  let userEnabled = true
  let skillEnabled = true
  for (const m of src) {
    const c = (m.content || '').trim()
    if (!c) continue
    if (m.type === 'user') {
      userParts.push(c)
      userEnabled = userEnabled && m.enabled !== false
    } else if (m.type === 'skill') {
      skillParts.push(c)
      skillEnabled = skillEnabled && m.enabled !== false
    } else {
      // 旧类型 project / global 归入技能记忆
      skillParts.push(c)
      skillEnabled = skillEnabled && m.enabled !== false
    }
  }
  const normalized: MemoryConfig = {
    description: typeof data.description === 'string' ? data.description : '',
    memories: [
      { id: 'user-memory', name: '用户记忆', type: 'user', content: userParts.join('\n\n'), enabled: userEnabled },
      { id: 'skill-memory', name: '技能记忆', type: 'skill', content: skillParts.join('\n\n'), enabled: skillEnabled },
    ],
  }
  const migrated = JSON.stringify(normalized) !== JSON.stringify(data)
  return { data: normalized, migrated }
}

export const useMemoryStore = defineStore('memory', () => {
  const ui = useUiStore()
  const memoryData = ref<MemoryConfig>({ description: '', memories: [] })
  const dirty = ref(false)
  const saving = ref(false)

  const totalMemories = computed(() => memoryData.value.memories.length)
  const enabledCount = computed(() => memoryData.value.memories.filter((m) => m.enabled).length)

  const userMemory = computed(() => memoryData.value.memories.find((m) => m.type === 'user'))
  const skillMemory = computed(() => memoryData.value.memories.find((m) => m.type === 'skill'))

  /** 确保指定类型条目存在（各类型固定一条） */
  function ensureItem(type: MemoryType): MemoryItem {
    let item = memoryData.value.memories.find((m) => m.type === type)
    if (!item) {
      item = {
        id: `${type}-memory`,
        name: type === 'user' ? '用户记忆' : '技能记忆',
        type,
        content: '',
        enabled: true,
      }
      memoryData.value.memories.push(item)
    }
    return item
  }

  function setContent(type: MemoryType, content: string) {
    ensureItem(type).content = content
    dirty.value = true
  }

  function setEnabled(type: MemoryType, enabled: boolean) {
    ensureItem(type).enabled = enabled
    dirty.value = true
  }

  async function loadMemory() {
    const r = await api<{ ok: boolean; data?: MemoryConfig }>('/api/memory')
    if (r.ok && r.data) {
      const { data, migrated } = normalizeMemory(r.data)
      memoryData.value = data
      // 旧格式（多条/project/global）迁移后提示保存
      dirty.value = migrated
    }
  }

  async function saveMemory(silent = false) {
    saving.value = true
    try {
      const r = await api<{ ok: boolean; error?: string }>('/api/memory', {
        method: 'POST',
        body: JSON.stringify({ data: memoryData.value }),
      })
      if (!silent) {
        r.ok ? ui.toast('memory.json 已保存') : ui.toast('保存失败: ' + r.error, 'err')
      }
      if (r.ok) dirty.value = false
      return r.ok
    } finally {
      saving.value = false
    }
  }

  async function syncMemory() {
    const r = await api<{ ok: boolean; message?: string; error?: string }>(
      '/api/memory/sync',
      { method: 'POST' },
    )
    if (r.ok) ui.toast(r.message || '已同步记忆')
    else ui.toast('同步失败: ' + (r.error || ''), 'err')
  }

  async function exportMemory() {
    const ok = await downloadFile('/api/memory/export', 'memory.json')
    if (ok) ui.toast('记忆已导出')
    else ui.toast('导出失败或已取消', 'err')
  }

  async function importMemory(content: string) {
    const r = await api<{ ok: boolean; error?: string }>('/api/memory/import', {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
    if (r.ok) {
      ui.toast('导入成功')
      await loadMemory()
    } else {
      ui.toast('导入失败: ' + (r.error || ''), 'err')
    }
  }

  return {
    memoryData,
    dirty,
    saving,
    totalMemories,
    enabledCount,
    userMemory,
    skillMemory,
    loadMemory,
    saveMemory,
    setContent,
    setEnabled,
    syncMemory,
    exportMemory,
    importMemory,
  }
})
