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
  function exportPlugin(file: string, format: 'zip' | 'yaml' = 'zip') {
    window.location.href = '/api/plugin/export?file=' + encodeURIComponent(file) + '&format=' + format
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
    // 统一用 FormData 上传（支持 .zip 含 skills 包 和 .yaml 单文件）
    const fd = new FormData()
    fd.append('file', f)
    const r = await fetch('/api/plugin/import', { method: 'POST', body: fd })
    const res = await r.json() as {
      ok: boolean; name?: string; error?: string; msg?: string
      plugin_count?: number; skill_count?: number; skipped?: any[]
    }
    input.value = ''
    if (res.ok) {
      // 构建 toast 摘要
      const parts: string[] = []
      if (res.plugin_count) parts.push(`${res.plugin_count} 个插件`)
      if (res.skill_count) parts.push(`${res.skill_count} 个技能`)
      const detail = parts.length ? '：' + parts.join('、') : ''
      const skippedNote = res.skipped?.length ? `，跳过 ${res.skipped.length} 项` : ''
      ui.toast('导入成功' + detail + skippedNote)
      refreshPluginList()
      skill.loadInstalledSkills()
    } else if (res.error === 'exists') {
      if (confirm(res.msg || '已存在，是否覆盖？')) {
        const fd2 = new FormData()
        fd2.append('file', f)
        fd2.append('overwrite', 'true')
        const r2 = await fetch('/api/plugin/import', { method: 'POST', body: fd2 })
        const res2 = await r2.json() as { ok: boolean; error?: string; plugin_count?: number; skill_count?: number }
        if (res2.ok) {
          const parts: string[] = []
          if (res2.plugin_count) parts.push(`${res2.plugin_count} 个插件`)
          if (res2.skill_count) parts.push(`${res2.skill_count} 个技能`)
          ui.toast('已覆盖导入' + (parts.length ? '：' + parts.join('、') : ''))
          refreshPluginList()
          skill.loadInstalledSkills()
        } else ui.toast('导入失败: ' + (res2.error || ''), 'err')
      }
    } else ui.toast('导入失败: ' + (res.error || ''), 'err')
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
    selectedPluginFile.value = file
    ui.toast('请在顶部切换到「插件构建」tab 继续编辑', 'warn')
  }

  return {
    plugins, selectedPluginFile, installingPlugin, importPluginInput,
    refreshPluginList, exportPlugin, exportAllPlugins, triggerImportPlugin,
    onImportPluginFile, onTogglePlugin, editPlugin,
  }
})
