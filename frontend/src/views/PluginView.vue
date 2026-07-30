<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { usePluginStore } from '../stores/plugin'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'
import { api } from '../api/client'

const emit = defineEmits<{ 'go-tab': [key: string] }>()

const plugin = usePluginStore()
const ui = useUiStore()
const auth = useAuthStore()
const { plugins, installingPlugin, selectedForExport } = storeToRefs(plugin)
const {
  refreshPluginList, exportPlugin, onImportPluginFile, importPluginFile,
  onTogglePlugin, editPlugin, deletePlugin, toggleSelectForExport, selectFilesForExport,
  clearExportSelection, exportSelectedPlugins, publishToMarketplace,
} = plugin

const inputRef = ref<HTMLInputElement | null>(null)
const listQuery = ref('')
const listFilter = ref<'all' | 'on' | 'off'>('all')
const exportMenu = ref<string | null>(null)
const dragging = ref(false)
const dragCounter = ref(0)

// ===== 导入弹层 =====
const importOpen = ref(false)
const importDragOver = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)

// ===== 发布弹窗 =====
interface TeamSpace { id: number; name: string; role: string }
const publishDialogOpen = ref(false)
const publishFile = ref('')
const publishScope = ref<'public' | 'team'>('public')
const publishTeamId = ref<number | null>(null)
const teamSpaces = ref<TeamSpace[]>([])

async function loadTeams() {
  if (!auth.isLoggedIn) return
  try {
    const r = await api('/api/teams')
    if (r.ok) teamSpaces.value = r.data || []
  } catch { /* ignore */ }
}

function openPublishDialog(file: string) {
  publishFile.value = file
  publishScope.value = 'public'
  publishTeamId.value = null
  publishDialogOpen.value = true
  if (auth.isLoggedIn) loadTeams()
}

async function doPublish() {
  publishDialogOpen.value = false
  await publishToMarketplace(publishFile.value, publishScope.value, publishTeamId.value || undefined)
}

// ===== 视图切换：列表（默认）/ 图标 =====
type ViewMode = 'list' | 'grid'
const viewMode = ref<ViewMode>('list')

// ===== 排序 =====
type SortBy = 'name' | 'description' | 'skills' | 'mcp' | 'status'
type SortDir = 'asc' | 'desc'
const sortBy = ref<SortBy>('name')
const sortDir = ref<SortDir>('asc')

function setSort(by: SortBy) {
  if (sortBy.value === by) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
    return
  }
  sortBy.value = by
  // 默认方向：name/description 升序，skills/mcp/status 降序
  sortDir.value = (by === 'skills' || by === 'mcp' || by === 'status') ? 'desc' : 'asc'
}

const installedCount = computed(() => plugins.value.filter((p) => p.installed).length)
const uninstalledCount = computed(() => plugins.value.length - installedCount.value)
const skillsTotal = computed(() => plugins.value.reduce((a, p) => a + (p.skills_count || 0), 0))

const filteredPlugins = computed(() => {
  const q = listQuery.value.trim().toLowerCase()
  return plugins.value.filter((p) => {
    if (listFilter.value === 'on' && !p.installed) return false
    if (listFilter.value === 'off' && p.installed) return false
    if (!q) return true
    return p.name.toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q)
  })
})

const sortedPlugins = computed(() => {
  const list = filteredPlugins.value.slice()
  const by = sortBy.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  const coll = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true })
  list.sort((a, b) => {
    let cmp = 0
    if (by === 'name') {
      cmp = coll.compare(a.name || '', b.name || '')
    } else if (by === 'description') {
      cmp = coll.compare(a.description || '', b.description || '')
      if ((a.description || '') !== (b.description || '')) {
        if (!a.description) return 1
        if (!b.description) return -1
      }
    } else if (by === 'skills') {
      cmp = (a.skills_count || 0) - (b.skills_count || 0)
    } else if (by === 'mcp') {
      cmp = (a.mcp_count || 0) - (b.mcp_count || 0)
    } else if (by === 'status') {
      // 已安装 (true) 排前
      cmp = (a.installed === b.installed) ? 0 : (a.installed ? -1 : 1)
    }
    if (cmp === 0) cmp = coll.compare(a.name || '', b.name || '')
    return cmp * dir
  })
  return list
})

// ===== 选中状态（仿 MCP/Skills） =====
const allFilteredSelected = computed(() =>
  sortedPlugins.value.length > 0 && sortedPlugins.value.every((p) => selectedForExport.value.has(p.file)),
)
const selectedCount = computed(() => selectedForExport.value.size)
function toggleSelectAll() {
  if (allFilteredSelected.value) {
    // 取消当前筛选列表的全选
    const s = new Set(selectedForExport.value)
    sortedPlugins.value.forEach((p) => s.delete(p.file))
    selectedForExport.value = s
  } else {
    const s = new Set(selectedForExport.value)
    sortedPlugins.value.forEach((p) => s.add(p.file))
    selectedForExport.value = s
  }
}
function selectVisible() {
  selectFilesForExport(sortedPlugins.value.map((p) => p.file))
}

function triggerImport() { importOpen.value = true }
function closeImport() { importOpen.value = false }
function onImportFileClick() { importFileInput.value?.click() }
function onImportFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) doImportFile(file)
  input.value = ''
}
async function onImportDrop(e: DragEvent) {
  e.preventDefault()
  importDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) doImportFile(file)
}
async function doImportFile(file: File) {
  const ok = /\.(ya?ml|zip)$/i.test(file.name)
  if (!ok) {
    ui.toast('仅支持 .zip / .yaml / .yml', 'warn')
    return
  }
  importOpen.value = false
  await importPluginFile(file)
}

// ===== 导出选项弹窗 =====
type KeyMode = 'plain' | 'vault' | 'redacted'
type ExportTarget =
  | { kind: 'batch' }
  | { kind: 'single'; file: string; format: 'zip' | 'yaml' }
const exportDialog = ref(false)
const exportKeyMode = ref<KeyMode>('vault')
const exportTarget = ref<ExportTarget | null>(null)
// 导出内容选择（默认全选）
const EXTRA_OPTIONS = [
  { key: 'skills', label: 'Skills', desc: '技能目录' },
  { key: 'llm', label: 'llm.yaml', desc: 'LLM 配置' },
  { key: 'mcp', label: 'mcp.yaml', desc: 'MCP 服务配置' },
  { key: 'keys', label: 'keys.yaml', desc: '密钥库' },
  { key: 'subagents', label: 'subagents.yaml', desc: '子代理' },
  { key: 'rules', label: 'rules', desc: '规则文件' },
  { key: 'commands', label: 'commands.yaml', desc: '斜杠命令' },
  { key: 'hooks', label: 'hooks.json', desc: '钩子' },
] as const
const exportExtras = ref<string[]>(['skills', 'llm', 'mcp', 'keys', 'subagents', 'rules', 'commands', 'hooks'])

function toggleExtra(key: string) {
  const i = exportExtras.value.indexOf(key)
  if (i >= 0) exportExtras.value.splice(i, 1)
  else exportExtras.value.push(key)
}

function openExportBatch() {
  if (!selectedForExport.value.size) {
    ui.toast('请先勾选要导出的插件', 'warn')
    return
  }
  exportTarget.value = { kind: 'batch' }
  exportKeyMode.value = 'vault'
  exportExtras.value = [...EXTRA_OPTIONS.map(o => o.key)]
  exportDialog.value = true
}

function openExportSingle(file: string, format: 'zip' | 'yaml') {
  exportMenu.value = null
  if (format === 'yaml') {
    // yaml 仅导出 plugin.yaml，不涉及密钥，直接下载
    exportPlugin(file, format, 'plain')
    return
  }
  exportTarget.value = { kind: 'single', file, format }
  exportKeyMode.value = 'vault'
  exportExtras.value = [...EXTRA_OPTIONS.map(o => o.key)]
  exportDialog.value = true
}

function cancelExport() {
  exportDialog.value = false
  exportTarget.value = null
}

async function confirmExport() {
  if (!exportTarget.value) return
  const mode = exportKeyMode.value
  const target = exportTarget.value
  const extras = [...exportExtras.value]
  exportDialog.value = false
  exportTarget.value = null
  if (target.kind === 'batch') {
    await exportSelectedPlugins(mode, extras)
  } else {
    exportPlugin(target.file, target.format, mode, extras)
  }
}

function onExportBatch() {
  openExportBatch()
}

async function batchInstall() {
  const targets = sortedPlugins.value.filter((p) => !p.installed && selectedForExport.value.has(p.file))
  if (!targets.length) {
    ui.toast('所选插件均已安装', 'warn')
    return
  }
  for (const p of targets) {
    await onTogglePlugin(p, true)
  }
  clearExportSelection()
}

async function batchUninstall() {
  const targets = sortedPlugins.value.filter((p) => p.installed && selectedForExport.value.has(p.file))
  if (!targets.length) {
    ui.toast('所选插件均未安装', 'warn')
    return
  }
  if (!confirm(`确认卸载 ${targets.length} 个插件？`)) return
  for (const p of targets) {
    await onTogglePlugin(p, false)
  }
  clearExportSelection()
}

function goBuild() {
  emit('go-tab', 'plugin-build')
}

function onEdit(file: string) {
  editPlugin(file)
  emit('go-tab', 'plugin-build')
}

function toggleExportMenu(file: string) {
  exportMenu.value = exportMenu.value === file ? null : file
}

function doExport(file: string, format: 'zip' | 'yaml') {
  openExportSingle(file, format)
}

function onDocClick(e: MouseEvent) {
  const t = e.target as HTMLElement
  if (!t.closest('.export-menu')) exportMenu.value = null
}

function onDragEnter(e: DragEvent) {
  if (!e.dataTransfer?.types?.includes('Files')) return
  e.preventDefault()
  dragCounter.value++
  dragging.value = true
}
function onDragOver(e: DragEvent) {
  if (!e.dataTransfer?.types?.includes('Files')) return
  e.preventDefault()
}
function onDragLeave(e: DragEvent) {
  e.preventDefault()
  dragCounter.value = Math.max(0, dragCounter.value - 1)
  if (dragCounter.value === 0) dragging.value = false
}
async function onDrop(e: DragEvent) {
  e.preventDefault()
  dragCounter.value = 0
  dragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (!f) return
  const ok = /\.(ya?ml|zip)$/i.test(f.name)
  if (!ok) {
    ui.toast('仅支持 .zip / .yaml / .yml', 'warn')
    return
  }
  await importPluginFile(f)
}

onMounted(() => {
  refreshPluginList()
  document.addEventListener('click', onDocClick)
})
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div
    class="plugin-page"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div class="plugin-head flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0">
        <h1 class="text-[15px] font-semibold text-ink-900 m-0">插件管理</h1>
        <p class="text-xs text-ink-500 mt-1 mb-0">集中管理本地智能体插件 · 一键安装 / 导入导出 / 分享到市场 · 打包 LLM+MCP+Skills+Keys 为可分发单元</p>
      </div>
      <div class="btn-cluster">
        <button type="button" class="btn btn-secondary" @click="refreshPluginList">刷新</button>
        <button type="button" class="btn btn-secondary" @click="triggerImport">导入</button>
        <button
          type="button"
          class="btn btn-secondary"
          :disabled="!plugins.length"
          @click="onExportBatch"
        >导出<span v-if="selectedCount" class="btn-badge">{{ selectedCount }}</span></button>
        <button type="button" class="btn btn-primary" @click="goBuild">构建插件</button>
        <input ref="inputRef" type="file" accept=".yaml,.yml,.zip" class="hidden" @change="onImportPluginFile">
      </div>
    </div>

    <div class="kpis">
      <div class="kpi brand"><b>{{ plugins.length }}</b><span>插件总数</span><em>本地可用</em></div>
      <div class="kpi live"><b>{{ installedCount }}</b><span>已安装</span><em>已写入配置</em></div>
      <div class="kpi"><b>{{ skillsTotal }}</b><span>Skills 合计</span><em>所有插件汇总</em></div>
      <div class="kpi warn"><b>{{ uninstalledCount }}</b><span>未安装</span><em>可一键安装</em></div>
    </div>

    <section class="panel">
      <div class="toolbar">
        <div class="toolbar-left">
          <label class="search">
            <input v-model="listQuery" type="search" placeholder="筛选名称 / 描述" />
          </label>
          <div class="seg" role="group" aria-label="安装状态">
            <button type="button" :class="{ on: listFilter === 'all' }" @click="listFilter = 'all'">全部</button>
            <button type="button" :class="{ on: listFilter === 'on' }" @click="listFilter = 'on'">已安装</button>
            <button type="button" :class="{ on: listFilter === 'off' }" @click="listFilter = 'off'">未安装</button>
          </div>
        </div>
        <div class="btn-cluster">
          <div class="seg view-toggle" role="group" aria-label="视图切换">
            <button type="button" :class="{ on: viewMode === 'list' }" @click="viewMode = 'list'" title="列表视图">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18M3 12h18M3 19h18"/></svg>
            </button>
            <button type="button" :class="{ on: viewMode === 'grid' }" @click="viewMode = 'grid'" title="图标视图">
              <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
            </button>
          </div>
          <div class="btn-pair" role="group" aria-label="批量选择">
            <button type="button" class="btn btn-ghost btn-sm" @click="selectVisible">全选可见</button>
            <button type="button" class="btn btn-ghost btn-sm" @click="clearExportSelection">清空</button>
          </div>
        </div>
      </div>

      <Transition name="fade-slide">
        <div v-if="selectedCount" class="batch-bar" role="toolbar" aria-label="批量操作">
          <span class="batch-count">已选 {{ selectedCount }} 个</span>
          <button type="button" class="btn btn-soft btn-sm" @click="batchInstall">安装</button>
          <button type="button" class="btn btn-danger-text btn-sm" @click="batchUninstall">卸载</button>
          <button type="button" class="btn btn-soft btn-sm" @click="onExportBatch">导出</button>
          <span class="batch-split" />
          <button type="button" class="btn btn-ghost btn-sm" @click="clearExportSelection">取消</button>
        </div>
      </Transition>

      <!-- 列表视图 -->
      <div v-if="viewMode === 'list'" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:48px">
                <input
                  type="checkbox"
                  class="row-check"
                  :checked="allFilteredSelected"
                  :indeterminate.prop="selectedCount > 0 && !allFilteredSelected"
                  aria-label="全选当前列表"
                  @change="toggleSelectAll"
                >
              </th>
              <th class="sortable" :class="{ active: sortBy === 'name' }" @click="setSort('name')">
                <span class="th-label">
                  插件
                  <svg class="sort-ic" :class="{ desc: sortBy === 'name' && sortDir === 'desc' }" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
                </span>
              </th>
              <th class="sortable desc-col" :class="{ active: sortBy === 'description' }" @click="setSort('description')">
                <span class="th-label">
                  描述
                  <svg class="sort-ic" :class="{ desc: sortBy === 'description' && sortDir === 'desc' }" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
                </span>
              </th>
              <th class="sortable num-th" :class="{ active: sortBy === 'skills' }" @click="setSort('skills')">
                <span class="th-label">
                  Skills
                  <svg class="sort-ic" :class="{ desc: sortBy === 'skills' && sortDir === 'desc' }" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
                </span>
              </th>
              <th class="sortable num-th" :class="{ active: sortBy === 'mcp' }" @click="setSort('mcp')">
                <span class="th-label">
                  MCP
                  <svg class="sort-ic" :class="{ desc: sortBy === 'mcp' && sortDir === 'desc' }" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
                </span>
              </th>
              <th class="sortable" style="width:90px" :class="{ active: sortBy === 'status' }" @click="setSort('status')">
                <span class="th-label">
                  状态
                  <svg class="sort-ic" :class="{ desc: sortBy === 'status' && sortDir === 'desc' }" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
                </span>
              </th>
              <th style="width:220px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in sortedPlugins" :key="p.file" :class="{ disabled: !p.installed, selected: selectedForExport.has(p.file) }">
              <td>
                <input
                  type="checkbox"
                  class="row-check"
                  :checked="selectedForExport.has(p.file)"
                  :aria-label="'选择 ' + p.name"
                  @change="toggleSelectForExport(p.file)"
                >
              </td>
              <td>
                <div class="name">{{ p.name }}<span class="ver">v{{ p.version }}</span></div>
              </td>
              <td><div class="desc" :title="p.description">{{ p.description || '—' }}</div></td>
              <td><span class="num-cell">{{ p.skills_count || 0 }}</span></td>
              <td><span class="num-cell">{{ p.mcp_count || 0 }}</span></td>
              <td>
                <span class="status" :class="p.installed ? 'on' : 'off'"><i />{{ p.installed ? '已安装' : '未安装' }}</span>
              </td>
              <td>
                <div class="ops">
                  <button
                    v-if="!p.installed"
                    type="button"
                    class="btn btn-primary btn-sm"
                    :disabled="!!installingPlugin"
                    @click="onTogglePlugin(p, true)"
                  >
                    {{ installingPlugin === p.name || installingPlugin === p.file ? '安装中…' : '安装' }}
                  </button>
                  <button
                    v-else
                    type="button"
                    class="btn btn-secondary btn-sm"
                    :disabled="!!installingPlugin"
                    @click="onTogglePlugin(p, false)"
                  >
                    卸载
                  </button>
                  <button type="button" class="btn btn-ghost btn-sm" @click="onEdit(p.file)">编辑</button>
                  <div class="export-menu relative">
                    <button type="button" class="btn btn-ghost btn-sm" @click.stop="toggleExportMenu(p.file)">导出</button>
                    <div v-if="exportMenu === p.file" class="menu-panel" @click.stop>
                      <button type="button" @click="doExport(p.file, 'zip')">ZIP（含 Skills）</button>
                      <button type="button" @click="doExport(p.file, 'yaml')">YAML（仅配置）</button>
                    </div>
                  </div>
                  <button type="button" class="btn btn-ghost btn-sm" title="发布到市场" @click="openPublishDialog(p.file)">分享</button>
                  <button type="button" class="btn btn-danger-text btn-sm" title="删除插件及其独占技能" @click="deletePlugin(p)">删除</button>
                </div>
              </td>
            </tr>
            <tr v-if="!sortedPlugins.length">
              <td colspan="7" class="empty-cell">
                {{ plugins.length ? '无匹配结果' : '暂无可用插件，点击「构建插件」或「导入」开始' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 图标视图 -->
      <div v-else class="grid-wrap">
        <article
          v-for="p in sortedPlugins"
          :key="p.file"
          class="plugin-card"
          :class="{ disabled: !p.installed, selected: selectedForExport.has(p.file) }"
        >
          <div class="card-top">
            <input
              type="checkbox"
              class="row-check"
              :checked="selectedForExport.has(p.file)"
              :aria-label="'选择 ' + p.name"
              @change="toggleSelectForExport(p.file)"
            >
            <div class="card-avatar" aria-hidden="true">{{ p.name.slice(0, 2) }}</div>
            <span class="status" :class="p.installed ? 'on' : 'off'"><i />{{ p.installed ? '已安装' : '未安装' }}</span>
          </div>
          <div class="card-body">
            <h3 :title="p.name">{{ p.name }}<span class="ver">v{{ p.version }}</span></h3>
            <p class="card-desc" :title="p.description">{{ p.description || '暂无描述' }}</p>
          </div>
          <div class="card-meta">
            <span class="mkt-chip brand">{{ p.skills_count || 0 }} skills</span>
            <span class="mkt-chip">{{ p.mcp_count || 0 }} mcp</span>
          </div>
          <div class="card-foot">
            <button
              v-if="!p.installed"
              type="button"
              class="btn btn-primary btn-sm"
              :disabled="!!installingPlugin"
              @click="onTogglePlugin(p, true)"
            >
              {{ installingPlugin === p.name || installingPlugin === p.file ? '安装中…' : '安装' }}
            </button>
            <button
              v-else
              type="button"
              class="btn btn-secondary btn-sm"
              :disabled="!!installingPlugin"
              @click="onTogglePlugin(p, false)"
            >
              卸载
            </button>
            <button type="button" class="btn btn-ghost btn-sm" @click="onEdit(p.file)">编辑</button>
            <div class="export-menu relative">
              <button type="button" class="btn btn-ghost btn-sm" @click.stop="toggleExportMenu(p.file)">导出</button>
              <div v-if="exportMenu === p.file" class="menu-panel" @click.stop>
                <button type="button" @click="doExport(p.file, 'zip')">ZIP</button>
                <button type="button" @click="doExport(p.file, 'yaml')">YAML</button>
              </div>
            </div>
            <button type="button" class="btn btn-ghost btn-sm" title="发布到市场" @click="openPublishDialog(p.file)">分享</button>
            <button type="button" class="btn btn-danger-text btn-sm" title="删除插件及其独占技能" @click="deletePlugin(p)">删除</button>
          </div>
        </article>
        <div v-if="!sortedPlugins.length" class="empty-cell">
          {{ plugins.length ? '无匹配结果' : '暂无可用插件，点击「构建插件」或「导入」开始' }}
        </div>
      </div>
    </section>

    <Teleport to="body">
      <div class="float-bar" :class="{ show: selectedForExport.size > 0 }">
        <span>已选 {{ selectedForExport.size }} 个插件</span>
        <button type="button" class="btn btn-ghost btn-sm" @click="clearExportSelection">取消</button>
        <button type="button" class="btn btn-primary btn-sm" @click="exportSelectedPlugins">导出 ZIP</button>
      </div>
    </Teleport>

    <!-- 导入弹层 -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="importOpen" class="modal-mask" @click.self="closeImport">
          <div class="modal-card import-modal" role="dialog" aria-modal="true" aria-labelledby="plugin-import-title">
            <header class="modal-head">
              <h2 id="plugin-import-title">导入插件</h2>
              <button type="button" class="modal-close" aria-label="关闭" @click="closeImport">×</button>
            </header>
            <div class="modal-body">
              <div
                class="import-dropzone"
                :class="{ over: importDragOver }"
                @dragover.prevent="importDragOver = true"
                @dragleave.prevent="importDragOver = false"
                @drop="onImportDrop"
                @click="onImportFileClick"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <div class="dz-text">
                  <b>点击选择文件</b> 或拖拽到此处
                  <div class="dz-formats">支持 .zip（含 Skills）或 .yaml / .yml</div>
                </div>
                <input
                  ref="importFileInput"
                  type="file"
                  accept=".yaml,.yml,.zip"
                  style="display:none"
                  @change="onImportFileChange"
                >
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 拖拽导入浮层 -->
    <Transition name="drop-fade">
      <div v-if="dragging" class="drop-overlay" @drop="onDrop" @dragover.prevent @dragleave.prevent>
        <div class="drop-card">
          <svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m8 11 4 4 4-4"/><path d="M4 19h16"/></svg>
          <strong>松开导入插件</strong>
          <span>支持 .zip（含 Skills）或 .yaml / .yml</span>
        </div>
      </div>
    </Transition>

    <!-- 导出选项弹窗 -->
    <Transition name="modal-fade">
      <div v-if="exportDialog" class="modal-mask" @click.self="cancelExport">
        <div class="modal-card export-modal" role="dialog" aria-modal="true" aria-label="导出选项">
          <header class="modal-head">
            <h2>导出选项</h2>
            <button type="button" class="modal-close" aria-label="关闭" @click="cancelExport">×</button>
          </header>
          <div class="modal-body">
            <p class="modal-hint">选择密钥处理方式（影响 llm.yaml 与 keys.yaml）</p>
            <label class="opt-row" :class="{ on: exportKeyMode === 'vault' }">
              <input v-model="exportKeyMode" type="radio" value="vault">
              <span class="opt-main">
                <span class="opt-title">使用密钥库（推荐）</span>
                <span class="opt-desc">明文 api_key 替换为 ${KEY} 引用，额外导出 keys.yaml（含真实值）。接收方导入后无需逐个填密码。</span>
              </span>
            </label>
            <label class="opt-row" :class="{ on: exportKeyMode === 'plain' }">
              <input v-model="exportKeyMode" type="radio" value="plain">
              <span class="opt-main">
                <span class="opt-title">含明文密码</span>
                <span class="opt-desc">原样导出 llm.yaml（api_key 为明文或 env: 引用），不导出 keys.yaml。仅自用备份。</span>
              </span>
            </label>
            <label class="opt-row" :class="{ on: exportKeyMode === 'redacted' }">
              <input v-model="exportKeyMode" type="radio" value="redacted">
              <span class="opt-main">
                <span class="opt-title">脱敏导出</span>
                <span class="opt-desc">llm.yaml 的 api_key 置空，keys.yaml 仅保留密钥名与描述。适合公开分享，接收方需自填密钥。</span>
              </span>
            </label>

            <div class="extras-section">
              <p class="modal-hint">导出内容（基于哪些配置文件）</p>
              <div class="extras-grid">
                <label
                  v-for="opt in EXTRA_OPTIONS"
                  :key="opt.key"
                  class="extra-chip"
                  :class="{ on: exportExtras.includes(opt.key) }"
                >
                  <input
                    type="checkbox"
                    :checked="exportExtras.includes(opt.key)"
                    @change="toggleExtra(opt.key)"
                  >
                  <span class="extra-label">{{ opt.label }}</span>
                  <span class="extra-desc">{{ opt.desc }}</span>
                </label>
              </div>
            </div>
          </div>
          <footer class="modal-foot">
            <button type="button" class="btn btn-ghost" @click="cancelExport">取消</button>
            <button type="button" class="btn btn-primary" @click="confirmExport">导出</button>
          </footer>
        </div>
      </div>
    </Transition>

    <!-- 发布插件弹窗 -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="publishDialogOpen" class="modal-mask" @click.self="publishDialogOpen = false">
          <div class="modal-card" role="dialog" aria-modal="true" style="max-width: 480px">
            <header class="modal-head">
              <h2>发布插件</h2>
              <button type="button" class="modal-close" aria-label="关闭" @click="publishDialogOpen = false">×</button>
            </header>
            <div class="modal-body">
              <label style="display:block;font-size:13px;font-weight:600;margin-bottom:10px">发布到</label>
              <div style="display:flex;gap:10px;margin-bottom:16px">
                <label style="flex:1;display:flex;align-items:center;gap:8px;padding:12px;border:1px solid var(--color-ink-300,#c9cdd4);border-radius:8px;cursor:pointer" :style="{ borderColor: publishScope === 'public' ? 'var(--brand-500,#6366f1)' : '' }">
                  <input type="radio" v-model="publishScope" value="public" style="accent-color:var(--brand-500,#6366f1)" />
                  <div>
                    <div style="font-size:14px;font-weight:600">公共市场</div>
                    <div style="font-size:12px;color:var(--text-tertiary)">所有人可见可下载</div>
                  </div>
                </label>
                <label v-if="auth.isLoggedIn && teamSpaces.length > 0" style="flex:1;display:flex;align-items:center;gap:8px;padding:12px;border:1px solid var(--color-ink-300,#c9cdd4);border-radius:8px;cursor:pointer" :style="{ borderColor: publishScope === 'team' ? 'var(--brand-500,#6366f1)' : '' }">
                  <input type="radio" v-model="publishScope" value="team" style="accent-color:var(--brand-500,#6366f1)" />
                  <div>
                    <div style="font-size:14px;font-weight:600">团队空间</div>
                    <div style="font-size:12px;color:var(--text-tertiary)">仅团队成员可见</div>
                  </div>
                </label>
              </div>
              <div v-if="publishScope === 'team' && teamSpaces.length > 0" style="margin-bottom:16px">
                <label style="display:block;font-size:13px;font-weight:600;margin-bottom:6px">选择团队</label>
                <select v-model="publishTeamId" style="width:100%;padding:10px 12px;border:1px solid var(--color-ink-300,#c9cdd4);border-radius:8px;font-size:14px;background:var(--bg-base,#f7f8fa)">
                  <option :value="null" disabled>请选择团队空间</option>
                  <option v-for="t in teamSpaces" :key="t.id" :value="t.id">{{ t.name }}（{{ t.role === 'owner' ? 'Owner' : 'Member' }}）</option>
                </select>
              </div>
              <p v-if="publishScope === 'team' && teamSpaces.length === 0" style="font-size:13px;color:var(--text-tertiary)">你还没有加入任何团队，请先创建团队空间</p>
              <p v-if="!auth.isLoggedIn" style="font-size:13px;color:var(--text-tertiary)">登录后可发布到团队空间</p>
            </div>
            <footer class="modal-foot">
              <button type="button" class="btn btn-ghost" @click="publishDialogOpen = false">取消</button>
              <button type="button" class="btn btn-primary" :disabled="publishScope === 'team' && !publishTeamId" @click="doPublish">发布</button>
            </footer>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.plugin-page {
  --green: #00b42a;
  --green-bg: #e8ffea;
  --amber: #ff7d00;
  --amber-bg: #fff7e8;
  --red: #f53f3f;
  --red-bg: #ffece8;
  --glow: 0 0 0 3px var(--primary-container-strong);
  --card: 0 1px 2px rgba(0, 0, 0, 0.04), 0 4px 12px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-bottom: 12px;
}

.plugin-head { margin: 0; }

.btn {
  height: 34px; padding: 0 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  white-space: nowrap; border: 1px solid transparent; cursor: pointer;
  transition: background .18s ease, color .18s ease, border-color .18s ease;
  background: none; color: inherit; user-select: none;
}
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn-sm { height: 28px; padding: 0 10px; font-size: 11px; border-radius: 7px; }
.btn-primary { background: var(--primary); color: #fff; box-shadow: 0 1px 2px rgba(22, 93, 255, .22); }
.btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
.btn-soft { background: var(--primary-container); color: var(--primary-hover); border-color: var(--primary-container-strong); }
.btn-soft:hover:not(:disabled) { background: #d9e6ff; }
.btn-secondary { background: var(--bg-elevated); color: var(--text-secondary); border-color: var(--border-base); }
.btn-secondary:hover:not(:disabled) { background: var(--bg-base); border-color: var(--border-strong); }
.btn-ghost { background: transparent; color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { background: var(--bg-base); color: var(--text-primary); }
.btn-danger-text { color: var(--text-secondary); }
.btn-danger-text:hover:not(:disabled) { background: var(--red-bg); color: var(--red); }
.btn:focus-visible { outline: none; box-shadow: var(--glow); }

.btn-cluster { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.btn-pair {
  display: inline-flex; border-radius: 8px; overflow: hidden;
  border: 1px solid var(--border-base); background: var(--bg-elevated);
}
.btn-pair .btn { border-radius: 0; border: none; height: 32px; border-right: 1px solid var(--border-base); }
.btn-pair .btn:last-child { border-right: none; }

.btn-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 16px; height: 16px; padding: 0 5px;
  margin-left: 4px;
  background: var(--primary);
  color: #fff;
  font-size: 10px; font-weight: 700;
  border-radius: 8px;
  line-height: 1;
}

.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi {
  background: var(--bg-elevated); border-radius: 12px; padding: 16px 18px;
  box-shadow: var(--card);
  border: 1px solid rgba(0,0,0,.03); position: relative; overflow: hidden;
}
.kpi::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--border-strong); }
.kpi.live::before { background: var(--green); }
.kpi.warn::before { background: var(--amber); }
.kpi.brand::before { background: var(--primary); }
.kpi b { display: block; font-size: 22px; font-variant-numeric: tabular-nums; line-height: 1.1; color: var(--text-primary); }
.kpi span { font-size: 12px; color: var(--text-tertiary); }
.kpi em { font-style: normal; font-size: 11px; color: var(--text-tertiary); margin-top: 6px; display: block; }

.panel {
  background: var(--bg-elevated); border-radius: 14px;
  box-shadow: var(--card);
  border: 1px solid rgba(0,0,0,.03); overflow: hidden;
}
.toolbar {
  display: flex; justify-content: space-between; gap: 14px; flex-wrap: wrap;
  padding: 14px 18px; border-bottom: 1px solid var(--border-base); align-items: center;
}
.toolbar-left { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.search {
  display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 12px;
  border: 1px solid var(--border-strong); border-radius: 8px; background: var(--bg-elevated); min-width: 220px;
}
.search:focus-within { border-color: var(--primary); box-shadow: var(--glow); }
.search input { border: none; outline: none; flex: 1; font-size: 12px; min-width: 0; background: transparent; }
.seg { display: inline-flex; background: var(--bg-base); padding: 3px; border-radius: 8px; }
.seg button {
  height: 28px; padding: 0 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
  color: var(--text-tertiary); border: none; background: transparent; cursor: pointer;
}
.seg button.on { background: var(--bg-elevated); color: var(--primary-hover); box-shadow: 0 1px 2px rgba(0, 0, 0, .06); }
.seg.view-toggle button { padding: 0 8px; display: inline-flex; align-items: center; justify-content: center; }
.seg.view-toggle svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

/* 批量操作条 */
.batch-bar {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 8px 4px 12px;
  background: var(--primary-container);
  border: 1px solid var(--primary-container-strong, rgba(22, 93, 255, 0.2));
  border-radius: 8px;
  font-size: 12px;
  margin: 10px 18px 0;
}
.batch-count { font-weight: 600; color: var(--primary-hover); margin-right: 4px; font-variant-numeric: tabular-nums; }
.batch-split { width: 1px; height: 16px; background: var(--border-base); margin: 0 4px; }

.fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.18s ease; }
.fade-slide-enter-from, .fade-slide-leave-to { opacity: 0; transform: translateY(-4px); }

.table-wrap { overflow: visible; }
table { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
th {
  text-align: left; font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase;
  letter-spacing: .04em; padding: 11px 18px; background: var(--bg-base); border-bottom: 1px solid var(--border-base);
}
td { padding: 13px 18px; border-bottom: 1px solid #f7f8fa; vertical-align: middle; }
tr:hover td { background: var(--bg-base); }
tr.disabled td { opacity: .62; }
tr.selected td { background: var(--primary-container); }
tr.selected:hover td { background: rgba(22, 93, 255, 0.12); }

/* 描述列宽控制：限制最大宽度，超出省略 */
.desc-col { width: 320px; }
td:nth-child(3) { width: 320px; }

th.sortable {
  cursor: pointer; user-select: none;
  transition: color .15s ease, background .15s ease;
}
th.sortable:hover { color: var(--text-primary); background: var(--bg-elevated); }
th.sortable.active { color: var(--primary); }
th.sortable .th-label {
  display: inline-flex; align-items: center; gap: 4px;
}
th.sortable .sort-ic {
  width: 12px; height: 12px; flex-shrink: 0;
  stroke: currentColor; fill: none; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round;
  opacity: 0; transform: rotate(0deg); transition: opacity .15s ease, transform .2s ease;
}
th.sortable:hover .sort-ic { opacity: .45; }
th.sortable.active .sort-ic { opacity: 1; }
th.sortable.active .sort-ic.desc { transform: rotate(180deg); }
.num-th { width: 90px; }

.row-check {
  width: 15px; height: 15px;
  cursor: pointer;
  accent-color: var(--primary);
  vertical-align: middle;
}

.pick { width: 16px; height: 16px; accent-color: var(--primary); cursor: pointer; }
.name { font-weight: 600; color: var(--text-primary); }
.ver {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px; color: var(--text-tertiary); margin-left: 8px; font-weight: 500;
}
.desc {
  font-size: 12.5px; color: var(--text-tertiary); line-height: 1.4;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.num-cell {
  font-variant-numeric: tabular-nums; font-weight: 600; color: var(--text-secondary);
}
.status {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px; font-weight: 600; padding: 3px 9px; border-radius: 999px;
}
.status i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status.on { background: var(--green-bg); color: var(--green); }
.status.off { background: var(--amber-bg); color: var(--amber); }

.ops { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }

.export-menu { position: relative; }
.menu-panel {
  position: absolute; right: 0; top: calc(100% + 4px); min-width: 148px;
  background: var(--bg-elevated); border: 1px solid var(--border-base); border-radius: 10px; box-shadow: var(--card);
  z-index: 20; overflow: hidden;
}
.menu-panel button {
  display: block; width: 100%; text-align: left; padding: 9px 12px; border: none; background: none;
  font-size: 12px; color: var(--text-secondary); cursor: pointer;
}
.menu-panel button:hover { background: var(--primary-container); color: var(--primary-hover); }

.empty-cell {
  text-align: center; color: var(--text-tertiary); font-size: 12.5px; padding: 28px 0;
}

/* 图标视图 */
.grid-wrap {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px; padding: 16px 18px;
}
.plugin-card {
  display: flex; flex-direction: column; gap: 10px; padding: 14px;
  border: 1px solid var(--border-base); border-radius: 12px; background: var(--bg-elevated);
  transition: border-color .18s ease, box-shadow .18s ease;
}
.plugin-card:hover { border-color: var(--primary); box-shadow: 0 4px 16px rgba(22, 93, 255, .06); }
.plugin-card.disabled { opacity: .65; }
.plugin-card.selected { border-color: var(--primary); background: var(--primary-container); }
.card-top { display: flex; align-items: center; gap: 10px; }
.card-avatar {
  width: 32px; height: 32px; border-radius: 8px; display: grid; place-items: center;
  background: var(--primary); color: #fff; font-weight: 700; font-size: 12px;
}
.card-top .status { margin-left: auto; }
.card-body h3 { margin: 0; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.card-desc {
  margin: 4px 0 0; font-size: 12px; color: var(--text-tertiary); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; min-height: 2.8em;
}
.card-meta { display: flex; flex-wrap: wrap; gap: 6px; }
.mkt-chip { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 999px; background: var(--bg-base); color: var(--text-secondary); }
.mkt-chip.brand { background: var(--primary-container); color: var(--primary-hover); }
.card-foot {
  margin-top: auto; display: flex; gap: 4px; flex-wrap: wrap; align-items: center;
  padding-top: 10px; border-top: 1px solid var(--bg-base);
}

.float-bar {
  position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%) translateY(20px);
  background: var(--text-primary); color: #fff; border-radius: 14px; padding: 10px 12px 10px 16px;
  display: flex; align-items: center; gap: 12px; box-shadow: 0 10px 30px rgba(0, 0, 0, .22);
  opacity: 0; pointer-events: none; transition: .2s ease; z-index: 40; max-width: calc(100vw - 32px);
}
.float-bar.show { opacity: 1; transform: translateX(-50%) translateY(0); pointer-events: auto; }
.float-bar span { font-size: 12.5px; white-space: nowrap; }
.float-bar .btn { height: 30px; color: #fff; border-color: rgba(255, 255, 255, .2); }
.float-bar .btn-primary { background: var(--primary); border-color: transparent; }
.float-bar .btn-ghost:hover:not(:disabled) { background: rgba(255, 255, 255, .1); color: #fff; }

/* 拖拽导入浮层 */
.drop-overlay {
  position: fixed; inset: 0; z-index: 50;
  background: rgba(22, 93, 255, .08);
  backdrop-filter: blur(2px);
  display: grid; place-items: center;
  pointer-events: auto;
}
.drop-card {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 32px 48px;
  border: 2px dashed var(--primary);
  border-radius: 18px;
  background: var(--bg-elevated);
  color: var(--primary-hover);
  text-align: center;
  box-shadow: 0 12px 40px rgba(22, 93, 255, .18);
}
.drop-card svg { width: 36px; height: 36px; stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.drop-card strong { font-size: 15px; }
.drop-card span { font-size: 12px; color: var(--text-tertiary); }
.drop-fade-enter-active, .drop-fade-leave-active { transition: opacity .18s ease; }
.drop-fade-enter-from, .drop-fade-leave-to { opacity: 0; }

/* 导出选项弹窗 */
.modal-mask {
  position: fixed; inset: 0; z-index: 60;
  background: rgba(0, 0, 0, .32);
  display: grid; place-items: center;
  padding: 16px;
}
.modal-card {
  width: 100%; max-width: 520px;
  background: var(--bg-elevated); border-radius: 14px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, .28);
  overflow: hidden;
}
.modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--border-base);
}
.modal-head h2 { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-primary); }
.modal-close {
  width: 28px; height: 28px; border: none; background: none; cursor: pointer;
  font-size: 20px; line-height: 1; color: var(--text-tertiary); border-radius: 6px;
}
.modal-close:hover { background: var(--bg-base); color: var(--text-primary); }
.modal-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }

/* 导入弹层专属 */
.import-modal { max-width: 480px; }
.import-dropzone {
  display: flex; align-items: center; gap: 14px;
  padding: 24px 20px;
  border: 2px dashed var(--border-base);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.18s;
  background: var(--bg-base);
}
.import-dropzone:hover { border-color: var(--primary); background: var(--primary-container); }
.import-dropzone.over { border-color: var(--primary); background: var(--primary-container); transform: scale(1.01); }
.import-dropzone svg { width: 32px; height: 32px; color: var(--text-tertiary); flex-shrink: 0; }
.import-dropzone .dz-text { font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
.import-dropzone .dz-text b { color: var(--primary); font-weight: 600; }
.import-dropzone .dz-formats { font-size: 11px; color: var(--text-tertiary); margin-top: 4px; }
.modal-hint { margin: 0 0 4px; font-size: 12px; color: var(--text-tertiary); }
.opt-row {
  display: flex; gap: 10px; padding: 12px 14px;
  border: 1px solid var(--border-base); border-radius: 10px;
  cursor: pointer; transition: border-color .15s ease, background .15s ease;
}
.opt-row:hover { border-color: var(--primary); }
.opt-row.on { border-color: var(--primary); background: var(--primary-container); }
.opt-row input[type="radio"] {
  margin-top: 2px; width: 15px; height: 15px; accent-color: var(--primary); flex-shrink: 0;
}
.opt-main { display: flex; flex-direction: column; gap: 3px; }
.opt-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.opt-desc { font-size: 12px; color: var(--text-tertiary); line-height: 1.45; }

/* 导出内容多选 */
.extras-section { margin-top: 8px; padding-top: 12px; border-top: 1px solid var(--border-base); }
.extras-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.extra-chip {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border: 1px solid var(--border-base); border-radius: 8px; cursor: pointer;
  transition: border-color .15s ease, background .15s ease;
}
.extra-chip:hover { border-color: var(--primary); }
.extra-chip.on { border-color: var(--primary); background: var(--primary-container); }
.extra-chip input[type="checkbox"] { width: 14px; height: 14px; accent-color: var(--primary); flex-shrink: 0; }
.extra-label { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.extra-desc { font-size: 11px; color: var(--text-tertiary); }

.modal-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 12px 20px; border-top: 1px solid var(--border-base);
}
.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity .18s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }

@media (max-width: 960px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .desc-col { width: 200px; }
  td:nth-child(3) { width: 200px; }
}
@media (max-width: 620px) {
  .kpis { grid-template-columns: 1fr; }
  .desc-col { width: 140px; }
  td:nth-child(3) { width: 140px; }
}
@media (prefers-reduced-motion: reduce) {
  .btn, .float-bar { transition: none !important; }
}
</style>
