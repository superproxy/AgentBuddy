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

export type SkillSourceId = 'skillssh' | 'smithery' | 'modelscope' | 'skillsmp' | 'clawhub' | 'anthropics' | 'github'

export const SKILL_SOURCE_ORDER: SkillSourceId[] = [
  'skillssh', 'smithery', 'modelscope', 'skillsmp', 'clawhub', 'anthropics', 'github',
]
export const SKILL_SOURCE_LABELS: Record<SkillSourceId, string> = {
  skillssh: 'skills.sh',
  smithery: 'Smithery',
  modelscope: 'ModelScope',
  skillsmp: 'SkillsMP',
  clawhub: 'ClawHub',
  anthropics: 'Anthropic',
  github: 'GitHub',
}

export const useSkillStore = defineStore('skill', () => {
  const ui = useUiStore()
  const sync = useSyncStore()
  const localSkills = ref<any[]>([])
  const skillFilter = reactive({ cat: '', role: '', text: '' })
  const skillTab = ref<'market' | 'local' | 'manual'>('market')
  const skillMarketSources = ref<SkillSourceId[]>(['skillssh', 'smithery', 'modelscope', 'skillsmp'])
  const skillSearchQ = ref('')
  const skillSearchResults = ref<any[]>([])
  const skillSearchHint = ref('')
  const skillSearched = ref(false)
  const skillSearching = ref(false)
  const skillSearchMeta = ref<any>(null)
  const manualSkillInput = ref('')
  const manualPreview = ref<{
    source: string
    skill_filter: string
    skills: { name: string; description?: string; path?: string }[]
    method: string
    count: number
  } | null>(null)
  const manualSelected = ref<string[]>([])
  const manualPreviewing = ref(false)
  const manualInstalling = ref(false)
  const installedSkills = ref<InstalledSkill[]>([])
  const listFilter = ref<'all' | 'on' | 'off'>('all')
  const listQuery = ref('')
  const localFilterQ = ref('')
  const _togglingSkills = reactive(new Set<string>())

  /** @deprecated 兼容旧模板；请用 skillMarketSources */
  const skillSources = reactive({ modelscope: true, skillssh: true })

  const skillCategories = computed(() => [...new Set(localSkills.value.map((s) => s.category).filter(Boolean))].sort())
  const skillRoles = computed(() => [...new Set(localSkills.value.flatMap((s) => (s.role || '').split('|')).filter(Boolean))].sort())
  const filteredLocalSkills = computed(() => {
    const q = localFilterQ.value.trim().toLowerCase() || skillFilter.text.trim().toLowerCase()
    return localSkills.value.filter((s) => {
      if (skillFilter.cat && s.category !== skillFilter.cat) return false
      if (skillFilter.role && !(s.role || '').includes(skillFilter.role)) return false
      if (q) {
        if (!(s.skill_name || '').toLowerCase().includes(q) && !(s.description || '').toLowerCase().includes(q)) return false
      }
      return true
    })
  })
  const enabledInstalledCount = computed(() => installedSkills.value.filter((s) => s.enabled).length)
  const disabledInstalledCount = computed(() => installedSkills.value.length - enabledInstalledCount.value)
  const filteredInstalled = computed(() => {
    const q = listQuery.value.trim().toLowerCase()
    return installedSkills.value.filter((s) => {
      if (listFilter.value === 'on' && !s.enabled) return false
      if (listFilter.value === 'off' && s.enabled) return false
      if (!q) return true
      return s.name.toLowerCase().includes(q) || (s.path || '').toLowerCase().includes(q)
    })
  })

  async function loadLocalSkills() {
    if (localSkills.value.length) return
    const r = await api<{ ok: boolean; data?: any[] }>('/api/skills/local')
    if (r.ok) localSkills.value = r.data || []
  }
  function toggleSkillSource(src: SkillSourceId) {
    const cur = skillMarketSources.value
    if (cur.includes(src)) {
      if (cur.length === 1) { ui.toast('请至少保留一个搜索源', 'warn'); return }
      skillMarketSources.value = cur.filter((s) => s !== src)
    } else {
      skillMarketSources.value = [...cur, src]
    }
  }
  async function searchSkills() {
    const q = skillSearchQ.value.trim()
    if (!q) return
    const srcs = skillMarketSources.value
    if (!srcs.length) { ui.toast('请至少勾选一个搜索源', 'warn'); return }
    skillSearched.value = true
    skillSearching.value = true
    skillSearchHint.value = '搜索中...'
    skillSearchMeta.value = null
    try {
      const r = await api<{
        ok: boolean
        data?: any[]
        errors?: string[]
        meta?: any
        error?: string
      }>('/api/skills/search?q=' + encodeURIComponent(q) + '&sources=' + encodeURIComponent(srcs.join(',')) + '&limit=12')
      if (r.ok) {
        skillSearchResults.value = r.data || []
        skillSearchMeta.value = r.meta || null
        if (r.errors && r.errors.length) ui.toast('部分源失败: ' + r.errors.join('; '), 'warn')
      } else {
        skillSearchResults.value = []
        ui.toast('搜索失败: ' + (r.error || '未知错误'), 'err')
      }
    } finally {
      skillSearching.value = false
      skillSearchHint.value = ''
    }
  }
  async function installFromSearch(s: any) {
    // 本地预置技能：直接从 template/skills/ 复制
    if (s.source === 'local' || (s.install_command === '' && s.source === 'local')) {
      ui.clearLog()
      await runSse('/api/skills/install?source=local:' + encodeURIComponent(s.name), (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
      return
    }
    let cmd = s.install_command || ''
    if (cmd && /^\s*npx\b/.test(cmd)) {
      // 仅对 skills add 补 --copy / npx --yes；clawhub 等其它 CLI 不改写
      if (/\bskills\s+add\b/.test(cmd)) {
        // 避免 npx 交互提示 Need to install the following packages: skills@...
        if (!/\bnpx\s+(-y|--yes)\b/.test(cmd)) cmd = cmd.replace(/^\s*npx\b/, 'npx --yes')
        if (!cmd.includes('--copy')) cmd = cmd.replace(/ -y$/, '').trimEnd() + ' --copy -y'
        if (!/\s-y(\s|$)/.test(cmd)) cmd += ' -y'
      }
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

  function clearManualPreview() {
    manualPreview.value = null
    manualSelected.value = []
  }

  async function previewManualSource() {
    const raw = manualSkillInput.value.trim()
    if (!raw) { ui.toast('请输入安装源', 'warn'); return }
    manualPreviewing.value = true
    clearManualPreview()
    try {
      const r = await api<{
        ok: boolean
        error?: string
        source?: string
        skill_filter?: string
        skills?: { name: string; description?: string; path?: string }[]
        method?: string
        count?: number
      }>('/api/skills/preview?source=' + encodeURIComponent(raw))
      if (!r.ok) {
        ui.toast('解析失败: ' + (r.error || '未知错误'), 'err')
        return
      }
      const skills = r.skills || []
      manualPreview.value = {
        source: r.source || raw,
        skill_filter: r.skill_filter || '',
        skills,
        method: r.method || '',
        count: r.count ?? skills.length,
      }
      // 单技能或已指定 @skill：默认全选；多技能默认不全选，避免误装全部
      if (skills.length <= 1 || r.skill_filter) {
        manualSelected.value = skills.map((s) => s.name)
      } else {
        manualSelected.value = []
      }
      if (!skills.length) ui.toast('该源下未发现可安装技能', 'warn')
    } finally {
      manualPreviewing.value = false
    }
  }

  function toggleManualSkill(name: string) {
    const set = new Set(manualSelected.value)
    if (set.has(name)) set.delete(name)
    else set.add(name)
    manualSelected.value = [...set]
  }

  function selectAllManualSkills(on: boolean) {
    if (!manualPreview.value) return
    manualSelected.value = on ? manualPreview.value.skills.map((s) => s.name) : []
  }

  async function installSelectedManualSkills() {
    if (!manualPreview.value) {
      await previewManualSource()
      return
    }
    const src = manualPreview.value.source
    const selected = manualSelected.value
    if (!selected.length) {
      ui.toast('请至少勾选一个技能', 'warn')
      return
    }
    manualInstalling.value = true
    ui.clearLog()
    try {
      const qs =
        '/api/skills/install?source=' + encodeURIComponent(src) +
        '&skills=' + encodeURIComponent(selected.join(','))
      await runSse(qs, (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
      ui.toast(`已提交安装 ${selected.length} 个技能`)
    } finally {
      manualInstalling.value = false
    }
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
    const ok = await ui.askConfirm({
      title: '卸载此技能？',
      message: '将从本地技能目录移除，此操作不可撤销。',
      detail: name,
      confirmText: '确认卸载',
      tone: 'danger',
    })
    if (!ok) return
    const r = await api<{ ok: boolean; error?: string; removed?: string[] }>('/api/skills/' + encodeURIComponent(name), { method: 'DELETE' })
    if (r.ok) {
      ui.toast('已卸载 ' + name)
      await loadInstalledSkills()
    } else {
      ui.toast('卸载失败: ' + (r.error || '未知错误'), 'err')
    }
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
    localSkills, skillFilter, skillTab, skillSources, skillMarketSources,
    skillSearchQ, skillSearchResults, skillSearchHint, skillSearched, skillSearching, skillSearchMeta,
    manualSkillInput, manualPreview, manualSelected, manualPreviewing, manualInstalling,
    installedSkills,
    listFilter, listQuery, localFilterQ,
    skillCategories, skillRoles, filteredLocalSkills, enabledInstalledCount, disabledInstalledCount,
    filteredInstalled,
    loadLocalSkills, searchSkills, toggleSkillSource, installFromSearch, installManualSkill,
    previewManualSource, clearManualPreview, toggleManualSkill, selectAllManualSkills, installSelectedManualSkills,
    loadInstalledSkills,
    viewSkillMd, uninstallSkill, syncToIde, onToggleSkill, toggleAllInstalled,
  }
})
