import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import { useUiStore } from './ui'

/** Hook 事件类型 */
export type HookEvent =
  | 'SessionStart'
  | 'UserPromptSubmit'
  | 'PreToolUse'
  | 'PostToolUse'
  | 'Stop'
  | 'Notification'

export const HOOK_EVENTS: HookEvent[] = [
  'SessionStart',
  'UserPromptSubmit',
  'PreToolUse',
  'PostToolUse',
  'Stop',
  'Notification',
]

export const HOOK_EVENT_DESC: Record<HookEvent, string> = {
  SessionStart: '创建 Session 后、发起第一个对话前',
  UserPromptSubmit: '用户发送 Query 后、智能体处理前',
  PreToolUse: '智能体发起工具调用后、实际执行前',
  PostToolUse: '工具调用实际执行完成后',
  Stop: '智能体完成输出、准备结束当前 Query 时',
  Notification: '工具调用等待用户确认或任务完成时',
}

export interface HookCommand {
  type: string
  command: string
  timeout?: number
  [key: string]: any
}

export interface HookGroup {
  hooks: HookCommand[]
  matcher?: string
}

export interface HooksConfig {
  description?: string
  hooks: Partial<Record<HookEvent, HookGroup[]>>
}

export const useHooksStore = defineStore('hooks', () => {
  const ui = useUiStore()
  const hooksData = ref<HooksConfig>({ description: '', hooks: {} })
  const dirty = ref(false)

  const eventCount = computed(() => {
    const counts: Record<string, number> = {}
    for (const ev of HOOK_EVENTS) {
      counts[ev] = (hooksData.value.hooks[ev] || []).length
    }
    return counts
  })

  const totalHooks = computed(() =>
    Object.values(eventCount.value).reduce((a, b) => a + b, 0),
  )

  async function loadHooks() {
    const r = await api<{ ok: boolean; data?: HooksConfig }>('/api/hooks')
    if (r.ok && r.data) {
      hooksData.value = r.data
      dirty.value = false
    }
  }

  async function saveHooks(silent = false) {
    const r = await api<{ ok: boolean; error?: string }>('/api/hooks', {
      method: 'POST',
      body: JSON.stringify({ data: hooksData.value }),
    })
    if (!silent) {
      r.ok ? ui.toast('hooks.json 已保存') : ui.toast('保存失败: ' + r.error, 'err')
    }
    if (r.ok) dirty.value = false
    return r.ok
  }

  function addHook(event: HookEvent) {
    if (!hooksData.value.hooks[event]) {
      hooksData.value.hooks[event] = []
    }
    hooksData.value.hooks[event]!.push({
      hooks: [{ type: 'command', command: '', timeout: 10 }],
    })
    dirty.value = true
  }

  function deleteHook(event: HookEvent, index: number) {
    const groups = hooksData.value.hooks[event]
    if (!groups) return
    groups.splice(index, 1)
    if (groups.length === 0) {
      delete hooksData.value.hooks[event]
    }
    dirty.value = true
  }

  function addCommand(event: HookEvent, groupIndex: number) {
    const groups = hooksData.value.hooks[event]
    if (!groups || !groups[groupIndex]) return
    groups[groupIndex].hooks.push({ type: 'command', command: '', timeout: 10 })
    dirty.value = true
  }

  function deleteCommand(event: HookEvent, groupIndex: number, cmdIndex: number) {
    const groups = hooksData.value.hooks[event]
    if (!groups || !groups[groupIndex]) return
    groups[groupIndex].hooks.splice(cmdIndex, 1)
    if (groups[groupIndex].hooks.length === 0) {
      groups.splice(groupIndex, 1)
      if (groups.length === 0) {
        delete hooksData.value.hooks[event]
      }
    }
    dirty.value = true
  }

  function moveHook(event: HookEvent, from: number, to: number) {
    const groups = hooksData.value.hooks[event]
    if (!groups) return
    if (from === to || from < 0 || to < 0 || from >= groups.length || to >= groups.length) return
    const [item] = groups.splice(from, 1)
    groups.splice(to, 0, item)
    dirty.value = true
  }

  function moveCommand(event: HookEvent, groupIndex: number, from: number, to: number) {
    const groups = hooksData.value.hooks[event]
    if (!groups || !groups[groupIndex]) return
    const cmds = groups[groupIndex].hooks
    if (from === to || from < 0 || to < 0 || from >= cmds.length || to >= cmds.length) return
    const [item] = cmds.splice(from, 1)
    cmds.splice(to, 0, item)
    dirty.value = true
  }

  function onContentChange() {
    dirty.value = true
  }

  async function syncHooks() {
    const r = await api<{ ok: boolean; message?: string; error?: string }>(
      '/api/hooks/sync',
      { method: 'POST' },
    )
    if (r.ok) ui.toast(r.message || '已同步 hooks')
    else ui.toast('同步失败: ' + (r.error || ''), 'err')
  }

  function exportHooks() {
    window.location.href = '/api/hooks/export'
  }

  async function importHooks(content: string) {
    const r = await api<{ ok: boolean; error?: string }>('/api/hooks/import', {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
    if (r.ok) {
      ui.toast('导入成功')
      await loadHooks()
    } else {
      ui.toast('导入失败: ' + (r.error || ''), 'err')
    }
  }

  return {
    hooksData,
    dirty,
    eventCount,
    totalHooks,
    loadHooks,
    saveHooks,
    addHook,
    deleteHook,
    addCommand,
    deleteCommand,
    moveHook,
    moveCommand,
    onContentChange,
    syncHooks,
    exportHooks,
    importHooks,
  }
})
