<script setup lang="ts">
import { onMounted, ref, nextTick, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useKeysStore } from '../stores/keys'
import { useUiStore } from '../stores/ui'

type ShellType = 'powershell' | 'zsh' | 'bash'

const ui = useUiStore()
const keys = useKeysStore() as any
// 响应式 state 必须用 storeToRefs 解构，否则丢失响应式
const { keysPath, keyEntries, keyCount, listQuery, draft, isAdding, usages } = storeToRefs(keys)

const newKeyInput = ref<HTMLInputElement | null>(null)
const newValueInput = ref<HTMLInputElement | null>(null)
const newDescInput = ref<HTMLInputElement | null>(null)
// 行内可见性状态：key -> boolean（局部 UI 状态，不入 store）
const revealedRows = ref<{ [k: string]: boolean }>({})

// 应用到系统弹层状态
const applyOpen = ref(false)
const applyShellType = ref<ShellType>(detectDefaultShell())
const applyIncludeEmpty = ref(false)
const applyPreviewText = ref('')
const applying = ref(false)
const applyResult = ref<{
  ok: boolean
  applied: Array<{ key: string; value: string }>
  skipped: Array<{ key: string; reason: string }>
  target: string
  note: string
  error?: string
} | null>(null)

// 批量导入弹层状态
const importOpen = ref(false)
const importText = ref('')
const importOverwrite = ref(false)
const importPreview = computed(() => {
  if (!importText.value.trim()) return []
  return keys.parseEnvText(importText.value)
})
const importSkippedPreview = computed(() => {
  const existing = new Set(Object.keys(keys.keysData.mcp || {}))
  return importPreview.value.filter((it: any) => existing.has(it.key))
})
const importNewPreview = computed(() => {
  const existing = new Set(Object.keys(keys.keysData.mcp || {}))
  return importPreview.value.filter((it: any) => !existing.has(it.key))
})
/** 当 overwrite=true 时，已存在的 key 算"将覆盖"而非"跳过" */
const importOverwritePreview = computed(() => {
  if (!importOverwrite.value) return []
  return importSkippedPreview.value
})
/** 真正会被处理的条目数（新增 + 覆盖） */
const importEffectiveCount = computed(() =>
  importOverwrite.value
    ? importNewPreview.value.length + importOverwritePreview.value.length
    : importNewPreview.value.length,
)

function detectDefaultShell(): ShellType {
  // 浏览器无 OS 信息，按平台推断：Windows 默认 powershell，macOS 默认 zsh，其他默认 bash
  const ua = navigator.userAgent || ''
  if (/Windows/i.test(ua)) return 'powershell'
  if (/Macintosh|Mac OS X/i.test(ua)) return 'zsh'
  return 'bash'
}

onMounted(() => {
  keys.loadKeys()
})

async function handleAdd() {
  keys.startAdd()
  await nextTick()
  newKeyInput.value?.focus()
}

async function handleCommitAdd() {
  const ok = await keys.commitAdd()
  if (ok) {
    // 添加成功后自动展开下一个 + 行，方便连续添加
    keys.startAdd()
    await nextTick()
    newKeyInput.value?.focus()
  }
}

function handleCancelAdd() {
  keys.cancelAdd()
}

function handleDelete(key: string) {
  keys.deleteKey(key)
}

function onValueInput(key: string, e: Event) {
  keys.updateValue(key, (e.target as HTMLInputElement).value)
}

function onDescriptionInput(key: string, e: Event) {
  keys.updateDescription(key, (e.target as HTMLInputElement).value)
}

function toggleReveal(key: string) {
  revealedRows.value[key] = !revealedRows.value[key]
}

function copyValue(value: string) {
  if (!value) return
  navigator.clipboard?.writeText(value).then(() => {
    ui.toast('已复制到剪贴板')
  })
}

/**
 * 新建行变量名粘贴：自动解析 key=value 文本。
 * - 多行：弹批量导入弹层
 * - 单行且能解析为 KEY=value：也弹弹层（避免被当作变量名整体填入）
 * - 单行且无法解析（纯变量名）：保持默认粘贴行为
 */
function onNewKeyPaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text') || ''
  if (!text) return
  const lines = text.split(/\r?\n/).filter((l) => l.trim())
  // 多行：直接触发批量导入
  if (lines.length > 1) {
    e.preventDefault()
    importText.value = text
    importOpen.value = true
    return
  }
  // 单行：尝试解析，能解析则触发弹层；不能则保持默认粘贴
  const parsed = keys.parseEnvText(text)
  if (parsed.length > 0) {
    e.preventDefault()
    importText.value = text
    importOpen.value = true
  }
}

function onNewKeyEnter(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    // 变量名已输入 → 直接创建（值/描述留空，可在行内继续编辑）
    if (draft.value.key.trim()) {
      handleCommitAdd()
    } else {
      newValueInput.value?.focus()
    }
  } else if (e.key === 'Escape') {
    handleCancelAdd()
  }
}

// 变量名失焦：若为空则取消，否则保留草稿（不自动提交，用户可继续填值/描述）
function onNewKeyBlur() {
  setTimeout(() => {
    // 检查焦点是否已转到其他新建输入框
    const active = document.activeElement
    if (
      active !== newKeyInput.value &&
      active !== newValueInput.value &&
      active !== newDescInput.value
    ) {
      // 焦点离开了新建行：若变量名为空则取消，否则尝试提交
      if (!draft.value.key.trim()) {
        handleCancelAdd()
      }
    }
  }, 100)
}

function onNewValueEnter(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    newDescInput.value?.focus()
  } else if (e.key === 'Escape') {
    handleCancelAdd()
  }
}

function onNewDescEnter(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    handleCommitAdd()
  } else if (e.key === 'Escape') {
    handleCancelAdd()
  }
}

/** 获取变量引用出处列表 */
function getUsages(key: string): Array<{source: string; scope: string; field: string; kind: string}> {
  return usages.value[key] || []
}

/** 出处摘要：拼接为 "mcp.yaml: Redis, Tavily" 格式 */
function usagesSummary(key: string): string {
  const list = getUsages(key)
  if (!list.length) return ''
  // 按 source 分组，scope 去重
  const bySource: { [k: string]: Set<string> } = {}
  list.forEach((u) => {
    if (!bySource[u.source]) bySource[u.source] = new Set()
    bySource[u.source].add(u.scope)
  })
  return Object.entries(bySource)
    .map(([src, scopes]) => `${src}: ${[...scopes].join(', ')}`)
    .join(' | ')
}

// ===== 应用到系统弹层 =====
function openApply() {
  applyOpen.value = true
  applyResult.value = null
  regenerateApplyPreview()
}

function regenerateApplyPreview() {
  // 仅作为预览展示对应 shell 的写入形式
  applyPreviewText.value = keys.exportShell(applyShellType.value, applyIncludeEmpty.value)
}

async function confirmApply() {
  applying.value = true
  applyResult.value = null
  try {
    const r = await keys.applyToSystem({ includeEmpty: applyIncludeEmpty.value })
    applyResult.value = r
  } finally {
    applying.value = false
  }
}

async function copyApplyPreview() {
  if (!applyPreviewText.value) return
  await navigator.clipboard?.writeText(applyPreviewText.value)
  ui.toast('已复制到剪贴板')
}

function downloadApplyPreview() {
  const ext = applyShellType.value === 'powershell' ? 'ps1' : applyShellType.value === 'zsh' ? 'zsh' : 'sh'
  const filename = `env.${ext}`
  const blob = new Blob([applyPreviewText.value], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ===== 导入弹层 =====
function openImport() {
  importText.value = ''
  importOpen.value = true
}

async function confirmImport() {
  const items = importPreview.value
  if (!items.length) {
    ui.toast('未识别到任何变量', 'err')
    return
  }
  const result = await keys.batchImport(items, { overwrite: importOverwrite.value })
  importOpen.value = false
  importText.value = ''
  importOverwrite.value = false
  // batchImport 内部已 toast，这里无需重复
  void result
}
</script>

<template>
  <div class="keys-page">
    <header class="page-head">
      <div class="head-text">
        <h1>密钥 / 环境变量</h1>
        <p class="text-xs mt-1 mb-0">
          集中管理配置中引用的密钥与环境变量 · 优先取系统环境变量，其次取此处，最后用默认值
        </p>
      </div>
    </header>

    <div class="kpi-row">
      <div class="kpi">
        <b>{{ keyCount }}</b>
        <span>变量总数</span>
        <em>{{ keysPath || 'config/keys.yaml' }}</em>
      </div>
    </div>

    <div class="toolbar">
      <input
        v-model="listQuery"
        type="search"
        class="search-input"
        placeholder="搜索变量名 / 值 / 描述…"
        aria-label="搜索"
      />
      <code v-if="keysPath" class="path-hint">{{ keysPath }}</code>
      <span class="auto-save-hint">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
        自动保存
      </span>
      <div class="toolbar-actions">
        <button type="button" class="btn btn-sm btn-ghost" @click="openImport">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          导入文本
        </button>
        <button type="button" class="btn btn-sm btn-soft" @click="openApply">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 4 21 12 13 12"/></svg>
          应用到系统
        </button>
      </div>
    </div>

    <!-- Excel 风格表格：变量名 / 值 / 描述 / 出处 / 操作 -->
    <div class="table-wrap">
      <table class="keys-table">
        <colgroup>
          <col class="col-name" />
          <col class="col-value" />
          <col class="col-desc" />
          <col class="col-usage" />
          <col class="col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th>变量名</th>
            <th>值</th>
            <th>描述</th>
            <th>出处</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in keyEntries" :key="entry.key" class="data-row">
            <td class="cell-name">
              <code class="key-name" :title="entry.key">{{ entry.key }}</code>
              <span v-if="!entry.value" class="badge badge-warn">未设值</span>
            </td>
            <td class="cell-value">
              <input
                :value="entry.value"
                @input="onValueInput(entry.key, $event)"
                :type="revealedRows[entry.key] ? 'text' : 'password'"
                class="value-input"
                placeholder="请输入值（如 sk-xxx）"
              />
            </td>
            <td class="cell-desc">
              <input
                :value="entry.description"
                @input="onDescriptionInput(entry.key, $event)"
                type="text"
                class="desc-input"
                placeholder="该变量的用途、获取方式…"
              />
            </td>
            <td class="cell-usage">
              <span v-if="getUsages(entry.key).length" class="usage-list" :title="usagesSummary(entry.key)">
                <span
                  v-for="(u, idx) in getUsages(entry.key).slice(0, 3)"
                  :key="idx"
                  class="usage-chip"
                  :class="'kind-' + u.kind"
                >
                  <span class="usage-source">{{ u.source === 'mcp.yaml' ? 'MCP' : 'LLM' }}</span>
                  <span class="usage-scope">{{ u.scope }}</span>
                </span>
                <span v-if="getUsages(entry.key).length > 3" class="usage-more">+{{ getUsages(entry.key).length - 3 }}</span>
              </span>
              <span v-else class="usage-empty" title="未被任何配置引用">未使用</span>
            </td>
            <td class="cell-actions">
              <button
                type="button"
                class="btn btn-icon btn-ghost btn-sm"
                :aria-label="(revealedRows[entry.key] ? '隐藏' : '显示') + '值'"
                :title="(revealedRows[entry.key] ? '隐藏' : '显示') + '值'"
                @click="toggleReveal(entry.key)"
              >
                <svg v-if="revealedRows[entry.key]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-10-8-10-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
              <button
                type="button"
                class="btn btn-icon btn-ghost btn-sm"
                aria-label="复制值"
                title="复制值"
                @click="copyValue(entry.value)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              </button>
              <button
                type="button"
                class="btn btn-danger btn-icon btn-sm"
                :aria-label="'删除 ' + entry.key"
                :title="'删除 ' + entry.key"
                @click="handleDelete(entry.key)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>
              </button>
            </td>
          </tr>

          <!-- 永久 + 行：点击进入新建模式 -->
          <tr v-if="!isAdding" class="add-row" @click="handleAdd" tabindex="0" @keydown.enter.prevent="handleAdd">
            <td colspan="5" class="add-placeholder">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
              <span>添加变量…</span>
            </td>
          </tr>

          <!-- 新建行（底部 + 行点击后展开） -->
          <tr v-if="isAdding" class="draft-row">
            <td class="cell-name">
              <input
                ref="newKeyInput"
                v-model="draft.key"
                type="text"
                class="key-name-input"
                placeholder="变量名（如 TAVILY_API_KEY），粘贴多行可批量解析"
                @keydown="onNewKeyEnter"
                @blur="onNewKeyBlur"
                @paste="onNewKeyPaste"
              />
            </td>
            <td class="cell-value">
              <input
                ref="newValueInput"
                v-model="draft.value"
                type="password"
                class="value-input"
                placeholder="值（如 sk-xxx）"
                @keydown="onNewValueEnter"
              />
            </td>
            <td class="cell-desc">
              <input
                ref="newDescInput"
                v-model="draft.description"
                type="text"
                class="desc-input"
                placeholder="描述（可选）"
                @keydown="onNewDescEnter"
              />
            </td>
            <td class="cell-usage">
              <span class="usage-empty">新变量</span>
            </td>
            <td class="cell-actions">
              <button
                type="button"
                class="btn btn-icon btn-primary btn-sm"
                aria-label="确认创建"
                title="确认创建"
                @click="handleCommitAdd"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              </button>
              <button
                type="button"
                class="btn btn-icon btn-danger btn-sm"
                aria-label="取消创建"
                title="取消创建"
                @click="handleCancelAdd"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </td>
          </tr>
          <tr v-if="isAdding && draft.error">
            <td colspan="5" class="draft-error">{{ draft.error }}</td>
          </tr>

          <tr v-if="!keyCount && !isAdding">
            <td colspan="5" class="m-empty">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3"/></svg>
              <p>暂无变量，点击上方「+ 添加变量…」开始。</p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 应用到系统弹层 -->
    <Teleport to="body">
      <Transition name="export-modal">
        <div v-if="applyOpen" class="modal-mask" @click.self="!applying && (applyOpen = false)">
          <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="apply-title">
            <header class="modal-head">
              <h3 id="apply-title">应用到系统</h3>
              <button type="button" class="btn btn-icon btn-ghost btn-sm" aria-label="关闭" :disabled="applying" @click="applyOpen = false">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </header>
            <div class="modal-body">
              <p class="apply-intro">
                把所有密钥/环境变量写入操作系统，让其在终端、IDE 等任意新进程中立即可读。
                <span class="text-ink-400">Windows 写入用户级注册表；macOS/Linux 追加到对应 rc 文件。</span>
              </p>
              <div class="shell-tabs">
                <label class="shell-tab" :class="{ active: applyShellType === 'powershell' }">
                  <input type="radio" v-model="applyShellType" value="powershell" @change="regenerateApplyPreview" />
                  <span>PowerShell</span>
                  <em>Windows</em>
                </label>
                <label class="shell-tab" :class="{ active: applyShellType === 'zsh' }">
                  <input type="radio" v-model="applyShellType" value="zsh" @change="regenerateApplyPreview" />
                  <span>zsh</span>
                  <em>macOS</em>
                </label>
                <label class="shell-tab" :class="{ active: applyShellType === 'bash' }">
                  <input type="radio" v-model="applyShellType" value="bash" @change="regenerateApplyPreview" />
                  <span>bash</span>
                  <em>Linux</em>
                </label>
              </div>
              <label class="opt-row">
                <input type="checkbox" v-model="applyIncludeEmpty" @change="regenerateApplyPreview" />
                <span>包含未设值的变量</span>
              </label>
              <details class="preview-details">
                <summary>预览将要写入的脚本</summary>
                <textarea
                  class="export-textarea"
                  :value="applyPreviewText"
                  readonly
                  rows="10"
                  spellcheck="false"
                  aria-label="预览脚本"
                ></textarea>
                <div class="preview-actions">
                  <button type="button" class="btn btn-sm btn-ghost" @click="copyApplyPreview">复制脚本</button>
                  <button type="button" class="btn btn-sm btn-ghost" @click="downloadApplyPreview">下载文件</button>
                </div>
              </details>

              <!-- 应用结果 -->
              <div v-if="applyResult" class="apply-result" :class="{ ok: applyResult.ok, err: !applyResult.ok }">
                <div v-if="!applyResult.ok" class="result-row err">
                  <strong>应用失败：</strong>
                  <span>{{ applyResult.error }}</span>
                </div>
                <div v-else>
                  <div class="result-row ok">
                    <strong>已应用 {{ applyResult.applied.length }} 个变量</strong>
                    <span class="target">{{ applyResult.target }}</span>
                  </div>
                  <p v-if="applyResult.note" class="result-note">{{ applyResult.note }}</p>
                  <div v-if="applyResult.applied.length" class="result-list">
                    <div v-for="it in applyResult.applied" :key="it.key" class="result-item">
                      <code>{{ it.key }}</code>
                      <span class="eq">=</span>
                      <code class="val">{{ it.value }}</code>
                    </div>
                  </div>
                  <div v-if="applyResult.skipped.length" class="skipped-box">
                    <span class="badge badge-warn">跳过 {{ applyResult.skipped.length }}</span>
                    <ul>
                      <li v-for="s in applyResult.skipped" :key="s.key">
                        <code>{{ s.key }}</code> — {{ s.reason }}
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
            <footer class="modal-foot">
              <span class="foot-hint">{{ applyPreviewText.split('\n').filter(l => l && !l.startsWith('#') && !l.startsWith('!')).length }} 个变量</span>
              <div class="foot-actions">
                <button type="button" class="btn btn-sm btn-ghost" :disabled="applying" @click="applyOpen = false">关闭</button>
                <button type="button" class="btn btn-sm btn-primary" :disabled="applying || !!applyResult?.ok" @click="confirmApply">
                  <svg v-if="applying" class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-3-6.7"/></svg>
                  {{ applying ? '应用中…' : applyResult?.ok ? '已应用' : '立即应用到系统' }}
                </button>
              </div>
            </footer>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 批量导入弹层 -->
    <Teleport to="body">
      <Transition name="export-modal">
        <div v-if="importOpen" class="modal-mask" @click.self="importOpen = false">
          <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="import-title">
            <header class="modal-head">
              <h3 id="import-title">批量导入变量</h3>
              <button type="button" class="btn btn-icon btn-ghost btn-sm" aria-label="关闭" @click="importOpen = false">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </header>
            <div class="modal-body">
              <p class="import-hint">
                粘贴 <code>KEY=value</code> / <code>export KEY=value</code> / <code>$env:KEY = "value"</code> / <code>set KEY=value</code> / <code>"KEY": "value"</code>（JSON 风，含尾逗号）/ 完整 JSON 对象 <code>{"K":"v",...}</code>，自动解析为 key/value。
              </p>
              <textarea
                v-model="importText"
                class="import-textarea"
                rows="10"
                spellcheck="false"
                placeholder="TAVILY_API_KEY=tvly-xxx&#10;export OPENAI_API_KEY=sk-xxx&#10;$env:GITHUB_TOKEN = &quot;ghp_xxx&quot;&#10;# 注释会被跳过"
                aria-label="待导入文本"
              ></textarea>
              <div v-if="importPreview.length" class="preview-box">
                <div class="preview-row">
                  <span class="badge badge-ok">新增 {{ importNewPreview.length }}</span>
                  <span v-if="importSkippedPreview.length && !importOverwrite" class="badge badge-warn">跳过（已存在）{{ importSkippedPreview.length }}</span>
                  <span v-if="importSkippedPreview.length && importOverwrite" class="badge badge-warn">覆盖 {{ importSkippedPreview.length }}</span>
                </div>
                <ul class="preview-list">
                  <li v-for="(it, idx) in importPreview" :key="idx" :class="{ skipped: importSkippedPreview.includes(it) && !importOverwrite }">
                    <code>{{ it.key }}</code>
                    <span class="eq">=</span>
                    <code class="val">{{ it.value }}</code>
                    <em v-if="importSkippedPreview.includes(it) && !importOverwrite">已存在</em>
                    <em v-else-if="importSkippedPreview.includes(it) && importOverwrite" class="will-overwrite">将覆盖</em>
                  </li>
                </ul>
              </div>
              <label v-if="importSkippedPreview.length" class="opt-row overwrite-opt">
                <input type="checkbox" v-model="importOverwrite" />
                <span>覆盖已存在的变量（共 {{ importSkippedPreview.length }} 个）</span>
              </label>
            </div>
            <footer class="modal-foot">
              <span class="foot-hint">{{ importPreview.length }} 条识别</span>
              <div class="foot-actions">
                <button type="button" class="btn btn-sm btn-ghost" @click="importOpen = false">取消</button>
                <button type="button" class="btn btn-sm btn-primary" :disabled="!importEffectiveCount" @click="confirmImport">
                  导入 {{ importEffectiveCount }} 条
                </button>
              </div>
            </footer>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.keys-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.head-text h1 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.head-text p {
  color: var(--text-secondary);
  line-height: 1.5;
}
.head-text code {
  background: var(--bg-elevated);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--brand-600, #2563eb);
  border: 1px solid var(--border-base);
}

.kpi-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.kpi {
  background: var(--bg-elevated);
  border-radius: 10px;
  padding: 12px 16px;
  border: 1px solid var(--border-base);
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 200px;
}
.kpi b {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
}
.kpi span {
  font-size: 12px;
  color: var(--text-secondary);
}
.kpi em {
  font-size: 10px;
  color: var(--text-tertiary);
  font-style: normal;
  margin-top: 4px;
  word-break: break-all;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
}
.btn-primary {
  background: var(--brand-500, #165dff);
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  background: var(--brand-600, #0e42d2);
}
.btn-soft {
  background: var(--primary-container, rgba(22, 93, 255, 0.08));
  color: var(--brand-600, #0e42d2);
  border-color: var(--primary-container-strong, rgba(22, 93, 255, 0.16));
}
.btn-soft:hover:not(:disabled) {
  background: rgba(22, 93, 255, 0.16);
}
.search-input {
  flex: 1;
  min-width: 200px;
  max-width: 400px;
  padding: 6px 12px;
  border: 1px solid var(--border-base);
  border-radius: 8px;
  font-size: 13px;
  background: var(--bg-elevated);
  color: var(--text-primary);
}
.search-input:focus {
  outline: none;
  border-color: var(--brand-500, #3b82f6);
}
.path-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-elevated);
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-base);
}
.auto-save-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-tertiary);
  margin-left: auto;
}
.auto-save-hint svg {
  width: 12px;
  height: 12px;
  color: #10b981;
}

/* 表格容器 */
.table-wrap {
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 10px;
  overflow: hidden;
}
.keys-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  table-layout: fixed;
}
.keys-table thead th {
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
  background: var(--bg-base);
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-base);
}
.col-name { width: 18%; }
.col-value { width: 28%; }
.col-desc { width: 24%; }
.col-usage { width: 20%; }
.col-actions { width: 10%; }

.keys-table tbody tr {
  border-bottom: 1px solid var(--border-base);
  transition: background 0.12s;
}
.keys-table tbody tr:last-child {
  border-bottom: none;
}
.keys-table tbody tr.data-row:hover {
  background: rgba(59, 130, 246, 0.04);
}

.keys-table td {
  padding: 6px 12px;
  vertical-align: middle;
}

/* 变量名列 */
.cell-name {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.key-name {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px;
  color: var(--brand-600, #2563eb);
  background: rgba(59, 130, 246, 0.08);
  padding: 3px 8px;
  border-radius: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.key-name-input {
  width: 100%;
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px;
  padding: 5px 8px;
  border-radius: 4px;
  background: var(--bg-base);
  border: 1px solid var(--brand-500, #3b82f6);
  color: var(--brand-600, #2563eb);
}
.key-name-input:focus {
  outline: none;
}

/* 值列 */
.cell-value {
  padding: 4px 8px;
}
.value-input {
  width: 100%;
  padding: 5px 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  font-size: 13px;
  font-family: 'SF Mono', 'Consolas', monospace;
  background: transparent;
  color: var(--text-primary);
}
.value-input:hover {
  border-color: var(--border-base);
  background: var(--bg-base);
}
.value-input:focus {
  outline: none;
  border-color: var(--brand-500, #3b82f6);
  background: var(--bg-base);
}

/* 描述列 */
.cell-desc {
  padding: 4px 8px;
}
.desc-input {
  width: 100%;
  padding: 5px 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  font-size: 13px;
  background: transparent;
  color: var(--text-primary);
}
.desc-input:hover {
  border-color: var(--border-base);
  background: var(--bg-base);
}
.desc-input:focus {
  outline: none;
  border-color: var(--brand-500, #3b82f6);
  background: var(--bg-base);
}
.desc-input::placeholder {
  color: var(--text-tertiary);
  opacity: 0.7;
}

/* 操作列 */
.cell-actions {
  display: flex;
  gap: 2px;
  justify-content: flex-end;
  align-items: center;
}

/* 按钮基础样式（KeysView scoped，避免依赖其他 view 的 scoped 样式） */
.btn {
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  white-space: nowrap;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background .18s ease, color .18s ease, border-color .18s ease;
  background: none;
  color: inherit;
  user-select: none;
}
.btn svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.btn:disabled {
  opacity: .45;
  cursor: not-allowed;
}
.btn-sm {
  height: 28px;
  padding: 0 10px;
  font-size: 11px;
  border-radius: 7px;
}
.btn-sm svg {
  width: 13px;
  height: 13px;
}
.btn-icon {
  width: 32px;
  padding: 0;
}
.btn-icon.btn-sm {
  width: 28px;
}
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
}
.btn-ghost:hover:not(:disabled) {
  background: var(--bg-base);
  color: var(--text-primary);
}
.btn-danger {
  background: transparent;
  color: var(--text-tertiary);
}
.btn-danger:hover:not(:disabled),
.btn-danger:focus-visible {
  background: rgba(220, 38, 38, 0.08);
  color: #dc2626;
  border-color: rgba(220, 38, 38, 0.2);
}

/* 出处列 */
.cell-usage {
  padding: 4px 8px;
}
.usage-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.usage-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  background: rgba(59, 130, 246, 0.08);
  color: var(--brand-600, #2563eb);
  border: 1px solid rgba(59, 130, 246, 0.2);
  max-width: 100%;
  overflow: hidden;
}
.usage-chip.kind-plaintext {
  background: rgba(16, 185, 129, 0.08);
  color: #059669;
  border-color: rgba(16, 185, 129, 0.2);
}
.usage-source {
  font-weight: 600;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  opacity: 0.8;
}
.usage-scope {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100px;
}
.usage-more {
  font-size: 11px;
  color: var(--text-tertiary);
  padding: 2px 4px;
}
.usage-empty {
  font-size: 11px;
  color: var(--text-tertiary);
  font-style: italic;
  opacity: 0.7;
}

/* 徽章 */
.badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
  white-space: nowrap;
}
.badge-warn {
  color: #d97706;
  background: rgba(245, 158, 11, 0.12);
}
.badge-ok {
  color: #059669;
  background: rgba(16, 185, 129, 0.12);
}

/* + 行 */
.add-row {
  cursor: pointer;
  outline: none;
}
.add-row:hover,
.add-row:focus-visible {
  background: rgba(59, 130, 246, 0.04);
}
.add-placeholder {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px !important;
  color: var(--text-tertiary);
  font-size: 13px;
  font-weight: 500;
}
.add-row:hover .add-placeholder,
.add-row:focus-visible .add-placeholder {
  color: var(--brand-600, #2563eb);
}
.add-placeholder svg {
  width: 14px;
  height: 14px;
}

/* 草稿行 */
.draft-row {
  background: rgba(59, 130, 246, 0.06) !important;
}
.draft-row td {
  border-top: 1px dashed var(--brand-500, #3b82f6);
  border-bottom: 1px dashed var(--brand-500, #3b82f6);
}
.draft-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
}
.draft-error {
  color: #ef4444;
  font-size: 12px;
  padding: 6px 12px !important;
  background: rgba(239, 68, 68, 0.05);
}

/* 空状态 */
.m-empty {
  text-align: center;
  padding: 32px 12px !important;
  color: var(--text-tertiary);
}
.m-empty svg {
  width: 32px;
  height: 32px;
  margin: 0 auto 8px;
  display: block;
  opacity: 0.5;
}
.m-empty p {
  margin: 0;
  font-size: 13px;
}

/* 响应式：窄屏改为横向滚动 */
@media (max-width: 720px) {
  .table-wrap {
    overflow-x: auto;
  }
  .keys-table {
    min-width: 600px;
  }
}

/* ===== 弹层（导出/导入） ===== */
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(15, 20, 30, 0.48);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.modal-panel {
  width: 100%;
  max-width: 680px;
  max-height: 90vh;
  background: var(--bg-elevated, #fff);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15, 20, 30, 0.22);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-base, #e5e6eb);
}
.modal-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #1f2329);
}
.modal-body {
  padding: 16px 18px;
  overflow-y: auto;
  flex: 1;
}
.modal-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  border-top: 1px solid var(--border-base, #e5e6eb);
  background: var(--bg-base, #f7f8fa);
}
.foot-hint {
  font-size: 11px;
  color: var(--text-tertiary, #86909c);
}
.foot-actions {
  display: flex;
  gap: 8px;
}

/* Shell 选项卡 */
.shell-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.shell-tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 8px;
  border: 1px solid var(--border-base, #e5e6eb);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--bg-base, #f7f8fa);
  position: relative;
}
.shell-tab input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.shell-tab span {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #4e5969);
}
.shell-tab em {
  font-size: 10px;
  font-style: normal;
  color: var(--text-tertiary, #86909c);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.shell-tab:hover {
  border-color: var(--brand-500, #165dff);
}
.shell-tab.active {
  border-color: var(--brand-500, #165dff);
  background: var(--primary-container, rgba(22, 93, 255, 0.08));
}
.shell-tab.active span {
  color: var(--brand-600, #0e42d2);
}

.opt-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary, #4e5969);
  margin-bottom: 10px;
  cursor: pointer;
}
.opt-row input {
  cursor: pointer;
}

.overwrite-opt {
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px dashed var(--border-base, #e5e6eb);
  border-radius: 6px;
  background: var(--bg-base, #f7f8fa);
}
.overwrite-opt input:checked + span {
  color: var(--brand-600, #0e42d2);
  font-weight: 600;
}

.will-overwrite {
  color: #d97706 !important;
  background: rgba(245, 158, 11, 0.12) !important;
  padding: 0 6px !important;
  border-radius: 3px !important;
  font-style: normal !important;
  font-size: 10px !important;
}

.export-textarea,
.import-textarea {
  width: 100%;
  font-family: 'SF Mono', 'Consolas', 'Menlo', monospace;
  font-size: 12px;
  line-height: 1.5;
  padding: 10px 12px;
  border: 1px solid var(--border-base, #e5e6eb);
  border-radius: 8px;
  background: var(--bg-base, #f7f8fa);
  color: var(--text-primary, #1f2329);
  resize: vertical;
  min-height: 200px;
}
.export-textarea {
  background: var(--bg-sunken, #f2f3f5);
  color: var(--text-secondary, #4e5969);
}
.export-textarea:focus,
.import-textarea:focus {
  outline: none;
  border-color: var(--brand-500, #165dff);
  background: var(--bg-elevated, #fff);
}

.import-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text-secondary, #4e5969);
  line-height: 1.6;
}
.import-hint code {
  background: var(--bg-base, #f7f8fa);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 11px;
  color: var(--brand-600, #0e42d2);
}

/* 应用到系统弹层专属 */
.apply-intro {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--text-secondary, #4e5969);
  line-height: 1.6;
}
.apply-intro .text-ink-400 {
  color: var(--text-tertiary, #86909c);
  display: block;
  margin-top: 2px;
}
.preview-details {
  margin-top: 10px;
  border: 1px solid var(--border-base, #e5e6eb);
  border-radius: 8px;
  background: var(--bg-base, #f7f8fa);
  padding: 8px 10px;
}
.preview-details summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #4e5969);
  user-select: none;
  margin-bottom: 6px;
}
.preview-details[open] summary {
  margin-bottom: 8px;
}
.preview-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  justify-content: flex-end;
}

.apply-result {
  margin-top: 12px;
  border-radius: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border-base, #e5e6eb);
}
.apply-result.ok {
  border-color: rgba(5, 150, 105, 0.3);
  background: rgba(5, 150, 105, 0.06);
}
.apply-result.err {
  border-color: rgba(220, 38, 38, 0.3);
  background: rgba(220, 38, 38, 0.06);
}
.result-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  flex-wrap: wrap;
}
.result-row.ok strong {
  color: #059669;
}
.result-row.err strong {
  color: #dc2626;
}
.result-row .target {
  font-size: 11px;
  color: var(--text-tertiary, #86909c);
  font-family: 'SF Mono', 'Consolas', monospace;
}
.result-note {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--text-secondary, #4e5969);
  line-height: 1.5;
}
.result-list {
  margin-top: 8px;
  max-height: 160px;
  overflow-y: auto;
}
.result-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: 11px;
  border-bottom: 1px solid var(--border-subtle, #f2f3f5);
}
.result-item:last-child {
  border-bottom: none;
}
.result-item code {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 11px;
  color: var(--brand-600, #0e42d2);
  background: rgba(22, 93, 255, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.result-item code.val {
  color: var(--text-secondary, #4e5969);
  background: var(--bg-elevated, #fff);
  flex: 1;
  max-width: 300px;
}
.result-item .eq {
  color: var(--text-tertiary, #86909c);
}
.skipped-box {
  margin-top: 8px;
  font-size: 11px;
}
.skipped-box ul {
  margin: 4px 0 0;
  padding-left: 16px;
  color: var(--text-secondary, #4e5969);
}
.skipped-box li code {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 10px;
  color: #d97706;
  background: rgba(245, 158, 11, 0.08);
  padding: 0 4px;
  border-radius: 3px;
}

.spin {
  animation: spin 0.8s linear infinite;
  width: 13px;
  height: 13px;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.preview-box {
  margin-top: 12px;
  border: 1px solid var(--border-base, #e5e6eb);
  border-radius: 8px;
  background: var(--bg-base, #f7f8fa);
  padding: 10px 12px;
}
.preview-row {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 11px;
}
.preview-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 200px;
  overflow-y: auto;
}
.preview-list li {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 12px;
  border-bottom: 1px solid var(--border-subtle, #f2f3f5);
}
.preview-list li:last-child {
  border-bottom: none;
}
.preview-list li.skipped {
  opacity: 0.55;
}
.preview-list code {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 11px;
  color: var(--brand-600, #0e42d2);
  background: rgba(22, 93, 255, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-list code.val {
  color: var(--text-secondary, #4e5969);
  background: var(--bg-elevated, #fff);
  flex: 1;
  max-width: 300px;
}
.preview-list .eq {
  color: var(--text-tertiary, #86909c);
  font-size: 11px;
}
.preview-list em {
  font-size: 10px;
  font-style: normal;
  color: #d97706;
  margin-left: auto;
}

/* 弹层过渡动画 */
.export-modal-enter-active,
.export-modal-leave-active {
  transition: opacity 0.18s ease;
}
.export-modal-enter-active > .modal-panel,
.export-modal-leave-active > .modal-panel {
  transition: transform 0.18s ease;
}
.export-modal-enter-from,
.export-modal-leave-to {
  opacity: 0;
}
.export-modal-enter-from > .modal-panel,
.export-modal-leave-to > .modal-panel {
  transform: translateY(8px) scale(0.98);
}
@media (prefers-reduced-motion: reduce) {
  .export-modal-enter-active,
  .export-modal-leave-active,
  .export-modal-enter-active > .modal-panel,
  .export-modal-leave-active > .modal-panel {
    transition: none;
  }
}
</style>
