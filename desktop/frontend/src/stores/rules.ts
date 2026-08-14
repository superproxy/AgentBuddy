import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import { downloadFile } from '../api/download'
import { useUiStore } from './ui'

export interface RuleItem {
  name: string
  path: string
  category: string
  /** 岗位（frontmatter.role；无则后端用目录映射回退） */
  role: string
  description: string
  alwaysApply: boolean
  globs: string
  scene: string
  source: 'config' | 'template'
  size: number
}

export type SourceFilter = 'all' | 'custom' | 'template' | 'always'
/** all | __none__ | 具体岗位名 */
export type RoleFilter = string

export const PRESET_ROLES = ['前端', '后端', '工程', 'Git', '协作', '测试', '运维', '设计', '产品']

export const useRulesStore = defineStore('rules', () => {
  const ui = useUiStore()
  const rules = ref<RuleItem[]>([])
  const selectedRulePath = ref('')
  const editingContent = ref('')
  const editingMeta = ref({
    description: '',
    alwaysApply: false,
    globs: '',
    scene: '',
    role: '',
  })
  const dirty = ref(false)
  const listQuery = ref('')
  const sourceFilter = ref<SourceFilter>('all')
  const roleFilter = ref<RoleFilter>('all')

  const selectedRule = computed(() => rules.value.find((r) => r.path === selectedRulePath.value))

  const usedRoles = computed(() => {
    const map = new Map<string, number>()
    let none = 0
    for (const r of rules.value) {
      const name = (r.role || '').trim()
      if (!name) {
        none += 1
        continue
      }
      map.set(name, (map.get(name) || 0) + 1)
    }
    const list = [...map.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
    return { list, none }
  })

  const roleCatalog = computed(() => {
    const map = new Map<string, number>()
    for (const name of PRESET_ROLES) map.set(name, 0)
    for (const r of rules.value) {
      const name = (r.role || '').trim()
      if (!name) continue
      map.set(name, (map.get(name) || 0) + 1)
    }
    return [...map.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => {
        if (b.count !== a.count) return b.count - a.count
        return a.name.localeCompare(b.name, 'zh')
      })
  })

  const filteredRules = computed(() => {
    const q = listQuery.value.trim().toLowerCase()
    return rules.value.filter((r) => {
      if (sourceFilter.value === 'custom' && r.source !== 'config') return false
      if (sourceFilter.value === 'template' && r.source !== 'template') return false
      if (sourceFilter.value === 'always' && !r.alwaysApply) return false
      const role = (r.role || '').trim()
      if (roleFilter.value === '__none__' && role) return false
      if (roleFilter.value !== 'all' && roleFilter.value !== '__none__' && role !== roleFilter.value) {
        return false
      }
      if (q) {
        const hay = `${r.name} ${r.description} ${r.path} ${role}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  })

  const groupedRules = computed(() => {
    const groups: Record<string, RuleItem[]> = {}
    for (const r of filteredRules.value) {
      const cat = (r.role || '').trim() || '未分类'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(r)
    }
    const keys = Object.keys(groups).sort((a, b) => {
      if (a === '未分类') return 1
      if (b === '未分类') return -1
      return a.localeCompare(b, 'zh')
    })
    return keys.map((key) => ({ key, items: groups[key] }))
  })

  async function loadRules() {
    const r = await api<{ ok: boolean; data?: RuleItem[]; count?: number }>('/api/rules')
    if (r.ok) {
      rules.value = (r.data || []).map((item) => ({
        ...item,
        role: item.role || '',
      }))
      // 当前岗位筛选若已失效则回退
      if (
        roleFilter.value !== 'all' &&
        roleFilter.value !== '__none__' &&
        !usedRoles.value.list.some((x) => x.name === roleFilter.value)
      ) {
        roleFilter.value = 'all'
      }
      if (roleFilter.value === '__none__' && usedRoles.value.none === 0) {
        roleFilter.value = 'all'
      }
    }
  }

  async function selectRule(path: string, force = false) {
    if (!force && dirty.value && selectedRulePath.value && selectedRulePath.value !== path) {
      if (!confirm('有未保存更改，切换将丢失。继续？')) return false
    }
    selectedRulePath.value = path
    const r = await api<{ ok: boolean; content?: string; writable?: boolean; error?: string }>(
      '/api/rules/content?path=' + encodeURIComponent(path),
    )
    if (r.ok) {
      editingContent.value = r.content || ''
      const rule = rules.value.find((x) => x.path === path)
      if (rule) {
        editingMeta.value = {
          description: rule.description,
          alwaysApply: rule.alwaysApply,
          globs: rule.globs,
          scene: rule.scene,
          role: rule.role || '',
        }
      }
      dirty.value = false
      return true
    }
    ui.toast('加载失败: ' + (r.error || ''), 'err')
    return false
  }

  function onContentChange() {
    dirty.value = true
  }

  function setRole(role: string) {
    editingMeta.value.role = (role || '').trim()
    dirty.value = true
    // 即时反映到列表分组（未保存也能预览）
    const rule = rules.value.find((r) => r.path === selectedRulePath.value)
    if (rule) rule.role = editingMeta.value.role
  }

  function discardChanges() {
    if (!selectedRulePath.value) {
      dirty.value = false
      return
    }
    void selectRule(selectedRulePath.value, true)
  }

  async function saveRule() {
    if (!selectedRulePath.value) return
    const body = editingContent.value
    let bodyOnly = body
    if (body.startsWith('---')) {
      const parts = body.split('---', 3)
      bodyOnly = parts.length >= 3 ? parts[2].trim() : body
    }
    const fm: string[] = ['---']
    if (editingMeta.value.description) fm.push(`description: ${editingMeta.value.description}`)
    fm.push(`alwaysApply: ${editingMeta.value.alwaysApply ? 'true' : 'false'}`)
    if (editingMeta.value.globs) fm.push(`globs: ${editingMeta.value.globs}`)
    if (editingMeta.value.scene) fm.push(`scene: ${editingMeta.value.scene}`)
    if (editingMeta.value.role) fm.push(`role: ${editingMeta.value.role}`)
    fm.push('---', '')
    const content = fm.join('\n') + '\n' + bodyOnly + '\n'

    const r = await api<{ ok: boolean; error?: string }>('/api/rules/save', {
      method: 'POST',
      body: JSON.stringify({ path: selectedRulePath.value, content }),
    })
    if (r.ok) {
      ui.toast('规则已保存')
      dirty.value = false
      const keep = selectedRulePath.value
      await loadRules()
      if (keep) await selectRule(keep, true)
    } else {
      ui.toast('保存失败: ' + (r.error || ''), 'err')
    }
  }

  async function deleteRule(path: string) {
    const rule = rules.value.find((r) => r.path === path)
    if (rule?.source === 'template') {
      ui.toast('预置规则不可删除', 'warn')
      return
    }
    if (!confirm('删除规则 ' + path + '?')) return
    const r = await api<{ ok: boolean; error?: string }>(
      '/api/rules?path=' + encodeURIComponent(path),
      { method: 'DELETE' },
    )
    if (r.ok) {
      ui.toast('已删除')
      const idx = rules.value.findIndex((x) => x.path === path)
      await loadRules()
      if (selectedRulePath.value === path) {
        if (rules.value.length) {
          const next = rules.value[Math.min(Math.max(idx, 0), rules.value.length - 1)]
          await selectRule(next.path, true)
        } else {
          selectedRulePath.value = ''
          editingContent.value = ''
          editingMeta.value = { description: '', alwaysApply: false, globs: '', scene: '', role: '' }
          dirty.value = false
        }
      }
    } else {
      ui.toast('删除失败: ' + (r.error || ''), 'err')
    }
  }

  function newRule() {
    const name = prompt('输入规则文件名（不含 .md 扩展名）:', 'new-rule')
    if (!name) return
    const safeName = name.replace(/[^a-zA-Z0-9\-_]/g, '-')
    const path = safeName + '.md'
    editingMeta.value = { description: '', alwaysApply: false, globs: '', scene: '', role: '' }
    editingContent.value = '# ' + safeName + '\n\n在此编写规则内容...\n'
    selectedRulePath.value = path
    dirty.value = true
    rules.value = [
      {
        name: safeName,
        path,
        category: '',
        role: '',
        description: '',
        alwaysApply: false,
        globs: '',
        scene: '',
        source: 'config',
        size: 0,
      },
      ...rules.value,
    ]
  }

  function clearFilters() {
    listQuery.value = ''
    sourceFilter.value = 'all'
    roleFilter.value = 'all'
  }

  async function syncRules() {
    const r = await api<{ ok: boolean; count?: number; message?: string; error?: string }>(
      '/api/rules/sync',
      { method: 'POST' },
    )
    if (r.ok) ui.toast(r.message || `已同步 ${r.count} 个规则`)
    else ui.toast('同步失败: ' + (r.error || ''), 'err')
  }

  async function exportRules() {
    const ok = await downloadFile('/api/rules/export', 'rules-export.zip')
    if (ok) ui.toast('rules 已导出')
    else ui.toast('导出失败或已取消', 'err')
  }

  async function importRules(e: Event) {
    const input = e.target as HTMLInputElement
    const f = input.files && input.files[0]
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    fd.append('overwrite', 'true')
    const resp = await fetch('/api/rules/import', { method: 'POST', body: fd })
    const res = (await resp.json()) as { ok: boolean; count?: number; error?: string }
    input.value = ''
    if (res.ok) {
      ui.toast(`导入成功: ${res.count} 个规则`)
      await loadRules()
      if (rules.value.length && !selectedRulePath.value) {
        await selectRule(rules.value[0].path, true)
      }
    } else {
      ui.toast('导入失败: ' + (res.error || ''), 'err')
    }
  }

  return {
    rules,
    selectedRulePath,
    editingContent,
    editingMeta,
    dirty,
    listQuery,
    sourceFilter,
    roleFilter,
    selectedRule,
    usedRoles,
    roleCatalog,
    filteredRules,
    groupedRules,
    loadRules,
    selectRule,
    onContentChange,
    setRole,
    discardChanges,
    saveRule,
    deleteRule,
    newRule,
    clearFilters,
    syncRules,
    exportRules,
    importRules,
  }
})
