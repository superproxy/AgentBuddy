import { defineStore } from 'pinia'
import { reactive, computed, ref } from 'vue'
import { api } from '../api/client'
import { useUiStore } from './ui'

export const useKeysStore = defineStore('keys', () => {
  const ui = useUiStore()
  const keysData = reactive<any>({ mcp: {} })
  const keysPath = ref<string>('')
  const loaded = ref(false)
  const listQuery = ref('')
  const selectedKey = ref<string>('')
  // 变量引用出处：{KEY: [{source, scope, field, kind}, ...]}
  const usages = ref<{ [k: string]: Array<{ source: string; scope: string; field: string; kind: string }> }>({})
  // 新建行草稿（不进 keysData.mcp，直到提交）
  const draft = reactive<{ key: string; value: string; description: string; error: string }>({
    key: '',
    value: '',
    description: '',
    error: '',
  })
  const isAdding = ref(false)

  // 规范化为 {value, description} 形式
  function normalizeEntry(v: any): { value: string; description: string } {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      return {
        value: typeof v.value === 'string' ? v.value : '',
        description: typeof v.description === 'string' ? v.description : '',
      }
    }
    // 旧格式：字符串
    return { value: typeof v === 'string' ? v : '', description: '' }
  }

  const keyEntries = computed(() => {
    const mcp = keysData.mcp || {}
    const q = listQuery.value.trim().toLowerCase()
    const entries = Object.entries(mcp).map(([k, v]: [string, any]) => ({
      key: k,
      ...normalizeEntry(v),
    }))
    if (!q) return entries
    return entries.filter(
      (e) =>
        e.key.toLowerCase().includes(q) ||
        e.value.toLowerCase().includes(q) ||
        e.description.toLowerCase().includes(q),
    )
  })

  const keyCount = computed(() => Object.keys(keysData.mcp || {}).length)

  const selectedEntry = computed(() => {
    if (!selectedKey.value) return null
    const v = keysData.mcp?.[selectedKey.value]
    if (v === undefined) return null
    return { key: selectedKey.value, ...normalizeEntry(v) }
  })

  async function loadKeys() {
    const r = await api('/api/keys')
    if (r.ok) {
      // 清空再赋值（保持响应式）
      Object.keys(keysData.mcp).forEach((k) => delete keysData.mcp[k])
      const data = r.data?.mcp || {}
      Object.keys(data).forEach((k) => {
        keysData.mcp[k] = normalizeEntry(data[k])
      })
      usages.value = r.usages || {}
      keysPath.value = r.path || ''
      loaded.value = true
    } else {
      ui.toast('加载密钥失败: ' + r.error, 'err')
    }
  }

  async function saveKeys() {
    const r = await api('/api/keys', { method: 'POST', body: JSON.stringify({ data: keysData }) })
    r.ok ? ui.toast('keys.yaml 已保存') : ui.toast('保存失败: ' + r.error, 'err')
  }

  /** 开始新建行（不弹窗，前端直接展示一行可编辑） */
  function startAdd() {
    draft.key = ''
    draft.value = ''
    draft.description = ''
    draft.error = ''
    isAdding.value = true
  }

  function cancelAdd() {
    isAdding.value = false
    draft.key = ''
    draft.value = ''
    draft.description = ''
    draft.error = ''
  }

  /** 提交新建行 → 调用后端 API 创建 */
  async function commitAdd() {
    const key = draft.key.trim()
    if (!key) {
      draft.error = '变量名不能为空'
      return false
    }
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      draft.error = '仅支持字母、数字、下划线，且不能以数字开头'
      return false
    }
    if (keysData.mcp[key]) {
      draft.error = '变量已存在'
      return false
    }
    const r = await api('/api/keys/key', {
      method: 'POST',
      body: JSON.stringify({
        key,
        value: draft.value,
        description: draft.description,
      }),
    })
    if (!r.ok) {
      draft.error = r.error || '创建失败'
      return false
    }
    keysData.mcp[key] = { value: draft.value, description: draft.description }
    selectedKey.value = key
    isAdding.value = false
    draft.key = ''
    draft.value = ''
    draft.description = ''
    draft.error = ''
    ui.toast('已添加: ' + key)
    return true
  }

  async function deleteKey(key: string) {
    const ok = await ui.askConfirm({
      title: '删除密钥？',
      message: '删除后不可恢复。',
      detail: key,
      confirmText: '确认删除',
      tone: 'danger',
    })
    if (!ok) return
    const r = await api('/api/keys/key/' + encodeURIComponent(key), { method: 'DELETE' })
    if (r.ok) {
      delete keysData.mcp[key]
      if (selectedKey.value === key) selectedKey.value = ''
      ui.toast('已删除')
    } else {
      ui.toast('删除失败: ' + r.error, 'err')
    }
  }

  /** 更新单条 value/description（PATCH 到后端） */
  async function patchEntry(key: string, patch: { value?: string; description?: string }) {
    if (!keysData.mcp[key]) return
    // 本地立即更新（保持响应式）
    const cur = normalizeEntry(keysData.mcp[key])
    const next = { ...cur, ...patch }
    keysData.mcp[key] = next
    // 后台异步持久化
    const r = await api('/api/keys/key/' + encodeURIComponent(key), {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
    if (!r.ok) ui.toast('保存失败: ' + r.error, 'err')
  }

  async function updateValue(key: string, value: string) {
    return patchEntry(key, { value })
  }

  async function updateDescription(key: string, description: string) {
    return patchEntry(key, { description })
  }

  function selectKey(key: string) {
    selectedKey.value = key
  }

  /**
   * 解析粘贴文本为 key/value 列表。
   * 支持格式：
   *   KEY=value
   *   KEY="value"
   *   KEY='value'
   *   export KEY=value       (bash/zsh)
   *   export KEY="value"
   *   $env:KEY = "value"     (PowerShell)
   *   set KEY=value           (Windows CMD)
   *   # 注释行 跳过
   *   空行 跳过
   * 多行粘贴会拆分为多条目。
   * 返回：[{key, value, description?}, ...]
   */
  function parseEnvText(text: string): Array<{ key: string; value: string; description?: string }> {
    if (!text) return []
    const results: Array<{ key: string; value: string; description?: string }> = []
    const lines = text.split(/\r?\n/)
    const keyRe = /^[A-Za-z_][A-Za-z0-9_]*$/
    for (let raw of lines) {
      let line = raw.trim()
      if (!line) continue
      // 跳过注释
      if (line.startsWith('#') || line.startsWith('//')) continue
      // 去除前缀
      line = line.replace(/^export\s+/, '') // bash/zsh
      line = line.replace(/^set\s+/i, '') // CMD
      line = line.replace(/^\$env:/, '') // PowerShell 前缀
      // 拆分 key=value（首个 = 或冒号+空格）
      let m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/)
      if (!m) {
        // 尝试 KEY : value 格式（YAML 风）
        m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$/)
        if (!m) continue
      }
      const key = m[1]
      if (!keyRe.test(key)) continue
      let value = m[2].trim()
      // 去除尾部注释（仅当值未被引号包裹时）
      if (value && !/^["']/.test(value)) {
        const hashIdx = value.indexOf(' #')
        if (hashIdx >= 0) value = value.slice(0, hashIdx).trim()
      }
      // 去除外层引号
      if (value.length >= 2) {
        const first = value[0]
        const last = value[value.length - 1]
        if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
          value = value.slice(1, -1)
        }
      }
      results.push({ key, value })
    }
    return results
  }

  /**
   * 批量导入：跳过已存在的 key，返回 {created, skipped} 数量。
   */
  async function batchImport(items: Array<{ key: string; value: string; description?: string }>): Promise<{ created: number; skipped: string[] }> {
    const created: string[] = []
    const skipped: string[] = []
    for (const item of items) {
      const key = item.key.trim()
      if (!key || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
        skipped.push(item.key || '(invalid)')
        continue
      }
      if (keysData.mcp[key]) {
        skipped.push(key)
        continue
      }
      const r = await api('/api/keys/key', {
        method: 'POST',
        body: JSON.stringify({
          key,
          value: item.value || '',
          description: item.description || '',
        }),
      })
      if (r.ok) {
        keysData.mcp[key] = { value: item.value || '', description: item.description || '' }
        created.push(key)
      } else {
        skipped.push(key)
      }
    }
    if (created.length) ui.toast(`已导入 ${created.length} 条` + (skipped.length ? `，跳过 ${skipped.length} 条` : ''))
    return { created: created.length, skipped }
  }

  /**
   * 生成 shell 环境变量配置文本（保留作为预览/导出辅助）。
   * @param shell 'powershell' | 'bash' | 'zsh'
   * @param includeEmpty 是否包含空值变量
   */
  function exportShell(shell: 'powershell' | 'bash' | 'zsh', includeEmpty = false): string {
    const mcp = keysData.mcp || {}
    const entries = Object.entries(mcp).map(([k, v]: [string, any]) => ({
      key: k,
      ...normalizeEntry(v),
    }))
    const lines: string[] = []
    if (shell === 'powershell') {
      lines.push('# PowerShell 环境变量配置（Windows）')
      lines.push('# 用法：将以下内容保存为 env.ps1，或在 PowerShell 会话中直接粘贴执行')
      lines.push('')
      for (const e of entries) {
        if (!e.value && !includeEmpty) continue
        // PowerShell 单引号转义：' → ''
        const v = e.value.replace(/'/g, "''")
        lines.push(`$env:${e.key} = '${v}'`)
      }
    } else if (shell === 'zsh') {
      lines.push('#!/bin/zsh')
      lines.push('# zsh 环境变量配置（macOS）')
      lines.push('# 用法：将以下内容追加到 ~/.zshrc，或 source env.zsh')
      lines.push('')
      for (const e of entries) {
        if (!e.value && !includeEmpty) continue
        const v = e.value.replace(/'/g, "'\\''")
        lines.push(`export ${e.key}='${v}'`)
      }
    } else {
      // bash
      lines.push('#!/bin/bash')
      lines.push('# bash 环境变量配置（Linux）')
      lines.push('# 用法：将以下内容追加到 ~/.bashrc，或 source env.sh')
      lines.push('')
      for (const e of entries) {
        if (!e.value && !includeEmpty) continue
        const v = e.value.replace(/'/g, "'\\''")
        lines.push(`export ${e.key}='${v}'`)
      }
    }
    return lines.join('\n')
  }

  /**
   * 把 keys 应用到操作系统（让环境变量在系统中生效）。
   * @param options.keys 仅应用指定变量；省略则应用全部
   * @param options.includeEmpty 是否包含空值变量
   * @returns { ok, applied, skipped, target, note }
   */
  async function applyToSystem(options: { keys?: string[]; includeEmpty?: boolean } = {}): Promise<{
    ok: boolean
    applied: Array<{ key: string; value: string }>
    skipped: Array<{ key: string; reason: string }>
    target: string
    note: string
    error?: string
  }> {
    const r = await api('/api/keys/apply-env', {
      method: 'POST',
      body: JSON.stringify({
        keys: options.keys || null,
        includeEmpty: !!options.includeEmpty,
      }),
    })
    if (r.ok) {
      ui.toast(`已应用 ${r.applied?.length || 0} 个变量到系统`)
    } else {
      ui.toast('应用到系统失败: ' + (r.error || ''), 'err')
    }
    return r
  }

  return {
    keysData,
    keysPath,
    loaded,
    listQuery,
    selectedKey,
    selectedEntry,
    draft,
    isAdding,
    usages,
    keyEntries,
    keyCount,
    loadKeys,
    saveKeys,
    startAdd,
    cancelAdd,
    commitAdd,
    addKey: startAdd, // 向后兼容
    deleteKey,
    updateValue,
    updateDescription,
    patchEntry,
    selectKey,
    parseEnvText,
    batchImport,
    exportShell,
    applyToSystem,
  }
})

