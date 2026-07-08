import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { api } from '../api/client'
import { runSse } from '../api/sse'
import { useUiStore } from './ui'
import { useSyncStore } from './sync'

export interface InstalledSkill {
  name: string
  path: string
  skill_md_exists: boolean
  enabled: boolean
}

export const useSkillStore = defineStore('skill', () => {
  const ui = useUiStore()
  const sync = useSyncStore()
  const localSkills = ref<any[]>([])
  const skillFilter = reactive({ cat: '', role: '', text: '' })
  const skillTab = ref('local')
  const skillSources = reactive({ modelscope: true, skillssh: false })
  const skillSearchQ = ref('')
  const skillSearchResults = ref<any[]>([])
  const skillSearchHint = ref('')
  const skillSearched = ref(false)
  const manualSkillInput = ref('')
  const installedSkills = ref<InstalledSkill[]>([])
  const _togglingSkills = reactive(new Set<string>())

  const skillCategories = computed(() => [...new Set(localSkills.value.map((s) => s.category).filter(Boolean))].sort())
  const skillRoles = computed(() => [...new Set(localSkills.value.flatMap((s) => (s.role || '').split('|')).filter(Boolean))].sort())
  const filteredLocalSkills = computed(() => localSkills.value.filter((s) => {
    if (skillFilter.cat && s.category !== skillFilter.cat) return false
    if (skillFilter.role && !(s.role || '').includes(skillFilter.role)) return false
    if (skillFilter.text) {
      const t = skillFilter.text.toLowerCase()
      if (!(s.skill_name || '').toLowerCase().includes(t) && !(s.description || '').toLowerCase().includes(t)) return false
    }
    return true
  }))
  const enabledInstalledCount = computed(() => installedSkills.value.filter((s) => s.enabled).length)

  async function loadLocalSkills() {
    if (localSkills.value.length) return
    const r = await api<{ ok: boolean; data?: any[] }>('/api/skills/local')
    if (r.ok) localSkills.value = r.data || []
  }
  async function searchSkills() {
    const q = skillSearchQ.value.trim()
    if (!q) return
    const srcs = Object.keys(skillSources).filter((k) => (skillSources as any)[k])
    if (!srcs.length) { ui.toast('请至少勾选一个搜索源', 'warn'); return }
    skillSearched.value = true
    skillSearchHint.value = '搜索中...'
    let results: any[] = []
    if (srcs.includes('local')) {
      const localHits = localSkills.value.filter((s) =>
        (s.skill_name || '').toLowerCase().includes(q.toLowerCase()) ||
        (s.description || '').toLowerCase().includes(q.toLowerCase()),
      ).map((s) => ({ source: 'local', name: s.skill_name, description: s.description, author: '', install_count: 0, install_command: '' }))
      results = results.concat(localHits)
    }
    const marketSrcs = srcs.filter((s) => s !== 'local')
    if (marketSrcs.length) {
      const sourceParam = marketSrcs.length === 2 ? 'all' : marketSrcs[0]
      const r = await api<{ ok: boolean; data?: any[]; errors?: string[] }>('/api/skills/search?q=' + encodeURIComponent(q) + '&source=' + sourceParam)
      if (r.ok) {
        results = results.concat(r.data || [])
        if (r.errors && r.errors.length) ui.toast('部分源失败: ' + r.errors.join('; '), 'warn')
      } else { ui.toast('搜索失败', 'err') }
    }
    skillSearchResults.value = results
    skillSearchHint.value = ''
  }
  async function installFromSearch(s: any) {
    // 本地预置技能：直接从 template/skills/ 复制
    if (s.source === 'local' || (s.install_command === '' && s.source === 'local')) {
      ui.clearLog()
      await runSse('/api/skills/install?source=local:' + encodeURIComponent(s.name), (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
      return
    }
    let cmd = s.install_command || ''
    if (cmd && cmd.startsWith('npx')) {
      if (!cmd.includes('--copy')) cmd = cmd.replace(/ -y$/, '') + ' --copy -y'
      if (!cmd.includes('-y')) cmd += ' -y'
      ui.clearLog()
      await runSse('/api/skills/install?command=' + encodeURIComponent(cmd), (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
      return
    }
    const src = s.author ? s.author + '/' + s.name : s.name
    ui.clearLog()
    await runSse('/api/skills/install?source=' + encodeURIComponent(src), (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
  }
  async function installManualSkill() {
    if (!manualSkillInput.value.trim()) return
    ui.clearLog()
    await runSse('/api/skills/install?source=' + encodeURIComponent(manualSkillInput.value.trim()), (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
  }
  async function loadInstalledSkills() {
    const r = await api<{ ok: boolean; data?: InstalledSkill[] }>('/api/skills/installed')
    if (r.ok) installedSkills.value = r.data || []
  }
  async function viewSkillMd(name: string) {
    const r = await api<{ ok: boolean; content?: string; error?: string }>('/api/skills/' + encodeURIComponent(name) + '/skillmd')
    if (r.ok) ui.showModal(name + ' / SKILL.md', r.content || '')
    else ui.toast('读取失败: ' + r.error, 'err')
  }
  async function uninstallSkill(name: string) {
    if (!confirm('卸载 ' + name + '?')) return
    const r = await api<{ ok: boolean; error?: string }>('/api/skills/' + encodeURIComponent(name), { method: 'DELETE' })
    if (r.ok) { ui.toast('已卸载'); loadInstalledSkills() }
    else ui.toast('卸载失败: ' + r.error, 'err')
  }
  async function syncToIde() {
    ui.clearLog()
    await runSse('/api/init-ide?ide=All&scope=skill', (line) => ui.appendLog(line))
  }
  async function onToggleSkill(s: InstalledSkill, enabled: boolean) {
    if (_togglingSkills.has(s.name)) return
    _togglingSkills.add(s.name)
    s.enabled = enabled
    try {
      const r = await api<{ ok: boolean; error?: string }>('/api/skills/' + encodeURIComponent(s.name) + '/toggle', {
        method: 'POST', body: JSON.stringify({ enabled, ides: sync.syncTargetIdes }),
      })
      if (r.ok) ui.toast(enabled ? `已启用 ${s.name} 并同步` : `已禁用 ${s.name}`)
      else { s.enabled = !enabled; ui.toast('切换失败: ' + (r.error || '未知错误'), 'err') }
    } catch (e: any) {
      s.enabled = !enabled
      ui.toast('切换失败: ' + e.message, 'err')
    } finally {
      _togglingSkills.delete(s.name)
    }
  }
  async function toggleAllInstalled(enabled: boolean) {
    const targets = installedSkills.value.filter((s) => s.enabled !== enabled)
    if (!targets.length) return
    if (!confirm(enabled ? `启用全部 ${targets.length} 个技能并同步?` : `禁用全部 ${targets.length} 个技能并同步?`)) return
    targets.forEach((s) => (s.enabled = enabled))
    for (const s of targets) {
      try {
        await api('/api/skills/' + encodeURIComponent(s.name) + '/toggle', {
          method: 'POST', body: JSON.stringify({ enabled, ides: sync.syncTargetIdes }),
        })
      } catch { /* 忽略单个失败 */ }
    }
    ui.toast(`已${enabled ? '启用' : '禁用'} ${targets.length} 个技能`)
  }

  return {
    localSkills, skillFilter, skillTab, skillSources, skillSearchQ, skillSearchResults,
    skillSearchHint, skillSearched, manualSkillInput, installedSkills,
    skillCategories, skillRoles, filteredLocalSkills, enabledInstalledCount,
    loadLocalSkills, searchSkills, installFromSearch, installManualSkill, loadInstalledSkills,
    viewSkillMd, uninstallSkill, syncToIde, onToggleSkill, toggleAllInstalled,
  }
})
