import { defineStore } from 'pinia'
import { reactive } from 'vue'
import { api } from '../api/client'
import { useUiStore } from './ui'

export interface CmdItem {
  name: string
  description?: string
  prompt?: string
}

export const useCmdStore = defineStore('cmd', () => {
  const ui = useUiStore()
  const cmdData = reactive<{ commands: CmdItem[] }>({ commands: [] })

  async function loadCmd() {
    const r = await api<{ ok: boolean; data?: any }>('/api/cmd')
    if (r.ok) cmdData.commands = (r.data && r.data.commands) || []
  }
  async function saveCmd(silent = false) {
    const r = await api<{ ok: boolean; error?: string }>('/api/cmd', { method: 'POST', body: JSON.stringify({ data: cmdData }) })
    if (!silent) r.ok ? ui.toast('cmd.yaml 已保存') : ui.toast('保存失败: ' + r.error, 'err')
    return r.ok
  }
  function addCmd() { cmdData.commands.push({ name: '', description: '', prompt: '' }) }
  function deleteCmd(idx: number) { cmdData.commands.splice(idx, 1) }
  function exportCmd() { window.location.href = '/api/cmd/export' }
  async function importCmd(content: string) {
    const r = await api<{ ok: boolean; error?: string }>('/api/cmd/import', { method: 'POST', body: JSON.stringify({ content }) })
    if (r.ok) { await loadCmd(); ui.toast('导入成功') }
    else ui.toast('导入失败: ' + r.error, 'err')
  }

  async function syncToOpencode() {
    const r = await api<{ ok: boolean; count?: number; error?: string }>("/api/cmd/sync-opencode", { method: "POST" })
    if (r.ok) ui.toast(`已同步 ${r.count} 个命令到 OpenCode`)
    else ui.toast("同步失败: " + r.error, "err")
  }

  return { cmdData, loadCmd, saveCmd, addCmd, deleteCmd, exportCmd, importCmd, syncToOpencode }
})
