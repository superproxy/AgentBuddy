import { defineStore } from 'pinia'
import { reactive } from 'vue'
import { api } from '../api/client'
import { useUiStore } from './ui'

export interface CmdItem {
  name: string
  command: string
  desc?: string
  category?: string
}

export const useCmdStore = defineStore('cmd', () => {
  const ui = useUiStore()
  const cmdData = reactive<{ commands: CmdItem[] }>({ commands: [] })

  async function loadCmd() {
    const r = await api<{ ok: boolean; data?: any }>('/api/cmd')
    if (r.ok) cmdData.commands = (r.data && r.data.commands) || []
  }
  async function saveCmd(silent = false) {
    const r = await api<{ ok: boolean; error?: string }>('/api/cmd', {
      method: 'POST', body: JSON.stringify({ data: cmdData }),
    })
    if (!silent) r.ok ? ui.toast('cmd.yaml 已保存') : ui.toast('保存失败: ' + r.error, 'err')
    return r.ok
  }
  function addCmd() {
    cmdData.commands.push({ name: '', command: '', desc: '', category: '' })
  }
  function deleteCmd(idx: number) {
    cmdData.commands.splice(idx, 1)
  }
  function copyCmd(command: string) {
    navigator.clipboard.writeText(command).then(() => ui.toast('已复制到剪贴板'))
  }

  return { cmdData, loadCmd, saveCmd, addCmd, deleteCmd, copyCmd }
})
