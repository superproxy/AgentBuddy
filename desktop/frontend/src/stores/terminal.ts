import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import { useUiStore } from './ui'

export const useTerminalStore = defineStore('terminal', () => {
  const ui = useUiStore()
  const running = ref(false)
  const terminalUrl = ref('')
  const loading = ref(false)

  async function start() {
    if (loading.value) return
    loading.value = true
    try {
      const r = await api<{ ok: boolean; url?: string; port?: number; error?: string }>(
        '/api/terminal/start', { method: 'POST' }
      )
      if (r.ok) {
        running.value = true
        terminalUrl.value = r.url || ''
        ui.toast('终端已启动')
      } else {
        ui.toast('终端启动失败: ' + (r.error || ''), 'err')
      }
    } finally {
      loading.value = false
    }
  }

  async function stop() {
    const r = await api<{ ok: boolean }>('/api/terminal/stop', { method: 'POST' })
    if (r.ok) {
      running.value = false
      terminalUrl.value = ''
      ui.toast('终端已关闭')
    }
  }

  async function checkStatus() {
    const r = await api<{ ok: boolean; running?: boolean; url?: string; port?: number }>(
      '/api/terminal/status'
    )
    if (r.ok && r.running) {
      running.value = true
      terminalUrl.value = r.url || ''
    } else {
      running.value = false
      terminalUrl.value = ''
    }
  }

  return { running, terminalUrl, loading, start, stop, checkStatus }
})
