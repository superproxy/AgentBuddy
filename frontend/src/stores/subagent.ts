import { defineStore } from 'pinia'
import { reactive } from 'vue'
import { api } from '../api/client'
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
  function addSubagent() { subagentData.subagents.push({ name: '', role: '', desc: '', category: '', prompt: '' }) }
  function deleteSubagent(idx: number) { subagentData.subagents.splice(idx, 1) }
  function exportSubagent() { window.location.href = '/api/subagent/export' }
  async function importSubagent(content: string) {
    const r = await api<{ ok: boolean; error?: string }>('/api/subagent/import', { method: 'POST', body: JSON.stringify({ content }) })
    if (r.ok) { await loadSubagent(); ui.toast('导入成功') }
    else ui.toast('导入失败: ' + r.error, 'err')
  }

  return { subagentData, loadSubagent, saveSubagent, addSubagent, deleteSubagent, exportSubagent, importSubagent }
})
