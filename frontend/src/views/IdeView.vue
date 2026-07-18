<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted, computed, ref, reactive } from 'vue'
import { useIdeStore } from '../stores/ide'
import { useSyncStore } from '../stores/sync'
import { useUiStore } from '../stores/ui'

const ide = useIdeStore()
const sync = useSyncStore()
const ui = useUiStore()
const {
  ideDetectStats, ideDetecting, ideInstallInfo, ideInstallInfoLoaded,
  installedIdes, notInstalledIdes, sessionableIdes, showNotInstalled,
  ideInstalling, ideUninstalling, ideReinstalling, ideSyncing,
  ideLaunching, ideResuming, ideOpeningConfig,
  expandedIde, sessionDrawerOpen, expandedIdeCard, ideCardTab,
  ideSessionsMap, ideSessionsStatsMap, ideLoadingSessions,
  exportingSession, shareModalOpen, shareModalSession, shareTargetIde, shareImporting,
  shareTargetIdes,
} = storeToRefs(ide)
const { dragIdeKey, dragOverIdeKey } = storeToRefs(sync)
const {
  loadIdeDetect, launchIde, installIde, uninstallIde, reinstallIde, openIdeConfig,
  syncIdeConfig, toggleIdeSessions, closeSessionDrawer, toggleIdeCard, setIdeCardTab, exportSession,
  openShareModal, importSession,
} = ide
const { onIdeDragStart, onIdeDragOver, onIdeDrop, onIdeDragEnd } = sync

/** 双击路径复制到剪贴板 */
async function copyPath(path: string | undefined) {
  if (!path) return
  try {
    await navigator.clipboard.writeText(path)
    ui.toast('已复制路径', 'ok')
  } catch {
    ui.toast('复制失败', 'err')
  }
}

/** 生成图标首字母（最多 2 个字符） */
function markText(label: string): string {
  const words = label.split(/\s+/).filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  return label.slice(0, 2)
}

/** 当前激活的 CLI/App tab */
function currentTab(it: any): string {
  // 展开后的条目（both 拆分）直接用 _tab 字段
  if (it._tab) return it._tab
  const t = ideCardTab.value[it.key]
  if (t) return t
  const info = ideInstallInfo.value[it.key]
  if (!info) return 'cli'
  if (!it.exe_path && info.app) return 'app'
  if (!info.cli && info.app) return 'app'
  return 'cli'
}

function currentInfo(it: any): any {
  const tab = currentTab(it)
  const info = ideInstallInfo.value[it.key]
  if (!info) return null
  return tab === 'cli' ? info.cli : info.app
}

function currentPath(it: any): string {
  const tab = currentTab(it)
  if (tab === 'cli') return it.exe_path || ''
  return it.app_path || ''
}

function currentMethod(it: any): string {
  return currentInfo(it)?.method || ''
}

function currentInstalled(it: any): boolean {
  const tab = currentTab(it)
  return tab === 'cli' ? !!it.exe_path : !!it.app_path
}

function busyKey(it: any): string {
  return it.key + ':' + currentTab(it)
}

/** —— Launchpad 风格新增函数 —— **/

// IDE 品牌色映射（基于方案 C 设计稿）
const IDE_BRAND: Record<string, { from: string; to: string }> = {
  Agents:     { from: '#9ca3af', to: '#6b7280' },
  Claude:     { from: '#e88a5c', to: '#c75d3a' },
  Codex:      { from: '#1ec8a0', to: '#0a8a6a' },
  Cursor:     { from: '#3a3a3a', to: '#0a0a0a' },
  IDEA:       { from: '#1ea7fd', to: '#0a5fc7' },
  OpenClaw:   { from: '#a78bfa', to: '#7c5cf0' },
  OpenCode:   { from: '#7280f5', to: '#4f5cd9' },
  Qoder:      { from: '#3bcee6', to: '#0a93b3' },
  QoderCN:    { from: '#22c1d6', to: '#0e8a9c' },
  Trae:       { from: '#6b7bf9', to: '#3d4fd6' },
  TraeCN:     { from: '#ff8c5a', to: '#e6492d' },
  TraeSoloCN: { from: '#5b6478', to: '#3a4252' },
  WorkBuddy:  { from: '#f87171', to: '#dc2626' },
  ZCode:      { from: '#10b981', to: '#047857' },
  Hermes:     { from: '#fbbf24', to: '#d97706' },
}

function brandColor(key: string) {
  return IDE_BRAND[key] || { from: '#6b7280', to: '#374151' }
}

function iconStyle(key: string): string {
  const c = brandColor(key)
  return `background:linear-gradient(145deg, ${c.from} 0%, ${c.to} 100%)`
}

// 真实程序图标（后端从已安装 .app 包提取，失败回退到字母）
const iconErrors = reactive<Record<string, boolean>>({})
// 版本戳用于强制刷新图标缓存（避免后端缓存目录被修复后前端仍读到旧图标）
const ICON_VERSION = '20260719b'
const iconUrl = (key: string) => `/api/ide/icon/${encodeURIComponent(key)}?v=${ICON_VERSION}`
const iconFailed = (key: string) => !!iconErrors[key]
function onIconError(key: string) {
  iconErrors[key] = true
}

/** IDE 原始类型（基于安装信息，不展开） */
function ideRawType(it: any): 'cli' | 'app' | 'both' | '' {
  const info = ideInstallInfo.value[it.key]
  if (!info) return ''
  const hasCli = !!(info.cli && it.cli_names?.length)
  const hasApp = !!info.app
  if (hasCli && hasApp) return 'both'
  if (hasCli) return 'cli'
  if (hasApp) return 'app'
  return ''
}

/** 展开后的条目类型：both 拆开后每个条目带 _tab 字段 */
function ideType(it: any): 'cli' | 'app' | '' {
  if (it._tab) return it._tab as 'cli' | 'app'
  return ideRawType(it) === 'app' ? 'app' : (ideRawType(it) === 'cli' ? 'cli' : '')
}

/** 把 both 类型的 IDE 拆成两个独立条目（CLI / App） */
function expandIde(it: any): any[] {
  const raw = ideRawType(it)
  if (raw !== 'both') return [it]
  return [
    { ...it, _tab: 'cli', _uid: it.key + ':cli', label: it.label + ' CLI', _expanded: true },
    { ...it, _tab: 'app', _uid: it.key + ':app', label: it.label + ' App', _expanded: true },
  ]
}

/** 条目的唯一标识（展开条目用 key:tab，普通条目用 key） */
function ideUid(it: any): string {
  return it._uid || it.key
}

function typeLabel(it: any): string {
  const t = ideType(it)
  if (t === 'cli') return 'CLI'
  if (t === 'app') return 'App'
  return '—'
}

function sessionCount(it: any): number {
  return ideSessionsStatsMap.value[it.key]?.total || 0
}

// 展开后的已安装/未安装列表（both 拆成两个独立条目）
const expandedInstalled = computed(() =>
  installedIdes.value.flatMap(it => expandIde(it))
)
const expandedNotInstalled = computed(() =>
  notInstalledIdes.value.flatMap(it => expandIde(it))
)

// 按类型分组（展开后只有 cli / app 两组）
const installedCli = computed(() =>
  expandedInstalled.value.filter(it => ideType(it) === 'cli')
)
const installedApp = computed(() =>
  expandedInstalled.value.filter(it => ideType(it) === 'app')
)
const notInstalledCli = computed(() =>
  expandedNotInstalled.value.filter(it => ideType(it) === 'cli')
)
const notInstalledApp = computed(() =>
  expandedNotInstalled.value.filter(it => ideType(it) === 'app')
)
// 既无 CLI 也无 App 的兜底分组（极少见，归类到"其他"）
const notInstalledOther = computed(() =>
  expandedNotInstalled.value.filter(it => ideType(it) === '')
)

/** 当前选中的 IDE 对象（用于 Dock） */
const currentSelectedIde = computed(() => {
  if (!expandedIde.value) return null
  // 优先在展开后的列表里按 _uid 查找（both 拆分条目）
  const all = [...expandedInstalled.value, ...expandedNotInstalled.value]
  return all.find(i => ideUid(i) === expandedIde.value) || null
})

// 进入 AIDE 管理页时自动检测（首次无数据才检测，避免重复请求）
onMounted(() => {
  if (!ide.ideDetects.length) loadIdeDetect()
})
</script>

<template>
  <div class="ide-launchpad">
    <!-- 右上角刷新按钮 -->
    <button v-if="!ideDetecting && ideInstallInfoLoaded" @click="loadIdeDetect" :disabled="ideDetecting" class="refresh-btn" type="button" title="重新检测">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
    </button>

    <!-- 加载中 -->
    <div v-if="ideDetecting || !ideInstallInfoLoaded" class="loading">
      <div class="spinner" aria-hidden="true"></div>
      <div>{{ ideDetecting ? '检测 IDE 安装状态...' : '加载安装信息...' }}</div>
    </div>

    <div v-else>
      <!-- 已安装 · CLI 工具 -->
      <section v-if="installedCli.length" class="section">
        <div class="section-head">
          <h2>
            <span class="type-icon cli">
              <svg fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 7l4 4-4 4M13 17h6"/></svg>
            </span>
            已安装 · CLI 工具
          </h2>
          <span class="count">{{ installedCli.length }} 个</span>
          <div class="line"></div>
        </div>
        <div class="grid">
          <div
            v-for="it in installedCli" :key="ideUid(it)"
            :class="['item', { 'selected': expandedIde === ideUid(it), 'dragging': dragIdeKey === ideUid(it), 'drag-over': dragOverIdeKey === ideUid(it) && dragIdeKey !== ideUid(it) }]"
            draggable="true"
            @click="toggleIdeCard(ideUid(it))"
            @dragstart="onIdeDragStart($event, it.key)"
            @dragover="onIdeDragOver($event, it.key)"
            @drop="onIdeDrop($event, it.key)"
            @dragend="onIdeDragEnd"
          >
            <div class="icon-wrap">
              <div class="icon" :class="{ 'has-img': !iconFailed(it.key) }" :style="iconStyle(it.key)" aria-hidden="true">
                <img v-if="!iconFailed(it.key)" :src="iconUrl(it.key)" :alt="it.label" class="icon-img" @error="onIconError(it.key)" draggable="false" />
                <span v-else class="icon-text">{{ markText(it.label) }}</span>
              </div>
              <div v-if="ideType(it)" :class="['type-badge', ideType(it)]" :title="typeLabel(it)">
                <svg v-if="ideType(it) === 'cli'" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 7l4 4-4 4M13 17h6"/></svg>
                <svg v-else-if="ideType(it) === 'app'" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16" stroke-linecap="round"/></svg>
                <svg v-else fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M5 7l4 4-4 4M13 17h6"/></svg>
              </div>
              <span v-if="sessionCount(it)" class="badge">{{ sessionCount(it) }}</span>
            </div>
            <div class="label" :title="it.label">{{ it.label }}</div>
            <div class="sublabel">
              <span>{{ typeLabel(it) }}</span>
              <span class="dot"></span>
              <span>{{ it.version || (currentMethod(it) || '—') }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 已安装 · 桌面 App -->
      <section v-if="installedApp.length" class="section">
        <div class="section-head">
          <h2>
            <span class="type-icon app">
              <svg fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16" stroke-linecap="round"/></svg>
            </span>
            已安装 · 桌面 App
          </h2>
          <span class="count">{{ installedApp.length }} 个</span>
          <div class="line"></div>
        </div>
        <div class="grid">
          <div
            v-for="it in installedApp" :key="ideUid(it)"
            :class="['item', { 'selected': expandedIde === ideUid(it), 'dragging': dragIdeKey === ideUid(it), 'drag-over': dragOverIdeKey === ideUid(it) && dragIdeKey !== ideUid(it) }]"
            draggable="true"
            @click="toggleIdeCard(ideUid(it))"
            @dragstart="onIdeDragStart($event, it.key)"
            @dragover="onIdeDragOver($event, it.key)"
            @drop="onIdeDrop($event, it.key)"
            @dragend="onIdeDragEnd"
          >
            <div class="icon-wrap">
              <div class="icon" :class="{ 'has-img': !iconFailed(it.key) }" :style="iconStyle(it.key)" aria-hidden="true">
                <img v-if="!iconFailed(it.key)" :src="iconUrl(it.key)" :alt="it.label" class="icon-img" @error="onIconError(it.key)" draggable="false" />
                <span v-else class="icon-text">{{ markText(it.label) }}</span>
              </div>
              <div v-if="ideType(it)" :class="['type-badge', ideType(it)]" :title="typeLabel(it)">
                <svg v-if="ideType(it) === 'cli'" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 7l4 4-4 4M13 17h6"/></svg>
                <svg v-else-if="ideType(it) === 'app'" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16" stroke-linecap="round"/></svg>
                <svg v-else fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M5 7l4 4-4 4M13 17h6"/></svg>
              </div>
              <span v-if="sessionCount(it)" class="badge">{{ sessionCount(it) }}</span>
            </div>
            <div class="label" :title="it.label">{{ it.label }}</div>
            <div class="sublabel">
              <span>{{ typeLabel(it) }}</span>
              <span class="dot"></span>
              <span>{{ it.version || (currentMethod(it) || '—') }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 未安装 · CLI 工具 -->
      <section v-if="notInstalledCli.length" class="section">
        <div class="section-head">
          <h2>
            <span class="type-icon cli">
              <svg fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 7l4 4-4 4M13 17h6"/></svg>
            </span>
            未安装 · CLI 工具
          </h2>
          <span class="count">{{ notInstalledCli.length }} 个</span>
          <div class="line"></div>
        </div>
        <div class="grid">
          <div
            v-for="it in notInstalledCli" :key="ideUid(it)"
            :class="['item', 'offline', { 'selected': expandedIde === ideUid(it), 'dragging': dragIdeKey === ideUid(it), 'drag-over': dragOverIdeKey === ideUid(it) && dragIdeKey !== ideUid(it) }]"
            draggable="true"
            @click="toggleIdeCard(ideUid(it))"
            @dragstart="onIdeDragStart($event, it.key)"
            @dragover="onIdeDragOver($event, it.key)"
            @drop="onIdeDrop($event, it.key)"
            @dragend="onIdeDragEnd"
          >
            <div class="icon-wrap">
              <div class="icon" :class="{ 'has-img': !iconFailed(it.key) }" :style="iconStyle(it.key)" aria-hidden="true">
                <img v-if="!iconFailed(it.key)" :src="iconUrl(it.key)" :alt="it.label" class="icon-img" @error="onIconError(it.key)" draggable="false" />
                <span v-else class="icon-text">{{ markText(it.label) }}</span>
              </div>
              <div :class="['type-badge', 'cli']" title="CLI 工具">
                <svg fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 7l4 4-4 4M13 17h6"/></svg>
              </div>
            </div>
            <div class="label" :title="it.label">{{ it.label }}</div>
            <div class="sublabel">
              <span>CLI</span>
              <span class="dot"></span>
              <span>未安装</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 未安装 · 桌面 App -->
      <section v-if="notInstalledApp.length" class="section">
        <div class="section-head">
          <h2>
            <span class="type-icon app">
              <svg fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16" stroke-linecap="round"/></svg>
            </span>
            未安装 · 桌面 App
          </h2>
          <span class="count">{{ notInstalledApp.length }} 个</span>
          <div class="line"></div>
        </div>
        <div class="grid">
          <div
            v-for="it in notInstalledApp" :key="ideUid(it)"
            :class="['item', 'offline', { 'selected': expandedIde === ideUid(it), 'dragging': dragIdeKey === ideUid(it), 'drag-over': dragOverIdeKey === ideUid(it) && dragIdeKey !== ideUid(it) }]"
            draggable="true"
            @click="toggleIdeCard(ideUid(it))"
            @dragstart="onIdeDragStart($event, it.key)"
            @dragover="onIdeDragOver($event, it.key)"
            @drop="onIdeDrop($event, it.key)"
            @dragend="onIdeDragEnd"
          >
            <div class="icon-wrap">
              <div class="icon" :class="{ 'has-img': !iconFailed(it.key) }" :style="iconStyle(it.key)" aria-hidden="true">
                <img v-if="!iconFailed(it.key)" :src="iconUrl(it.key)" :alt="it.label" class="icon-img" @error="onIconError(it.key)" draggable="false" />
                <span v-else class="icon-text">{{ markText(it.label) }}</span>
              </div>
              <div :class="['type-badge', 'app']" title="桌面 App">
                <svg fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h16" stroke-linecap="round"/></svg>
              </div>
            </div>
            <div class="label" :title="it.label">{{ it.label }}</div>
            <div class="sublabel">
              <span>App</span>
              <span class="dot"></span>
              <span>未安装</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 兜底：其他未分类 -->
      <section v-if="notInstalledOther.length" class="section">
        <div class="section-head">
          <h2>
            <span class="type-icon other">
              <svg fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01" stroke-linecap="round"/></svg>
            </span>
            未安装 · 其他
          </h2>
          <span class="count">{{ notInstalledOther.length }} 个</span>
          <div class="line"></div>
        </div>
        <div class="grid">
          <div
            v-for="it in notInstalledOther" :key="ideUid(it)"
            :class="['item', 'offline', { 'selected': expandedIde === ideUid(it), 'dragging': dragIdeKey === ideUid(it), 'drag-over': dragOverIdeKey === ideUid(it) && dragIdeKey !== ideUid(it) }]"
            draggable="true"
            @click="toggleIdeCard(ideUid(it))"
            @dragstart="onIdeDragStart($event, it.key)"
            @dragover="onIdeDragOver($event, it.key)"
            @drop="onIdeDrop($event, it.key)"
            @dragend="onIdeDragEnd"
          >
            <div class="icon-wrap">
              <div class="icon" :class="{ 'has-img': !iconFailed(it.key) }" :style="iconStyle(it.key)" aria-hidden="true">
                <img v-if="!iconFailed(it.key)" :src="iconUrl(it.key)" :alt="it.label" class="icon-img" @error="onIconError(it.key)" draggable="false" />
                <span v-else class="icon-text">{{ markText(it.label) }}</span>
              </div>
            </div>
            <div class="label" :title="it.label">{{ it.label }}</div>
            <div class="sublabel">
              <span>配置目录</span>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- 底部 Dock 操作栏：选中 IDE 后浮动显示 -->
    <Transition name="dock">
      <div v-if="currentSelectedIde" class="dock" @click.stop>
        <div class="dock-title">
          <span class="dock-name">{{ currentSelectedIde.label }}</span>
          <span v-if="ideType(currentSelectedIde)" :class="['type-tag', ideType(currentSelectedIde)]">{{ typeLabel(currentSelectedIde) }}</span>
        </div>

        <div class="dock-path" :title="currentPath(currentSelectedIde) || (currentInfo(currentSelectedIde) ? '未安装' : '—')">
          <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
          <span @dblclick="copyPath(currentPath(currentSelectedIde))">{{ currentPath(currentSelectedIde) || (currentInfo(currentSelectedIde) ? '未安装' : '—') }}</span>
        </div>

        <div class="dock-actions">
          <template v-if="currentInstalled(currentSelectedIde)">
            <button @click="launchIde(currentSelectedIde.key, null, currentTab(currentSelectedIde))" :disabled="ideLaunching === currentSelectedIde.key || !!ideResuming" class="dock-item primary" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              {{ ideLaunching === currentSelectedIde.key ? '...' : '打开' }}
            </button>
            <button @click="syncIdeConfig(currentSelectedIde.key)" :disabled="ideSyncing === currentSelectedIde.key" class="dock-item" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
              {{ ideSyncing === currentSelectedIde.key ? '...' : '同步' }}
            </button>
            <button v-if="currentSelectedIde.sessions_dir" @click="toggleIdeSessions(currentSelectedIde.key)" :disabled="!!ideLoadingSessions" class="dock-item" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
              {{ ideLoadingSessions === currentSelectedIde.key ? '...' : '会话' }}<span v-if="sessionCount(currentSelectedIde)" class="dock-count">{{ sessionCount(currentSelectedIde) }}</span>
            </button>
            <button v-if="currentSelectedIde.config_paths?.length" @click="openIdeConfig(currentSelectedIde.key)" :disabled="ideOpeningConfig === currentSelectedIde.key" class="dock-item" type="button">{{ ideOpeningConfig === currentSelectedIde.key ? '...' : '配置' }}</button>
            <button v-if="currentMethod(currentSelectedIde) && currentMethod(currentSelectedIde) !== 'manual'" @click="reinstallIde(currentSelectedIde.key, currentTab(currentSelectedIde))" :disabled="ideReinstalling === busyKey(currentSelectedIde)" class="dock-item" type="button">{{ ideReinstalling === busyKey(currentSelectedIde) ? '...' : '重装' }}</button>
            <button v-if="currentMethod(currentSelectedIde) && currentMethod(currentSelectedIde) !== 'manual'" @click="uninstallIde(currentSelectedIde.key, currentTab(currentSelectedIde))" :disabled="ideUninstalling === busyKey(currentSelectedIde)" class="dock-item danger" type="button">{{ ideUninstalling === busyKey(currentSelectedIde) ? '...' : '卸载' }}</button>
            <button v-if="currentMethod(currentSelectedIde) && currentMethod(currentSelectedIde) !== 'manual'" @click="uninstallIde(currentSelectedIde.key, currentTab(currentSelectedIde), true)" :disabled="ideUninstalling === busyKey(currentSelectedIde) + ':force'" class="dock-item danger" type="button" title="跳过系统卸载程序，直接强删目录">{{ ideUninstalling === busyKey(currentSelectedIde) + ':force' ? '...' : '强删' }}</button>
          </template>
          <template v-else>
            <button v-if="currentMethod(currentSelectedIde) && currentMethod(currentSelectedIde) !== 'manual'" @click="installIde(currentSelectedIde.key, currentTab(currentSelectedIde))" :disabled="ideInstalling === busyKey(currentSelectedIde)" class="dock-item primary" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/></svg>
              {{ ideInstalling === busyKey(currentSelectedIde) ? '...' : '安装' }}
            </button>
            <a v-else-if="currentInfo(currentSelectedIde)?.url" :href="currentInfo(currentSelectedIde).url" target="_blank" class="dock-item">下载</a>
            <button v-if="currentSelectedIde.config_paths?.length" @click="openIdeConfig(currentSelectedIde.key)" :disabled="ideOpeningConfig === currentSelectedIde.key" class="dock-item" type="button">{{ ideOpeningConfig === currentSelectedIde.key ? '...' : '配置' }}</button>
          </template>
          <a v-if="ideInstallInfo[currentSelectedIde.key]?.homepage" :href="ideInstallInfo[currentSelectedIde.key].homepage" target="_blank" class="dock-item">官网</a>
          <button @click="toggleIdeCard(currentSelectedIde.key)" class="dock-item close" type="button" title="关闭">
            <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
      </div>
    </Transition>

    <!-- 会话管理抽屉（保留原功能） -->
    <Transition name="drawer">
      <div v-if="sessionDrawerOpen" class="sess-overlay" @click.self="closeSessionDrawer" role="presentation">
        <aside class="sess-drawer" role="dialog" aria-modal="true" aria-labelledby="sess-drawer-title">
          <header class="sess-head">
            <div class="sess-head-main">
              <div class="sess-head-icon" aria-hidden="true">
                <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
              </div>
              <div class="sess-head-text">
                <h2 id="sess-drawer-title">会话管理</h2>
                <p v-if="expandedIde">
                  {{ sessionableIdes.find(i => i.key === expandedIde)?.label || expandedIde }}
                  · {{ ideSessionsStatsMap[expandedIde]?.total || 0 }} 个会话
                </p>
                <p v-else>选择 IDE 查看会话</p>
              </div>
            </div>
            <button type="button" class="sess-close" @click="closeSessionDrawer" aria-label="关闭">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </header>

          <div v-if="sessionableIdes.length" class="sess-tabs" role="tablist" aria-label="IDE 切换">
            <button
              v-for="it in sessionableIdes" :key="ideUid(it)"
              type="button" role="tab"
              :aria-selected="expandedIde === ideUid(it)"
              :class="['sess-tab', expandedIde === ideUid(it) && 'active']"
              @click="toggleIdeSessions(it.key)"
            >
              {{ it.label }}
              <span v-if="ideSessionsStatsMap[it.key]" class="sess-tab-count">{{ ideSessionsStatsMap[it.key].total }}</span>
            </button>
          </div>

          <div class="sess-body">
            <div v-if="!sessionableIdes.length" class="sess-empty">
              <div class="sess-empty-icon" aria-hidden="true">
                <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              </div>
              <strong>暂无可用 IDE</strong>
              <span>当前没有支持会话管理的 IDE</span>
            </div>
            <div v-else-if="!expandedIde" class="sess-empty">
              <div class="sess-empty-icon" aria-hidden="true">
                <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
              </div>
              <strong>选择一个 IDE</strong>
              <span>点击上方标签查看会话列表</span>
            </div>
            <div v-else-if="ideLoadingSessions === expandedIde" class="sess-empty">
              <div class="sess-spinner" aria-hidden="true"></div>
              <strong>加载中</strong>
              <span>正在读取会话列表…</span>
            </div>
            <div v-else-if="!ideSessionsMap[expandedIde]?.length" class="sess-empty">
              <div class="sess-empty-icon" aria-hidden="true">
                <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
              </div>
              <strong>暂无会话</strong>
              <span>该 IDE 还没有可恢复的会话记录</span>
            </div>
            <ul v-else class="sess-list" role="list">
              <li v-for="s in ideSessionsMap[expandedIde]" :key="s.id" class="sess-item">
                <div class="sess-item-main">
                  <div class="sess-item-title">{{ s.title || s.id.slice(0, 8) }}</div>
                  <div class="sess-item-meta">
                    <span>{{ s.messages_count }} 条消息</span>
                    <span v-if="s.tool_calls" class="dot" aria-hidden="true"></span>
                    <span v-if="s.tool_calls">{{ s.tool_calls }} 工具</span>
                    <span class="dot" aria-hidden="true"></span>
                    <span>{{ s.updated_at }}</span>
                  </div>
                  <div v-if="s.cwd" class="sess-item-path" :title="s.cwd">
                    <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
                    <code>{{ s.cwd }}</code>
                  </div>
                </div>
                <div class="sess-item-actions">
                  <button v-if="exportingSession !== s.id" @click="exportSession(s.id)" type="button" class="btn btn-sm btn-ink">导出</button>
                  <button v-else type="button" disabled class="btn btn-sm btn-ink">导出中</button>
                  <button @click="openShareModal(s.id)" type="button" class="btn btn-sm btn-soft">分享</button>
                  <button @click="launchIde(expandedIde, s.id, 'cli')" :disabled="ideResuming === s.id || !!ideLaunching" type="button" class="btn btn-sm btn-primary">
                    {{ ideResuming === s.id ? '...' : '恢复' }}
                  </button>
                </div>
              </li>
            </ul>
          </div>
        </aside>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* —— Launchpad 容器 · 浅色 ink 风格（与全局同步面板统一） —— */
.ide-launchpad {
  position: relative;
  min-height: 100%;
  padding: 40px 32px 140px;
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', sans-serif;
  -webkit-font-smoothing: antialiased;
  background: var(--bg-base);
  background-attachment: fixed;
  overflow-x: hidden;
}
.ide-launchpad::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255,255,255,0.6) 0%, transparent 200px);
  pointer-events: none;
  z-index: 0;
}
.ide-launchpad > * {
  position: relative;
  z-index: 1;
}

/* —— 右上角刷新按钮 —— */
.refresh-btn {
  position: fixed;
  top: 16px;
  right: 24px;
  z-index: 20;
  width: 32px;
  height: 32px;
  display: inline-grid;
  place-items: center;
  border-radius: 10px;
  border: 1px solid var(--border-base);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.refresh-btn svg { width: 14px; height: 14px; }
.refresh-btn:hover:not(:disabled) { background: var(--bg-base); border-color: var(--border-strong); }
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* —— 加载 —— */
.loading {
  text-align: center;
  padding: 80px 16px;
  color: var(--text-tertiary);
  font-size: 13px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.spinner {
  width: 28px;
  height: 28px;
  border: 2.5px solid var(--border-base);
  border-top-color: var(--text-secondary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* —— Section —— */
.section {
  margin: 0 0 44px;
}
.section-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 20px;
  padding: 0 8px;
}
.section-head h2 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.02em;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.section-head h2 .type-icon {
  width: 18px;
  height: 18px;
  display: inline-grid;
  place-items: center;
  border-radius: 5px;
}
.section-head h2 .type-icon svg { width: 11px; height: 11px; }
.section-head h2 .type-icon.ok { background: rgba(16, 185, 129, 0.12); color: #059669; }
.section-head h2 .type-icon.cli { background: rgba(16, 185, 129, 0.12); color: #059669; }
.section-head h2 .type-icon.app { background: rgba(59, 130, 246, 0.12); color: #2563eb; }
.section-head h2 .type-icon.both { background: rgba(139, 92, 246, 0.12); color: #7c3aed; }
.section-head h2 .type-icon.other { background: var(--border-base); color: var(--text-tertiary); }
.section-head .count {
  font-size: 12px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}
.section-head .line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, var(--border-base), transparent);
}

/* —— 图标网格 —— */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px 16px;
}

/* —— 图标项 —— */
.item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 18px 8px 14px;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.2, 0.8, 0.2, 1);
  position: relative;
  text-align: center;
  user-select: none;
}
.item:hover {
  background: var(--bg-elevated);
  transform: scale(1.04);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}
.item:active { transform: scale(0.98); }
.item.selected {
  background: var(--bg-elevated);
  box-shadow: 0 0 0 2px var(--primary), 0 8px 24px rgba(37, 99, 235, 0.15);
}
.item.dragging { opacity: 0.4; cursor: grabbing; transform: scale(0.96); }
.item.drag-over { box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.5); }

.icon-wrap {
  position: relative;
  width: 72px;
  height: 72px;
}
.icon {
  width: 72px;
  height: 72px;
  border-radius: 18px;
  display: grid;
  place-items: center;
  position: relative;
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.04) inset,
    0 8px 20px rgba(0, 0, 0, 0.1);
  transition: transform 0.2s;
}
.item:hover .icon { transform: translateY(-2px); }
.icon::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.3), transparent 50%);
  pointer-events: none;
}
/* 真实程序图标：移除渐变背景和顶部高光，让 logo 完整显示 */
.icon.has-img {
  background: var(--bg-elevated) !important;
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.04) inset,
    0 8px 20px rgba(0, 0, 0, 0.1);
}
.icon.has-img::after { display: none; }
.icon-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: inherit;
  display: block;
  position: relative;
  z-index: 1;
}
.icon-text {
  font-size: 22px;
  font-weight: 800;
  color: #fff;
  letter-spacing: -0.02em;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
  position: relative;
  z-index: 1;
}

/* —— 类型角标 —— */
.type-badge {
  position: absolute;
  right: -3px;
  bottom: -3px;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  border: 2px solid #fff;
  box-shadow: 0 2px 6px rgba(0,0,0, 0.15);
}
.type-badge svg { width: 12px; height: 12px; filter: none; }
.type-badge.cli {
  background: linear-gradient(145deg, #10b981, #059669);
  color: #fff;
}
.type-badge.app {
  background: linear-gradient(145deg, #3b82f6, #2563eb);
  color: #fff;
}
.type-badge.both {
  background: linear-gradient(145deg, #8b5cf6, #7c3aed);
  color: #fff;
}

/* —— 会话数徽章 —— */
.badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 999px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: grid;
  place-items: center;
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.4);
  border: 2px solid #fff;
  font-variant-numeric: tabular-nums;
}

/* —— 标签 —— */
.label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.3;
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sublabel {
  font-size: 10px;
  color: var(--text-tertiary);
  margin-top: 1px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.sublabel .dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--border-strong);
}

/* —— 离线（未安装） —— */
.item.offline .icon {
  filter: grayscale(0.6) brightness(1.05);
  opacity: 0.65;
}
.item.offline .label { color: var(--text-tertiary); }
.item.offline .type-badge { opacity: 0.6; }
.item.offline:hover .icon { filter: grayscale(0.3) brightness(1.05); opacity: 0.85; }

/* —— 底部 Dock —— */
.dock {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
  padding: 12px 14px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 18px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.12);
  z-index: 20;
  align-items: center;
  max-width: 92vw;
  flex-wrap: wrap;
  justify-content: center;
}
.dock-title {
  padding: 0 12px 0 6px;
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
  border-right: 1px solid var(--border-base);
  margin-right: 4px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.dock-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dock-title .type-tag {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 5px;
  font-weight: 600;
}
.dock-title .type-tag.cli { background: rgba(16, 185, 129, 0.12); color: #059669; }
.dock-title .type-tag.app { background: rgba(59, 130, 246, 0.12); color: #2563eb; }
.dock-title .type-tag.both { background: rgba(139, 92, 246, 0.12); color: #7c3aed; }

.dock-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  background: var(--bg-base);
  border-radius: 8px;
}
.dock-tab {
  padding: 5px 12px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.dock-tab:hover { color: var(--text-secondary); }
.dock-tab.active {
  background: var(--bg-elevated);
  color: var(--text-primary);
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.dock-path {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 240px;
  padding: 6px 10px;
  background: var(--bg-base);
  border: 1px solid var(--border-base);
  border-radius: 8px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 10.5px;
  color: var(--text-secondary);
  overflow: hidden;
}
.dock-path svg { width: 12px; height: 12px; flex-shrink: 0; color: var(--text-tertiary); }
.dock-path span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: text;
  user-select: text;
}

.dock-actions {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}
.dock-item {
  padding: 7px 14px;
  border-radius: 9px;
  background: var(--bg-base);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  text-decoration: none;
}
.dock-item svg { width: 13px; height: 13px; }
.dock-item:hover:not(:disabled) { background: var(--border-base); }
.dock-item:disabled { opacity: 0.45; cursor: not-allowed; }
.dock-item.primary {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
.dock-item.primary:hover:not(:disabled) { background: var(--primary-hover); border-color: var(--primary-hover); }
.dock-item.danger {
  background: #fee2e2;
  color: #b91c1c;
}
.dock-item.danger:hover:not(:disabled) { background: #fecaca; }
.dock-item.close {
  padding: 7px 9px;
  background: var(--bg-base);
}
.dock-item.close:hover { background: var(--border-base); }
.dock-count {
  font-size: 10px;
  font-weight: 700;
  background: #ef4444;
  color: #fff;
  padding: 1px 5px;
  border-radius: 999px;
  margin-left: 2px;
}

/* Dock 过渡 */
.dock-enter-active, .dock-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.dock-enter-from, .dock-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(20px);
}

/* —— 通用按钮（会话抽屉使用） —— */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s, color 0.2s, box-shadow 0.2s, filter 0.2s;
  line-height: 1.2;
  text-decoration: none;
}
.btn svg { width: 14px; height: 14px; flex-shrink: 0; }
.btn:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--primary-container-strong); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--primary); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
.btn-soft { background: var(--primary-container); color: var(--primary-hover); border-color: var(--primary-container-strong); }
.btn-soft:hover:not(:disabled) { background: #d9e6ff; }
.btn-ink { background: var(--bg-elevated); color: var(--text-primary); border-color: var(--border-base); }
.btn-ink:hover:not(:disabled) { background: var(--bg-base); border-color: var(--border-strong); }
.btn-sm { padding: 6px 10px; font-size: 11px; border-radius: 7px; }
.btn-sm svg { width: 12px; height: 12px; }

/* —— 会话抽屉（白色面板） —— */
.sess-overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  justify-content: flex-end;
  background: rgba(31, 35, 41, 0.4);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
}
.sess-drawer {
  width: 440px;
  max-width: 92vw;
  height: 100%;
  background: var(--bg-elevated);
  border-left: 1px solid var(--border-base);
  box-shadow: -12px 0 40px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.sess-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--border-base);
  background: var(--bg-elevated);
  flex-shrink: 0;
}
.sess-head-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}
.sess-head-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--primary-container);
  color: var(--primary-hover);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.sess-head-icon svg { width: 18px; height: 18px; }
.sess-head-text { min-width: 0; }
.sess-head-text h2 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  line-height: 1.3;
  margin: 0;
}
.sess-head-text p {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
}
.sess-close {
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-base);
  background: var(--bg-elevated);
  border-radius: 8px;
  color: var(--text-tertiary);
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background-color 0.2s, border-color 0.2s, color 0.2s;
}
.sess-close svg { width: 16px; height: 16px; }
.sess-close:hover { background: var(--bg-base); color: var(--text-primary); border-color: var(--border-strong); }
.sess-close:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--primary-container-strong); }

.sess-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-base);
  background: var(--bg-base);
  flex-shrink: 0;
}
.sess-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  padding: 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s, border-color 0.2s, box-shadow 0.2s;
}
.sess-tab:hover { background: var(--bg-elevated); color: var(--text-primary); }
.sess-tab.active {
  background: var(--bg-elevated);
  color: var(--primary-hover);
  border-color: var(--primary-container-strong);
  box-shadow: 0 1px 2px rgba(31, 35, 41, 0.06);
}
.sess-tab:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--primary-container-strong); }
.sess-tab-count {
  font-size: 10px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
  background: var(--border-base);
  border-radius: 999px;
  padding: 1px 6px;
  min-width: 1.4em;
  text-align: center;
}
.sess-tab.active .sess-tab-count { background: var(--primary-container); color: var(--primary-hover); }

.sess-body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  background: var(--bg-elevated);
}
.sess-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 6px;
  padding: 56px 24px;
  color: var(--text-tertiary);
}
.sess-empty-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: var(--bg-base);
  color: var(--text-secondary);
  display: grid;
  place-items: center;
  margin-bottom: 8px;
}
.sess-empty-icon svg { width: 24px; height: 24px; }
.sess-empty strong { font-size: 13px; font-weight: 700; color: var(--text-secondary); }
.sess-empty span { font-size: 12px; color: var(--text-tertiary); max-width: 220px; line-height: 1.45; }
.sess-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--primary-container-strong);
  border-top-color: var(--primary);
  border-radius: 50%;
  margin-bottom: 8px;
  animation: sess-spin 0.7s linear infinite;
}
@keyframes sess-spin { to { transform: rotate(360deg); } }

.sess-list {
  list-style: none;
  margin: 0;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sess-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border-base);
  border-radius: 12px;
  background: var(--bg-elevated);
  transition: border-color 0.2s, background-color 0.2s;
}
.sess-item:hover { border-color: var(--primary-container-strong); background: var(--primary-container); }
.sess-item-main { min-width: 0; flex: 1; }
.sess-item-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sess-item:hover .sess-item-title { color: var(--primary-hover); }
.sess-item-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  font-size: 11px;
  color: var(--text-tertiary);
}
.sess-item-meta .dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--border-strong);
}
.sess-item-path {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  min-width: 0;
  font-size: 10.5px;
  color: var(--text-tertiary);
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 7px;
  padding: 5px 8px;
}
.sess-item:hover .sess-item-path { border-color: var(--primary-container-strong); }
.sess-item-path svg { width: 12px; height: 12px; flex-shrink: 0; color: var(--text-secondary); }
.sess-item-path code {
  font-family: 'JetBrains Mono', Consolas, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.sess-item-actions {
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex-shrink: 0;
}
.sess-item-actions .btn { min-width: 52px; }

/* —— 抽屉过渡 —— */
.drawer-enter-active, .drawer-leave-active { transition: opacity 0.22s ease; }
.drawer-enter-active .sess-drawer, .drawer-leave-active .sess-drawer { transition: transform 0.22s ease; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .sess-drawer, .drawer-leave-to .sess-drawer { transform: translateX(100%); }

/* —— 响应式 —— */
@media (max-width: 780px) {
  .ide-launchpad { padding: 32px 16px 160px; }
  .grid { grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 6px 10px; }
  .icon, .icon-wrap { width: 60px; height: 60px; }
  .icon { border-radius: 14px; }
  .icon-text { font-size: 18px; }
  .label { font-size: 12px; max-width: 92px; }
  .dock {
    bottom: 12px;
    left: 12px;
    right: 12px;
    transform: none;
    max-width: none;
  }
  .dock-enter-from, .dock-leave-to { transform: translateY(20px); }
  .sess-drawer { width: 100vw; }
}

@media (prefers-reduced-motion: reduce) {
  .spinner, .sess-spinner { animation: none; }
  .dock-enter-active, .dock-leave-active,
  .drawer-enter-active, .drawer-leave-active,
  .drawer-enter-active .sess-drawer, .drawer-leave-active .sess-drawer {
    transition-duration: 0.01ms;
  }
  .item:hover { transform: none; }
  .item:hover .icon { transform: none; }
}
</style>