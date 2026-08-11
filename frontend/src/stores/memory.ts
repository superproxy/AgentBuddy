import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import { downloadFile } from '../api/download'
import { useUiStore } from './ui'

/** 记忆类型 */
export type MemoryType = 'user' | 'project' | 'global'

export const MEMORY_TYPES: { value: MemoryType; label: string }[] = [
  { value: 'user', label: '用户记忆' },
  { value: 'project', label: '项目记忆' },
  { value: 'global', label: '全局记忆' },
]

export const MEMORY_TYPE_DESC: Record<MemoryType, string> = {
  user: '个人偏好、身份、习惯等，跨项目生效',
  project: '当前项目相关的技术栈、约定、背景，仅当前项目生效',
  global: '对所有项目生效的通用记忆',
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

/** 生成简单唯一 id（时间戳 + 随机） */
function genId(): string {
  return 'mem_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8)
}

export const useMemoryStore = defineStore('memory', () => {
  const ui = useUiStore()
  const memoryData = ref<MemoryConfig>({ description: '', memories: [] })
  const dirty = ref(false)
  const saving = ref(false)

  const totalMemories = computed(() => memoryData.value.memories.length)
  const enabledCount = computed(() => memoryData.value.memories.filter((m) => m.enabled).length)

  async function loadMemory() {
    const r = await api<{ ok: boolean; data?: MemoryConfig }>('/api/memory')
    if (r.ok && r.data) {
      memoryData.value = r.data
      dirty.value = false
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

  function addMemory(type: MemoryType = 'user') {
    memoryData.value.memories.push({
      id: genId(),
      name: '',
      type,
      content: '',
      enabled: true,
    })
    dirty.value = true
  }

  function deleteMemory(id: string) {
    const idx = memoryData.value.memories.findIndex((m) => m.id === id)
    if (idx >= 0) {
      memoryData.value.memories.splice(idx, 1)
      dirty.value = true
    }
  }

  function toggleMemory(id: string) {
    const m = memoryData.value.memories.find((x) => x.id === id)
    if (m) {
      m.enabled = !m.enabled
      dirty.value = true
    }
  }

  function moveMemory(from: number, to: number) {
    const arr = memoryData.value.memories
    if (from === to || from < 0 || to < 0 || from >= arr.length || to >= arr.length) return
    const [item] = arr.splice(from, 1)
    arr.splice(to, 0, item)
    dirty.value = true
  }

  function onContentChange() {
    dirty.value = true
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
    loadMemory,
    saveMemory,
    addMemory,
    deleteMemory,
    toggleMemory,
    moveMemory,
    onContentChange,
    syncMemory,
    exportMemory,
    importMemory,
  }
})
