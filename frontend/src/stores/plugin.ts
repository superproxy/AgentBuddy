import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { api } from '../api/client'
import { runSse } from '../api/sse'
import { useUiStore } from './ui'
import { useSyncStore } from './sync'
import { useSkillStore } from './skill'

export interface PluginItem {
  file: string
  name: string
  version: string
  description: string
  installed: boolean
  skills_count: number
  mcp_count: number
}

export const usePluginStore = defineStore('plugin', () => {
  const ui = useUiStore()
  const sync = useSyncStore()
  const skill = useSkillStore()
  const plugins = ref<PluginItem[]>([])
  const selectedPluginFile = ref('')
  const installingPlugin = ref('')
  const importPluginInput = ref<HTMLInputElement | null>(null)

  async function refreshPluginList() {
    const r = await api<{ ok: boolean; data?: PluginItem[] }>('/api/plugins')
    if (r.ok) plugins.value = r.data || []
  }
  function exportPlugin(file: string) {
    window.location.href = '/api/plugin/export?file=' + encodeURIComponent(file)
  }
  function exportAllPlugins() {
    window.location.href = '/api/plugin/export-all'
  }
  function triggerImportPlugin() {
    importPluginInput.value && importPluginInput.value.click()
  }
  async function onImportPluginFile(e: Event) {
    const input = e.target as HTMLInputElement
    const f = input.files && input.files[0]
    if (!f) return
    const content = await f.text()
    const filename = f.name
    const r = await api<{ ok: boolean; name?: string; error?: string; msg?: string }>('/api/plugin/import', {
      method: 'POST', body: JSON.stringify({ filename, content }),
    })
    input.value = ''
    if (r.ok) { ui.toast('导入成功: ' + r.name); refreshPluginList() }
    else if (r.error === 'exists') {
      if (confirm(r.msg || '已存在，是否覆盖？')) {
        const r2 = await api<{ ok: boolean; name?: string; error?: string }>('/api/plugin/import', {
          method: 'POST', body: JSON.stringify({ filename, content, overwrite: true }),
        })
        if (r2.ok) { ui.toast('已覆盖导入: ' + r2.name); refreshPluginList() }
        else ui.toast('导入失败: ' + (r2.error || ''), 'err')
      }
    } else ui.toast('导入失败: ' + (r.error || ''), 'err')
  }
  async function onTogglePlugin(p: PluginItem, checked: boolean) {
    if (installingPlugin.value) { ui.toast('正在安装其他插件，请稍候', 'warn'); return }
    if (checked) {
      installingPlugin.value = p.name
      p.installed = true
      const ides = sync.syncTargetIdes.join(',')
      ui.clearLog()
      await runSse('/api/plugin/install?file=' + encodeURIComponent(p.file) + '&ide=' + encodeURIComponent(ides),
        (line) => ui.appendLog(line),
        { onDone: () => { skill.loadInstalledSkills(); refreshPluginList() } })
      installingPlugin.value = ''
    } else {
      if (!confirm('卸载插件 ' + p.name + '?')) { p.installed = true; return }
      const r = await api<{ ok: boolean; error?: string }>('/api/plugin/uninstall', {
        method: 'POST', body: JSON.stringify({ name: p.name }),
      })
      if (r.ok) { p.installed = false; ui.toast('已卸载: ' + p.name); refreshPluginList() }
      else { p.installed = true; ui.toast('卸载失败: ' + (r.error || '未知错误'), 'err') }
    }
  }
  function editPlugin(file: string) {
    ui.toast('插件构建向导迁移中，暂用旧版 /old', 'warn')
  }

  return {
    plugins, selectedPluginFile, installingPlugin, importPluginInput,
    refreshPluginList, exportPlugin, exportAllPlugins, triggerImportPlugin,
    onImportPluginFile, onTogglePlugin, editPlugin,
  }
})
