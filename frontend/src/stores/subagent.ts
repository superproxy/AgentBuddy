import { defineStore } from 'pinia'
import { reactive } from 'vue'
import { api } from '../api/client'
import { downloadFile } from '../api/download'
import { useUiStore } from './ui'

export interface SubagentItem {
  name: string
  role: string
  desc?: string
  category?: string
  prompt?: string
}

export const useSubagentStore = defineStore('subagent', () => {
  const ui = useUiStore()
  const subagentData = reactive<{ subagents: SubagentItem[] }>({ subagents: [] })

  async function loadSubagent() {
    const r = await api<{ ok: boolean; data?: any }>('/api/subagent')
    if (r.ok) subagentData.subagents = (r.data && r.data.subagents) || []
  }
  async function saveSubagent(silent = false) {
    const r = await api<{ ok: boolean; error?: string }>('/api/subagent', { method: 'POST', body: JSON.stringify({ data: subagentData }) })
    if (!silent) r.ok ? ui.toast('subagent.yaml 已保存') : ui.toast('保存失败: ' + r.error, 'err')
    return r.ok
  }
  function addSubagent(partial?: Partial<SubagentItem>) {
    subagentData.subagents.push({
      name: '',
      role: '',
      desc: '',
      category: '开发',
      prompt: '',
      ...partial,
    })
    return subagentData.subagents.length - 1
  }
  function deleteSubagent(idx: number) { subagentData.subagents.splice(idx, 1) }
  function updateSubagent(idx: number, item: SubagentItem) {
    if (idx < 0 || idx >= subagentData.subagents.length) return
    subagentData.subagents[idx] = { ...item }
  }
  async function exportSubagent() {
    const ok = await downloadFile('/api/subagent/export', 'subagent.yaml')
    if (ok) ui.toast('subagent 已导出')
    else ui.toast('导出失败或已取消', 'err')
  }
  async function importSubagent(content: string) {
    const r = await api<{ ok: boolean; error?: string }>('/api/subagent/import', { method: 'POST', body: JSON.stringify({ content }) })
    if (r.ok) { await loadSubagent(); ui.toast('导入成功') }
    else ui.toast('导入失败: ' + r.error, 'err')
  }

  async function syncToOpencode() {
    const r = await api<{ ok: boolean; count?: number; error?: string }>("/api/subagent/sync", { method: "POST" })
    if (r.ok) ui.toast(`已同步角色: ${r.message || r.count + " 个"}`)
    else ui.toast("同步失败: " + r.error, "err")
  }

  return {
    subagentData,
    loadSubagent,
    saveSubagent,
    addSubagent,
    deleteSubagent,
    updateSubagent,
    exportSubagent,
    importSubagent,
    syncToOpencode,
  }
})
