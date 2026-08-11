<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted, computed, ref, reactive, watch } from 'vue'
import { useIdeStore } from '../stores/ide'
import { useSyncStore } from '../stores/sync'
import { useUiStore } from '../stores/ui'
import { useBrandOrderStore } from '../stores/brandOrder'

const ide = useIdeStore()
const sync = useSyncStore()
const ui = useUiStore()
const brandOrder = useBrandOrderStore()
const {
  ideDetectStats, ideDetecting, ideInstallInfo, ideInstallInfoLoaded,
  installedIdes, notInstalledIdes, sessionableIdes, showNotInstalled,
  ideInstalling, ideUninstalling, ideReinstalling, ideSyncing,
  ideLaunching, ideResuming, ideOpeningConfig,
  expandedIde, sessionDrawerOpen, expandedIdeCard, ideCardTab,
  ideSessionsMap, ideSessionsStatsMap, ideLoadingSessions,
  exportingSession, shareModalOpen, shareModalSession, shareTargetIde, shareImporting,
  shareTargetIdes,
  brandGroups,
} = storeToRefs(ide)

// 品牌视图下的全局筛选状态
// 一级 chip：品牌（默认 'all' 显示全部）
const activeBrandChip = ref<string>('all')

// 常用品牌排序复用 brandOrder store（常用区 + 更多区 + 后端持久化）
const DEFAULT_BRAND_COUNT = 5
const showMoreBrands = ref(false)

// 品牌拖拽状态
const draggingBrand = ref<string | null>(null)

// 拖拽开始
function onBrandDragStart(e: DragEvent, brand: string) {
  draggingBrand.value = brand
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', brand)
  }
}

// 拖拽经过目标
function onBrandDragOver(e: DragEvent, brand: string) {
  if (draggingBrand.value === null || draggingBrand.value === brand) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
}

// 拖拽放置
function onBrandDrop(e: DragEvent, targetBrand: string) {
  e.preventDefault()
  const src = draggingBrand.value
  if (!src || src === targetBrand) return
  const fromIdx = brandOrder.favoriteKeys.indexOf(src)
  const toIdx = brandOrder.favoriteKeys.indexOf(targetBrand)
  if (fromIdx < 0 || toIdx < 0) return
  const adjusted = fromIdx < toIdx ? toIdx - 1 : toIdx
  brandOrder.moveFavorite(fromIdx, adjusted)
}

// 拖拽结束
function onBrandDragEnd() {
  draggingBrand.value = null
}

// 品牌 chip 选项（列出所有品牌）
const brandChipOptions = computed(() => {
  const chips: Array<{ key: string; label: string }> = [{ key: 'all', label: '全部 AIDE' }]
  for (const bg of brandGroups.value) {
    chips.push({ key: bg.brand, label: bg.brand })
  }
  return chips
})

// 初始化常用品牌（默认取已安装的前 N 个，不足则补未安装的品牌）
const initFavoriteBrands = () => {
  if (brandGroups.value.length === 0) return
  const allBrands = brandGroups.value.map((b) => ({ key: b.brand, label: b.brand }))
  // 默认常用区：优先已安装的品牌
  const installed = brandGroups.value.filter((b) => b.installedCount > 0)
  const notInstalled = brandGroups.value.filter((b) => b.installedCount === 0)
  const defaults = [...installed, ...notInstalled]
    .slice(0, DEFAULT_BRAND_COUNT)
    .map((b) => b.brand)
  brandOrder.init(allBrands, defaults)
}

// 更多品牌（非常用区的品牌）
const moreBrands = computed(() => brandOrder.moreItems)

// 当前显示的品牌 chip（"全部品牌" + 常用品牌，按用户排序）
const visibleBrandChips = computed(() => {
  const allChip = brandChipOptions.value.filter((c) => c.key === 'all')
  const favChips = brandOrder.favoriteKeys
    .map((brand) => brandChipOptions.value.find((c) => c.key === brand))
    .filter((c): c is NonNullable<typeof c> => !!c)
  return [...allChip, ...favChips]
})

// 加入常用区
const addToFavorite = (brand: string) => {
  if (!brandOrder.favoriteKeys.includes(brand)) {
    brandOrder.moveToFavorites(brand)
  }
}

// 移出常用区
const removeFromFavorite = (brand: string) => {
  brandOrder.moveToMore(brand)
  // 如果当前选中的品牌被移出，切回"全部品牌"
  if (activeBrandChip.value === brand) {
    activeBrandChip.value = 'all'
  }
}

// 点击更多品牌项：临时选中该品牌（不加入常用）
const selectMoreBrand = (brand: string) => {
  activeBrandChip.value = brand
  showMoreBrands.value = false
}

// 过滤后的品牌分组（按 activeBrandChip 筛选，Code 和 Work 并列展示）
const filteredBrandGroups = computed(() => {
  const groups = brandGroups.value
    .filter((bg) => activeBrandChip.value === 'all' || bg.brand === activeBrandChip.value)
    .filter((g): g is NonNullable<typeof g> => g !== null)
  // 当显示全部品牌时，按用户自定义顺序排序
  if (activeBrandChip.value === 'all' && brandOrder.favoriteKeys.length > 0) {
    return [...groups].sort((a, b) => {
      const ia = brandOrder.favoriteKeys.indexOf(a.brand)
      const ib = brandOrder.favoriteKeys.indexOf(b.brand)
      // 常用品牌按自定义顺序排前，非常用品牌保持原序
      if (ia >= 0 && ib >= 0) return ia - ib
      if (ia >= 0) return -1
      if (ib >= 0) return 1
      return 0
    })
  }
  return groups
})

// 品牌元数据（前端本地常量，与 stores/ide.ts 同步）
const BRAND_META_LOCAL: Record<string, { vendor: string; color: string; logo: string }> = {
  Kimi:      { vendor: 'Moonshot AI · 月之暗面',  color: '#1a1a2e', logo: 'K' },
  CherryStudio: { vendor: 'Cherry Studio',        color: '#e11d48', logo: 'CS' },
  Claude:    { vendor: 'Anthropic',                color: '#c75d3a', logo: 'Cl' },
  Codex:     { vendor: 'OpenAI',                   color: '#0a8a6a', logo: 'Co' },
  Trae:      { vendor: '字节跳动 · ByteDance',     color: '#e6492d', logo: 'Tr' },
  'Trae CN': { vendor: '字节跳动 · ByteDance (国内版)', color: '#3d4fd6', logo: 'Tr' },
  Qoder:     { vendor: '阿里云 · 通义灵码',        color: '#0a93b3', logo: 'Qo' },
  'Qoder CN': { vendor: '阿里云 · 通义灵码 (国内版)', color: '#0a6b8d', logo: 'QC' },
  ZCode:     { vendor: '智谱 ADE',                 color: '#047857', logo: 'ZC' },
  JetBrains: { vendor: 'JetBrains s.r.o.',         color: '#0a5fc7', logo: 'JB' },
  OpenCode:  { vendor: 'anomalyco',               color: '#4f5cd9', logo: 'OO' },
  OpenClaw:  { vendor: '开源社区',                 color: '#7c5cf0', logo: 'OC' },
  Hermes:    { vendor: '内部 Agent 平台',          color: '#6b7280', logo: 'He' },
  WorkBuddy: { vendor: '腾讯 CodeBuddy · AI 工作台', color: '#dc2626', logo: 'WB' },
  CodeBuddy: { vendor: '腾讯云 · Tencent',          color: '#0052d9', logo: 'CB' },
  Pi:        { vendor: 'earendil-works',           color: '#7c3aed', logo: 'Pi' },
  'Trae Work': { vendor: '字节跳动 · ByteDance',   color: '#f59e0b', logo: 'TW' },
  'Command Code': { vendor: 'Command Code',       color: '#0891b2', logo: 'CC' },
}

// 形式徽章配色
const FORM_META_LOCAL: Record<string, { label: string; color: string; bg: string; border: string }> = {
  cli:       { label: 'CLI',           color: '#c4b5fd', bg: 'rgba(124,92,240,0.15)',  border: 'rgba(124,92,240,0.3)' },
  app:       { label: 'App',           color: '#93c5fd', bg: 'rgba(59,130,246,0.15)',  border: 'rgba(59,130,246,0.3)' },
  vscode:    { label: 'VSCode 插件',   color: '#6ee7b7', bg: 'rgba(16,185,129,0.15)',  border: 'rgba(16,185,129,0.3)' },
  idea: { label: 'IDEA 插件', color: '#fca5a5', bg: 'rgba(239,68,68,0.15)',  border: 'rgba(239,68,68,0.3)' },
  acp:       { label: 'ACP',           color: '#fcd34d', bg: 'rgba(245,158,11,0.15)',  border: 'rgba(245,158,11,0.3)' },
  web:       { label: 'Web',           color: '#34d399', bg: 'rgba(52,211,153,0.15)',  border: 'rgba(52,211,153,0.3)' },
}

// 顶层分类配色
const CATEGORY_META_LOCAL: Record<string, { label: string; color: string; bg: string; border: string }> = {
  code: { label: 'Code', color: '#c4b5fd', bg: 'linear-gradient(135deg, rgba(124,92,240,0.2), rgba(79,92,217,0.2))', border: 'rgba(124,92,240,0.4)' },
  work: { label: 'Work', color: '#fbbf24', bg: 'linear-gradient(135deg, rgba(251,191,36,0.2), rgba(217,119,6,0.2))', border: 'rgba(251,191,36,0.4)' },
}
const { dragIdeKey, dragOverIdeKey } = storeToRefs(sync)
const {
  loadIdeDetect, launchIde, installIde, uninstallIde, reinstallIde, openIdeConfig,
  syncIdeConfig, toggleIdeSessions, closeSessionDrawer, toggleIdeCard, setIdeCardTab, exportSession,
  openShareModal, importSession, openExternal, openIdeUrl,
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
/** form 标签（用于扁平网格中区分 cli/app/vscode 等） */
function formLabel(form: string): string {
  return FORM_META_LOCAL[form]?.label || form
}

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
  if (tab === 'cli') return info.cli
  if (tab === 'app') return info.app
  if (tab === 'vscode') return info.vscode
  if (tab === 'idea') return info.idea
  if (tab === 'acp') return info.acp
  if (tab === 'web') return info.web
  return info.cli || info.app
}

function currentPath(it: any): string {
  const tab = currentTab(it)
  if (tab === 'cli' || tab === 'acp' || tab === 'web') return it.exe_path || ''
  return it.app_path || ''
}

function currentMethod(it: any): string {
  return currentInfo(it)?.method || ''
}

function currentInstalled(it: any): boolean {
  const tab = currentTab(it)
  if (tab === 'cli' || tab === 'acp' || tab === 'web') return !!it.exe_path
  return !!it.app_path
}

function busyKey(it: any): string {
  return it.key + ':' + currentTab(it)
}

/** —— Launchpad 风格新增函数 —— **/

// IDE 品牌色映射（基于方案 C 设计稿）
const IDE_BRAND: Record<string, { from: string; to: string }> = {
  Agents:     { from: '#9ca3af', to: '#6b7280' },
  CherryStudio: { from: '#f43f5e', to: '#e11d48' },
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
const ICON_VERSION = '20260720a'
const iconUrl = (key: string) => `/api/ide/icon/${encodeURIComponent(key)}?v=${ICON_VERSION}`
const iconFailed = (key: string) => !!iconErrors[key]
function onIconError(key: string) {
  iconErrors[key] = true
}

/** IDE 是否支持某安装维度（基于 install info 静态配置） */
function supportsTab(it: any, tab: 'cli' | 'app' | 'vscode' | 'idea' | 'acp' | 'web'): boolean {
  const info = ideInstallInfo.value[it.key]
  if (!info) return false
  if (tab === 'cli') return !!(info.cli && it.cli_names?.length)
  if (tab === 'app') return !!info.app
  if (tab === 'vscode') return !!info.vscode
  if (tab === 'idea') return !!info.idea
  if (tab === 'acp') return !!info.acp
  if (tab === 'web') return !!info.web
  return false
}

/** 条目类型：展开条目用 _tab，未展开条目按唯一支持维度推断 */
function ideType(it: any): 'cli' | 'app' | 'vscode' | 'idea' | 'acp' | 'web' | '' {
  if (it._tab) return it._tab as 'cli' | 'app' | 'vscode' | 'idea' | 'acp' | 'web'
  const tabs: Array<'cli' | 'app' | 'vscode' | 'idea' | 'acp' | 'web'> = ['cli', 'app', 'vscode', 'idea', 'acp', 'web']
  const supported = tabs.filter(t => supportsTab(it, t))
  if (supported.length === 1) return supported[0]
  return ''
}

/** 按维度独立展开条目（cli / app / vscode / jetbrains）。
 * 每个维度各自独立判断：
 *   - 支持 CLI → 生成 cli 条目（app_path 清空）
 *   - 支持 App → 生成 app 条目（exe_path 清空）
 *   - 支持 VSCode → 生成 vscode 条目
 *   - 支持 JetBrains → 生成 jetbrains 条目
 *   - 都不支持 → 单条目（如 Agents，仅配置目录）
 * 每个条目的 installed 由 currentInstalled 按 exe_path/app_path 独立判定。
 */
function expandIde(it: any): any[] {
  const cli = supportsTab(it, 'cli')
  const app = supportsTab(it, 'app')
  const vscode = supportsTab(it, 'vscode')
  const idea = supportsTab(it, 'idea')
  const acp = supportsTab(it, 'acp')
  const web = supportsTab(it, 'web')
  if (!cli && !app && !vscode && !idea && !acp && !web) return [it]
  const entries: any[] = []
  if (cli) {
    entries.push({ ...it, _tab: 'cli', _uid: it.key + ':cli', label: it.label + ' CLI', _expanded: true, app_path: '' })
  }
  if (app) {
    entries.push({ ...it, _tab: 'app', _uid: it.key + ':app', label: it.label + ' App', _expanded: true, exe_path: '' })
  }
  if (vscode) {
    entries.push({ ...it, _tab: 'vscode', _uid: it.key + ':vscode', label: it.label + ' VSCode', _expanded: true, exe_path: '', app_path: '' })
  }
  if (idea) {
    entries.push({ ...it, _tab: 'idea', _uid: it.key + ':idea', label: it.label + ' IDEA', _expanded: true, exe_path: '', app_path: '' })
  }
  if (acp) {
    entries.push({ ...it, _tab: 'acp', _uid: it.key + ':acp', label: it.label + ' ACP', _expanded: true, exe_path: '', app_path: '' })
  }
  if (web) {
    entries.push({ ...it, _tab: 'web', _uid: it.key + ':web', label: it.label + ' Web', _expanded: true, exe_path: '', app_path: '' })
  }
  return entries
}

/** 条目的唯一标识（展开条目用 key:tab，普通条目用 key） */
function ideUid(it: any): string {
  return it._uid || it.key
}

function typeLabel(it: any): string {
  const t = ideType(it)
  if (t === 'cli') return 'CLI'
  if (t === 'app') return 'App'
  if (t === 'vscode') return 'VSCode'
  if (t === 'idea') return 'IDEA'
  if (t === 'acp') return 'ACP'
  if (t === 'web') return 'Web'
  return '—'
}

function sessionCount(it: any): number {
  return ideSessionsStatsMap.value[it.key]?.total || 0
}

// 展开后的全部条目（CLI/App 独立展开），取 ideDetects 全量
const expandedAll = computed(() =>
  [...installedIdes.value, ...notInstalledIdes.value].flatMap(it => expandIde(it))
)
// 已安装/未安装按"每个维度的实际安装状态"独立判定（exe_path / app_path）
const expandedInstalled = computed(() =>
  expandedAll.value.filter(it => currentInstalled(it))
)
const expandedNotInstalled = computed(() =>
  expandedAll.value.filter(it => !currentInstalled(it))
)

/** 当前选中的 IDE 对象（用于 Dock） */
const currentSelectedIde = computed(() => {
  if (!expandedIde.value) return null
  // 优先在展开后的列表里按 _uid 精确查找（both 拆分条目 key:tab）
  const byUid = expandedAll.value.find(i => ideUid(i) === expandedIde.value)
  if (byUid) return byUid
  // 回退：品牌视图点击传入 key:form，展开条目 _uid 也带 :tab 后缀。
  // 拆分出 rawKey 和 form，按 key 匹配并优先选对应 tab 的条目
  const sepIdx = expandedIde.value.indexOf(':')
  const rawKey = sepIdx > -1 ? expandedIde.value.slice(0, sepIdx) : expandedIde.value
  const form = sepIdx > -1 ? expandedIde.value.slice(sepIdx + 1) : ''
  const byKey = expandedAll.value.filter(i => i.key === rawKey)
  if (byKey.length > 0) {
    // 优先选对应 form 的展开条目，其次选已安装的，否则取第一个
    if (form) {
      const byTab = byKey.find(i => i._tab === form)
      if (byTab) return byTab
    }
    return byKey.find(i => currentInstalled(i)) || byKey[0]
  }
  // 最终回退：在原始 detect 列表中按 key 查找
  const raw = [...installedIdes.value, ...notInstalledIdes.value].find(i => i.key === rawKey)
  return raw || null
})

// 进入 AIDE 管理页时自动检测（首次无数据才检测，避免重复请求）
onMounted(async () => {
  if (!ide.ideDetects.length) await loadIdeDetect()
  // 初始化常用品牌（默认前 N 个）
  initFavoriteBrands()
})

// brandGroups 异步加载完成后，如果常用品牌未初始化，自动初始化
watch(
  () => brandGroups.value.length,
  (len) => {
    if (len > 0 && !brandOrder.ready) {
      initFavoriteBrands()
    }
  }
)
</script>

<template>
  <div class="ide-launchpad">
    <!-- 右上角刷新按钮 -->
    <button
      @click="loadIdeDetect"
      :disabled="ideDetecting"
      class="refresh-btn"
      :class="{ 'is-loading': ideDetecting }"
      type="button"
      :title="ideDetecting ? '检测中...' : '重新检测已安装的 IDE'"
    >
      <svg class="refresh-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
      <span>{{ ideDetecting ? '检测中' : '刷新检测' }}</span>
    </button>

    <!-- 加载中 -->
    <div v-if="ideDetecting || !ideInstallInfoLoaded" class="loading">
      <div class="spinner" aria-hidden="true"></div>
      <div>{{ ideDetecting ? '检测 IDE 安装状态...' : '加载安装信息...' }}</div>
    </div>

    <div v-else>
      <!-- ==================== 品牌分组视图 ==================== -->
      <div class="brand-view">
        <!-- 品牌 chip（常用区 + 更多收起，类似工具栏菜单） -->
        <div class="brand-chips">
          <!-- 常用品牌（可拖拽排序，顺序持久化到 localStorage） -->
          <button
            v-for="chip in visibleBrandChips"
            :key="chip.key"
            :class="['brand-chip', { active: activeBrandChip === chip.key, dragging: draggingBrand === chip.key }]"
            :draggable="chip.key !== 'all'"
            @click="activeBrandChip = chip.key"
            @dragstart="chip.key !== 'all' && onBrandDragStart($event, chip.key)"
            @dragover="chip.key !== 'all' && onBrandDragOver($event, chip.key)"
            @drop="chip.key !== 'all' && onBrandDrop($event, chip.key)"
            @dragend="onBrandDragEnd"
            type="button"
          >
            <span class="brand-chip-label">{{ chip.label }}</span>
            <span
              v-if="chip.key !== 'all' && brandOrder.favoriteKeys.length > 1"
              class="brand-chip-remove"
              title="移出常用区"
              @click.stop="removeFromFavorite(chip.key)"
            >×</span>
          </button>

          <!-- 更多收起区 -->
          <div v-if="moreBrands.length > 0" class="brand-more-wrap">
            <button
              type="button"
              :class="['brand-chip brand-more-trigger', { 'brand-more-open': showMoreBrands, 'is-active': moreBrands.includes(activeBrandChip) }]"
              @click="showMoreBrands = !showMoreBrands"
              :aria-expanded="showMoreBrands"
              title="更多品牌"
            >
              <span>更多 {{ moreBrands.length }}</span>
              <svg
                class="brand-more-chev"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
              >
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>

            <!-- 更多下拉面板 -->
            <div v-if="showMoreBrands" class="brand-more-panel" role="menu">
              <div class="brand-more-head">
                <span>更多品牌（点击 + 加入常用区）</span>
              </div>
              <div
                v-for="brand in moreBrands"
                :key="brand"
                role="menuitem"
                :class="['brand-more-item', { 'is-active': activeBrandChip === brand }]"
                @click="selectMoreBrand(brand)"
              >
                <span class="brand-more-label">{{ brand }}</span>
                <button
                  type="button"
                  class="brand-more-add"
                  title="加入常用区"
                  aria-label="加入常用区"
                  @click.stop="addToFavorite(brand)"
                >+</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 品牌卡片列表（扁平网格：B 方案） -->
        <div
          v-for="bg in filteredBrandGroups"
          :key="bg.brand"
          class="brand-card"
        >
          <!-- 品牌卡片头 -->
          <div class="brand-head">
            <div class="brand-logo">
              <span class="brand-logo-text">{{ bg.brandLogo }}</span>
            </div>
            <div class="brand-title">
              <div class="brand-name">{{ bg.brand }}</div>
              <div class="brand-vendor">{{ bg.vendor }}</div>
            </div>
          </div>

          <!-- 扁平网格：直接平铺所有 IDE -->
          <div class="brand-grid">
            <template v-for="cat in bg.categories" :key="cat.category">
              <div
                v-for="fg in cat.forms"
                :key="fg.form"
                class="sub-form-flat"
              >
                <div
                  v-for="it in fg.items"
                  :key="it.key + ':' + fg.form"
                  :class="['item', { 'selected': expandedIde === it.key + ':' + fg.form, 'offline': !it.installed, 'dragging': dragIdeKey === it.key, 'drag-over': dragOverIdeKey === it.key && dragIdeKey !== it.key }]"
                  draggable="true"
                  @click="toggleIdeCard(it.key + ':' + fg.form)"
                  @dragstart="onIdeDragStart($event, it.key)"
                  @dragover="onIdeDragOver($event, it.key)"
                  @drop="onIdeDrop($event, it.key)"
                  @dragend="onIdeDragEnd"
                >
                  <div class="icon-wrap">
                    <div class="icon" :class="{ 'has-img': !iconFailed(it.key) }" :style="iconStyle(it.key)" aria-hidden="true">
                      <img v-if="!iconFailed(it.key)" :src="iconUrl(it.key)" :alt="it.label + ' ' + formLabel(fg.form)" class="icon-img" @error="onIconError(it.key)" draggable="false" />
                      <span v-else class="icon-text">{{ markText(it.label) }}</span>
                    </div>
                    <span v-if="sessionCount(it)" class="badge">{{ sessionCount(it) }}</span>
                  </div>
                  <div class="label" :title="it.label">{{ it.label }}</div>
                  <div v-if="fg.form" class="form-tag" :title="formLabel(fg.form)">{{ formLabel(fg.form) }}</div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- 空状态：当前筛选条件下无 IDE -->
        <div v-if="filteredBrandGroups.length === 0" class="empty-state">
          当前筛选条件下无 IDE
        </div>
      </div>
    </div>

    <!-- 底部 Dock 操作栏：选中 IDE 后浮动显示 -->
    <Transition name="dock">
      <div v-if="currentSelectedIde" class="dock" @click.stop>
        <div class="dock-title">
          <span class="dock-name" :title="currentSelectedIde.label">{{ currentSelectedIde.label }}</span>
          <span v-if="ideType(currentSelectedIde)" :class="['type-tag', ideType(currentSelectedIde)]">{{ typeLabel(currentSelectedIde) }}</span>
        </div>

        <div class="dock-path" :title="currentPath(currentSelectedIde) || (currentInfo(currentSelectedIde) ? '未安装' : '—')">
          <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
          <span @dblclick="copyPath(currentPath(currentSelectedIde))">{{ currentPath(currentSelectedIde) || (currentInfo(currentSelectedIde) ? '未安装' : '—') }}</span>
        </div>

        <div class="dock-actions">
          <!-- ACP 专属按钮：启动 ACP 命令 + 同步到 JetBrains + 打开 IDEA -->
          <template v-if="currentTab(currentSelectedIde) === 'acp'">
            <button @click="launchIde(currentSelectedIde.key, null, 'acp')" :disabled="ideLaunching === currentSelectedIde.key" class="dock-item primary" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              {{ ideLaunching === currentSelectedIde.key ? '...' : '启动 ACP' }}
            </button>
            <button @click="launchIde('IDEA', null, 'app')" :disabled="ideLaunching === 'IDEA'" class="dock-item" type="button" title="打开 IntelliJ IDEA">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              {{ ideLaunching === 'IDEA' ? '...' : '打开 IDEA' }}
            </button>
            <button @click="syncIdeConfig(currentSelectedIde.key)" :disabled="ideSyncing === currentSelectedIde.key" class="dock-item" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
              {{ ideSyncing === currentSelectedIde.key ? '...' : '同步到 JetBrains' }}
            </button>
            <a v-if="currentInfo(currentSelectedIde)?.url" href="javascript:void(0)" @click.prevent="openIdeUrl(currentInfo(currentSelectedIde).url)" class="dock-item">ACP 官网</a>
          </template>
          <!-- Web 专属按钮：启动本地 Web 服务（如 opencode web，默认端口）+ 同步配置 -->
          <template v-else-if="currentTab(currentSelectedIde) === 'web'">
            <button @click="launchIde(currentSelectedIde.key, null, 'web')" :disabled="ideLaunching === currentSelectedIde.key" class="dock-item primary" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              {{ ideLaunching === currentSelectedIde.key ? '...' : '启动 Web' }}
            </button>
            <button @click="syncIdeConfig(currentSelectedIde.key)" :disabled="ideSyncing === currentSelectedIde.key" class="dock-item" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
              {{ ideSyncing === currentSelectedIde.key ? '...' : '同步' }}
            </button>
            <a v-if="currentInfo(currentSelectedIde)?.url" href="javascript:void(0)" @click.prevent="openIdeUrl(currentInfo(currentSelectedIde).url)" class="dock-item">Web 官网</a>
          </template>
          <template v-else-if="currentInstalled(currentSelectedIde)">
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
            <!-- 安装按钮：extension 走 deep link 跳转市场，其他 method 走后端安装，manual 走下载页 -->
            <button v-if="currentMethod(currentSelectedIde) === 'extension'" @click.prevent="openIdeUrl(currentInfo(currentSelectedIde).url)" class="dock-item primary" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/></svg>
              安装插件
            </button>
            <button v-else-if="currentMethod(currentSelectedIde) && currentMethod(currentSelectedIde) !== 'manual'" @click="installIde(currentSelectedIde.key, currentTab(currentSelectedIde))" :disabled="ideInstalling === busyKey(currentSelectedIde)" class="dock-item primary" type="button">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/></svg>
              {{ ideInstalling === busyKey(currentSelectedIde) ? '...' : '安装' }}
            </button>
            <a v-else-if="currentInfo(currentSelectedIde)?.url" href="javascript:void(0)" @click.prevent="openIdeUrl(currentInfo(currentSelectedIde).url)" class="dock-item">下载</a>
            <!-- 打开宿主 IDE：vscode tab → 打开 VSCode 应用；idea tab → 打开 IDEA 应用 -->
            <button v-if="currentTab(currentSelectedIde) === 'vscode'" @click="launchIde('VSCode', null, 'app')" :disabled="ideLaunching === 'VSCode'" class="dock-item" type="button" title="打开 VSCode 编辑器">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              {{ ideLaunching === 'VSCode' ? '...' : '打开 VSCode' }}
            </button>
            <button v-if="currentTab(currentSelectedIde) === 'idea'" @click="launchIde('IDEA', null, 'app')" :disabled="ideLaunching === 'IDEA'" class="dock-item" type="button" title="打开 IntelliJ IDEA">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              {{ ideLaunching === 'IDEA' ? '...' : '打开 IDEA' }}
            </button>
            <button v-if="currentSelectedIde.config_paths?.length" @click="openIdeConfig(currentSelectedIde.key)" :disabled="ideOpeningConfig === currentSelectedIde.key" class="dock-item" type="button">{{ ideOpeningConfig === currentSelectedIde.key ? '...' : '配置' }}</button>
          </template>
          <a v-if="ideInstallInfo[currentSelectedIde.key]?.homepage" href="javascript:void(0)" @click.prevent="openIdeUrl(ideInstallInfo[currentSelectedIde.key].homepage)" class="dock-item">官网</a>
          <button @click="toggleIdeCard(expandedIde)" class="dock-item close" type="button" title="关闭">
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
                  <button v-if="exportingSession !== s.id" @click="exportSession(expandedIde, s)" type="button" class="btn btn-sm btn-ink">导出</button>
                  <button v-else type="button" disabled class="btn btn-sm btn-ink">导出中</button>
                  <button @click="openShareModal(expandedIde, s)" type="button" class="btn btn-sm btn-soft">分享</button>
                  <button @click="launchIde(expandedIde, s, 'cli')" :disabled="ideResuming === s.id || !!ideLaunching" type="button" class="btn btn-sm btn-primary">
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-base);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s, color 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.refresh-btn svg { width: 14px; height: 14px; }
.refresh-btn:hover:not(:disabled) {
  background: var(--bg-base);
  border-color: var(--border-strong);
  color: var(--text-primary);
}
.refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.refresh-btn.is-loading .refresh-icon { animation: spin 0.8s linear infinite; }
@keyframes spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }

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
.type-badge.acp {
  background: linear-gradient(145deg, #f59e0b, #d97706);
  color: #fff;
}
.type-badge.web {
  background: linear-gradient(145deg, #34d399, #10b981);
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
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  text-align: center;
}
.sublabel {
  font-size: 10px;
  color: var(--text-tertiary);
  margin-top: 1px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.form-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  color: var(--text-tertiary);
  background: var(--bg-soft);
  border: 1px solid var(--border-base);
  border-radius: 999px;
  padding: 2px 7px;
  margin-top: 2px;
  max-width: 88px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
.dock-title .type-tag.acp { background: rgba(245, 158, 11, 0.12); color: #d97706; }
.dock-title .type-tag.web { background: rgba(52, 211, 153, 0.12); color: #10b981; }

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

/* ==================== 品牌分组视图样式 ==================== */

/* 品牌视图容器 — 竖排堆叠，品牌内水平排列 */
.brand-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 品牌 chip（常用区 + 更多收起） */
.brand-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--border-base);
}
.brand-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border-base);
  background: transparent;
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 500;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s;
}
.brand-chip:hover { color: var(--text-secondary); border-color: var(--border-strong); }
.brand-chip.active {
  background: var(--text-primary);
  color: var(--bg-base);
  border-color: var(--text-primary);
}
.brand-chip.dragging {
  opacity: 0.4;
  cursor: grabbing;
}
.brand-chip[draggable="true"]:not(.dragging) {
  cursor: grab;
}
.brand-chip-label { line-height: 1; }

/* 移出按钮（×） */
.brand-chip-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: inherit;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  margin-left: 2px;
  margin-right: -4px;
  transition: background 0.15s;
}
.brand-chip-remove:hover {
  background: rgba(255, 80, 80, 0.4);
}
.brand-chip:not(.active) .brand-chip-remove {
  background: var(--border-base);
  color: var(--text-tertiary);
}
.brand-chip:not(.active) .brand-chip-remove:hover {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

/* 更多收起区 */
.brand-more-wrap {
  position: relative;
}
.brand-more-trigger {
  background: transparent !important;
  color: var(--text-tertiary) !important;
  border: 1px dashed var(--border-strong) !important;
}
.brand-more-trigger:hover {
  color: var(--text-secondary) !important;
  border-color: var(--text-tertiary) !important;
}
.brand-more-trigger.is-active {
  color: var(--text-primary) !important;
  border-color: var(--text-primary) !important;
  border-style: solid !important;
}
.brand-more-trigger.brand-more-open .brand-more-chev {
  transform: rotate(180deg);
}
.brand-more-chev {
  width: 12px;
  height: 12px;
  transition: transform 0.2s;
}

/* 更多下拉面板 */
.brand-more-panel {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 200px;
  max-width: 320px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
  padding: 6px;
  z-index: 50;
}
.brand-more-head {
  font-size: 11px;
  color: var(--text-tertiary);
  padding: 4px 8px 6px;
  border-bottom: 1px dashed var(--border-base);
  margin-bottom: 4px;
}
.brand-more-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: background 0.12s;
}
.brand-more-item:hover {
  background: var(--bg-soft);
}
.brand-more-item.is-active {
  background: rgba(59, 130, 246, 0.12);
  color: #2563eb;
}
.brand-more-label { line-height: 1; }
.brand-more-add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: var(--border-base);
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.12s;
}
.brand-more-add:hover {
  background: #10b981;
  color: #fff;
}

/* 品牌卡片内 Code/Work 并列布局 */
.cat-row {
  display: flex;
  flex-direction: row;
  gap: 16px;
  flex-wrap: wrap;
}
@media (max-width: 900px) {
  .cat-row { flex-direction: column; }
}
.cat-col {
  min-width: 0;
  flex: 1 1 320px;
}
/* 品牌视图下 cat-col 为 flex row，让所有 sub-form 横向排列 */
.brand-view .cat-col {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
}
.brand-view .sub-form {
  flex-shrink: 0;
}
.cat-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px dashed var(--border-base);
}
.cat-head .line { flex: 1; height: 1px; background: var(--border-base); }
.cat-badge {
  padding: 3px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid;
}

/* 空状态 */
.empty-state {
  padding: 40px 20px;
  text-align: center;
  color: #6b7280;
  font-size: 13px;
}

/* 品牌大卡片 —— 透明背景，继承 .ide-launchpad 的 --bg-base */
.brand-card {
  background: transparent;
  border: 1px solid var(--border-base);
  border-radius: 14px;
  padding: 16px;
}
.brand-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-base);
  margin-bottom: 10px;
}
.brand-logo {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  background: transparent;
  border: 1px solid var(--border-base);
}
.brand-logo-text {
  font-size: 16px;
  font-weight: 800;
  color: var(--text-secondary);
  letter-spacing: -0.02em;
}
.brand-title { flex: 1; min-width: 0; }
.brand-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.2;
}
.brand-vendor {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}
.brand-stats {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.brand-stats .stat {
  padding: 3px 10px;
  border-radius: 999px;
  background: transparent;
  border: 1px solid var(--border-base);
  font-size: 11px;
  color: var(--text-tertiary);
}
.brand-stats .stat .num {
  color: var(--text-secondary);
  font-weight: 600;
  margin-right: 4px;
}
.brand-stats .stat.installed {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.25);
  color: #059669;
}
.brand-stats .stat.installed .num { color: #059669; }

/* 顶层分类（Code/Work）—— 不再使用，保留兼容 */
.brand-foot {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border-base);
  text-align: center;
}

/* B 方案：扁平网格 */
.brand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
  gap: 30px;
}
.sub-form-flat {
  display: contents;
}
.top-form { margin: 10px 0 8px; }
.top-form-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

/* 子形式分组（cli/app/vscode/idea） */
.sub-form {
  margin: 8px 0;
  padding-left: 12px;
  border-left: 2px solid var(--border-base);
}
.sub-form-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 6px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.sub-form-head .line { flex: 1; height: 1px; background: var(--border-base); }
.sub-form-head .count { color: var(--text-quaternary); font-size: 11px; }
.sub-form-name { color: var(--text-tertiary); }

/* 品牌视图下复用 .type-icon 的原配色（与经典视图一致） */
.brand-view .type-icon {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  flex-shrink: 0;
}
.brand-view .type-icon svg { width: 11px; height: 11px; }
.brand-view .type-icon.cli { background: rgba(16, 185, 129, 0.12); color: #059669; }
.brand-view .type-icon.app { background: rgba(59, 130, 246, 0.12); color: #2563eb; }
.brand-view .type-icon.vscode { background: rgba(16, 185, 129, 0.12); color: #059669; }
.brand-view .type-icon.idea { background: rgba(139, 92, 246, 0.12); color: #7c3aed; }
.brand-view .type-icon.other { background: var(--border-base); color: var(--text-tertiary); }

/* 品牌视图下的 type-badge 复用原 .type-badge 配色 */
.brand-view .type-badge.vscode { background: linear-gradient(145deg, #3b82f6, #2563eb); color: #fff; }
.brand-view .type-badge.idea { background: linear-gradient(145deg, #8b5cf6, #7c3aed); color: #fff; }
.brand-view .type-badge.acp { background: linear-gradient(145deg, #f59e0b, #d97706); color: #fff; }
.brand-view .type-badge.web { background: linear-gradient(145deg, #34d399, #10b981); color: #fff; }

/* 品牌视图下的 grid 横排排列 */
.brand-view .grid {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 8px;
}
.brand-view .item {
  padding: 12px 8px;
  flex: 0 0 auto;
  width: 96px;
}
.brand-view .item .icon-wrap .icon {
  width: 72px;
  height: 72px;
  font-size: 22px;
}
.brand-view .item .label {
  font-size: 12px;
}
.brand-view .item .sublabel {
  font-size: 10px;
}
</style>