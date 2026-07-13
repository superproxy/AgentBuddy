<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useSyncStore } from '../stores/sync'
import { useSyncLayoutStore, type SyncBarPlacement } from '../stores/syncLayout'
import { useIdeStore } from '../stores/ide'
import { useUiStore } from '../stores/ui'
import { useCmdStore } from '../stores/cmd'
import { useSubagentStore } from '../stores/subagent'
import { runSse } from '../api/sse'
import { api } from '../api/client'

const props = defineProps<{ tab: string }>()
const sync = useSyncStore()
const layout = useSyncLayoutStore()
const ideStore = useIdeStore()
const cmdStore = useCmdStore()
const subagentStore = useSubagentStore()
const ui = useUiStore()
const { ideList, syncTargetIdes, autoSync, syncing, dragIdeKey, dragOverIdeKey } = storeToRefs(sync)
const { placement, floatPos, floatSize, dragging, hoverZone, headerOffset, expandTick } = storeToRefs(layout)
const { installedIdes } = storeToRefs(ideStore)
const { onIdeDragStart, onIdeDragOver, onIdeDrop, onIdeDragEnd } = sync

type FilterMode = 'all' | 'selected' | 'cn'
type ResizeEdge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
type ScopeKind = 'init-ide' | 'cmd' | 'subagent' | 'rules' | 'hooks'
const filterMode = ref<FilterMode>('all')
const panelRef = ref<HTMLElement | null>(null)
const collapsed = ref(false)

const CN_IDE_KEYS = new Set(['QoderCN', 'TraeCN', 'TraeSoloCN'])
const EDGE_PX = 56

/** tab → 同步范围；含 LLM/MCP/Skills + 命令/Subagent/插件 */
const SCOPE_META: Record<string, { key: string; label: string; kind: ScopeKind }> = {
  env: { key: 'llm', label: 'LLM', kind: 'init-ide' },
  mcp: { key: 'mcp', label: 'MCP', kind: 'init-ide' },
  skill: { key: 'skill', label: 'Skills', kind: 'init-ide' },
  command: { key: 'cmd', label: 'Command', kind: 'cmd' },
  subagent: { key: 'subagent', label: 'Subagent', kind: 'subagent' },
  plugin: { key: 'plugin', label: 'Plugin', kind: 'init-ide' },
  rules: { key: 'rules', label: 'Rules', kind: 'rules' },
  hooks: { key: 'hooks', label: 'Hooks', kind: 'hooks' },
}

const currentScope = computed(() => SCOPE_META[props.tab] ?? null)
const visible = computed(() => props.tab !== 'plugin-build' && props.tab !== 'ide')

/** 「全部」= AIDE 管理页已检测到的已安装 IDE/CLI */
const installedKeySet = computed(() => new Set(installedIdes.value.map((i) => i.key)))
const installedIdeList = computed(() => {
  const fromDetect = ideList.value.filter((ide) => installedKeySet.value.has(ide.key))
  if (fromDetect.length) return fromDetect
  // 检测尚未完成时，回退为空列表（避免误展示全部）
  return []
})

const selectedIdes = computed(() =>
  ideList.value.filter((ide) => syncTargetIdes.value.includes(ide.key)),
)
const previewIdes = computed(() => selectedIdes.value.slice(0, 4))
const previewExtra = computed(() => Math.max(0, selectedIdes.value.length - 4))

const filteredIdes = computed(() => {
  if (filterMode.value === 'selected') {
    return ideList.value.filter((ide) => syncTargetIdes.value.includes(ide.key))
  }
  if (filterMode.value === 'cn') {
    return installedIdeList.value.filter((ide) => CN_IDE_KEYS.has(ide.key))
  }
  return installedIdeList.value
})

const actionHint = computed(() => {
  if (!currentScope.value) return '当前页不支持一键同步'
  if (currentScope.value.kind === 'cmd') return '将同步自定义命令到支持的 IDE'
  if (currentScope.value.kind === 'subagent') return '将同步 Subagent 到支持的 IDE'
  if (currentScope.value.kind === 'rules') return '将同步 Rules 到支持的 IDE'
  if (currentScope.value.kind === 'hooks') return '将同步 Hooks 到支持的 IDE'
  return `个目标将接收当前 ${currentScope.value.label} 配置`
})

/** LLM/MCP/Skills/插件需勾选 IDE；命令/Subagent 走专用 API */
const needsIdeTargets = computed(() => currentScope.value?.kind === 'init-ide')

const canSync = computed(() => {
  if (syncing.value || !currentScope.value) return false
  if (needsIdeTargets.value) return syncTargetIdes.value.length > 0
  return true
})

const execCountLabel = computed(() => {
  if (!currentScope.value) return '—'
  if (currentScope.value.kind === 'cmd' || currentScope.value.kind === 'subagent' || currentScope.value.kind === 'rules' || currentScope.value.kind === 'hooks') return '✓'
  return String(syncTargetIdes.value.length)
})

const isSide = computed(() => placement.value === 'left' || placement.value === 'right')
const isFloat = computed(() => placement.value === 'float')
const placementLabel = computed(() => {
  const map: Record<SyncBarPlacement, string> = {
    top: '顶部停靠',
    bottom: '底部停靠',
    left: '左侧停靠',
    right: '右侧停靠',
    float: '窗口化',
  }
  return map[placement.value]
})

const shellStyle = computed(() => {
  if (isFloat.value) {
    return {
      left: `${floatPos.value.x}px`,
      top: `${floatPos.value.y}px`,
      width: `${floatSize.value.w}px`,
      height: `${floatSize.value.h}px`,
      minWidth: `${layout.MIN_W}px`,
      minHeight: `${layout.MIN_H}px`,
      right: 'auto',
      bottom: 'auto',
      maxHeight: 'none',
    }
  }
  if (placement.value === 'top') {
    return {
      top: `${headerOffset.value}px`,
      left: '0',
      right: '0',
      bottom: 'auto',
      width: '100%',
      height: 'auto',
    }
  }
  if (placement.value === 'bottom') {
    return { top: 'auto', left: '0', right: '0', bottom: '0', width: '100%', height: 'auto' }
  }
  // 左/右：嵌入 Header 下方；收起时变为竖向侧栏
  const sideWidth = collapsed.value ? '44px' : 'min(360px, 92vw)'
  if (placement.value === 'left') {
    return {
      top: `${headerOffset.value}px`,
      left: '0',
      right: 'auto',
      bottom: '0',
      width: sideWidth,
      height: 'auto',
    }
  }
  if (placement.value === 'right') {
    return {
      top: `${headerOffset.value}px`,
      left: 'auto',
      right: '0',
      bottom: '0',
      width: sideWidth,
      height: 'auto',
    }
  }
  return undefined
})

/** 甲板布局由 CSS 容器查询驱动；侧栏强制单列 */
const deckClass = computed(() => {
  if (isSide.value) return 'deck deck--side'
  return 'deck'
})

/** 瓦片网格由容器查询驱动 */
const tileGridClass = computed(() => {
  if (isSide.value) return 'tile-grid tile-grid--side'
  return 'tile-grid'
})

/** 从停靠拖离 / 切到窗口化时，落到最小可用尺寸并跟手定位 */
function enterFloatAtPointer(clientX: number, clientY: number, offsetX: number, offsetY: number) {
  // 收起态拖出窗口化时必须展开，否则 body 仍被 v-show 隐藏
  collapsed.value = false
  const size = layout.resetToMinFloatSize()
  const ox = Math.min(Math.max(24, offsetX), size.w - 24)
  const oy = Math.min(Math.max(16, offsetY), 40)
  const pos = layout.clampFloatPos(clientX - ox, clientY - oy, size.w, size.h)
  layout.setFloatPos(pos.x, pos.y)
  return { size, pos, ox, oy }
}

function isSelected(key: string) {
  return syncTargetIdes.value.includes(key)
}
function isCn(key: string) {
  return CN_IDE_KEYS.has(key)
}
function toggleIde(key: string) {
  const idx = syncTargetIdes.value.indexOf(key)
  if (idx >= 0) syncTargetIdes.value.splice(idx, 1)
  else syncTargetIdes.value.push(key)
}
function selectAll() {
  // 全选当前筛选可见项
  const keys = filteredIdes.value.map((i) => i.key)
  const set = new Set(syncTargetIdes.value)
  keys.forEach((k) => set.add(k))
  syncTargetIdes.value = [...set]
}
function clearAll() {
  syncTargetIdes.value = []
}

async function syncCurrentScope() {
  if (syncing.value) return
  const meta = currentScope.value
  if (!meta) {
    ui.toast('当前页面不支持同步', 'warn')
    return
  }
  if (meta.kind === 'init-ide' && !syncTargetIdes.value.length) {
    ui.toast('请先选择目标 IDE', 'warn')
    return
  }

  syncing.value = true
  ui.clearLog()
  try {
    if (meta.kind === 'cmd') {
      await cmdStore.syncToOpencode()
    } else if (meta.kind === 'subagent') {
      await subagentStore.syncToOpencode()
    } else if (meta.kind === 'rules') {
      const r = await api<{ ok: boolean; count?: number; message?: string; error?: string }>(
        '/api/rules/sync', { method: 'POST' },
      )
      if (r.ok) ui.toast(r.message || `已同步 ${r.count} 个规则`)
      else ui.toast('同步失败: ' + (r.error || ''), 'err')
    } else if (meta.kind === 'hooks') {
      const r = await api<{ ok: boolean; message?: string; error?: string }>(
        '/api/hooks/sync', { method: 'POST' },
      )
      if (r.ok) ui.toast(r.message || '已同步 hooks')
      else ui.toast('同步失败: ' + (r.error || ''), 'err')
    } else {
      for (const ide of syncTargetIdes.value) {
        await runSse(
          '/api/init-ide?ide=' + encodeURIComponent(ide) + '&scope=' + meta.key,
          (line) => ui.appendLog(line),
        )
      }
      ui.toast('同步完成')
    }
  } finally {
    syncing.value = false
  }
}

/* —— 窗口化拖拽 —— */
let dragMode: 'reposition' | 'resize' | null = null
let resizeEdge: ResizeEdge | null = null
let startX = 0
let startY = 0
let originX = 0
let originY = 0
let originW = 0
let originH = 0
let moved = false
let floatW = 860
let floatH = 420
let grabOffsetX = 0
let grabOffsetY = 0

/**
 * 仅在真正靠近四边时吸附；其余区域一律窗口化。
 * 修复：从左/右拖出时不再被「最近边」吸回去。
 */
function resolveZone(clientX: number, clientY: number): SyncBarPlacement {
  const w = window.innerWidth
  const h = window.innerHeight
  if (clientX <= EDGE_PX) return 'left'
  if (clientX >= w - EDGE_PX) return 'right'
  if (clientY <= EDGE_PX) return 'top'
  if (clientY >= h - EDGE_PX) return 'bottom'
  return 'float'
}

function onTitlePointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  const target = e.target as HTMLElement
  if (target.closest('button, a, input, label, .resize-handle')) return

  dragMode = 'reposition'
  moved = false
  startX = e.clientX
  startY = e.clientY
  originX = floatPos.value.x
  originY = floatPos.value.y
  floatW = floatSize.value.w
  floatH = floatSize.value.h

  if (panelRef.value) {
    const rect = panelRef.value.getBoundingClientRect()
    floatW = rect.width
    floatH = rect.height
    grabOffsetX = e.clientX - rect.left
    grabOffsetY = e.clientY - rect.top
  }

  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  window.addEventListener('pointermove', onTitlePointerMove)
  window.addEventListener('pointerup', onTitlePointerUp)
  window.addEventListener('pointercancel', onTitlePointerUp)
}

function onTitlePointerMove(e: PointerEvent) {
  if (dragMode !== 'reposition') return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  if (!moved && Math.hypot(dx, dy) < 4) return
  moved = true

  if (!dragging.value) {
    layout.dragging = true
    // 从停靠态拖出：落到最小尺寸窗口化，跟手移动
    if (placement.value !== 'float') {
      const { size, pos, ox, oy } = enterFloatAtPointer(
        e.clientX,
        e.clientY,
        grabOffsetX,
        grabOffsetY,
      )
      floatW = size.w
      floatH = size.h
      grabOffsetX = ox
      grabOffsetY = oy
      originX = pos.x
      originY = pos.y
      startX = e.clientX
      startY = e.clientY
      layout.setPlacement('float')
    }
  }

  if (placement.value === 'float') {
    const next = layout.clampFloatPos(
      originX + (e.clientX - startX),
      originY + (e.clientY - startY),
      floatSize.value.w,
      floatSize.value.h,
    )
    layout.setFloatPos(next.x, next.y)
  }

  layout.hoverZone = resolveZone(e.clientX, e.clientY)
}

function onTitlePointerUp(e: PointerEvent) {
  window.removeEventListener('pointermove', onTitlePointerMove)
  window.removeEventListener('pointerup', onTitlePointerUp)
  window.removeEventListener('pointercancel', onTitlePointerUp)

  if (dragMode !== 'reposition') return
  dragMode = null

  if (moved) {
    const zone = hoverZone.value ?? resolveZone(e.clientX, e.clientY)
    if (zone === 'float') {
      // 从停靠拖离已在 move 阶段落到最小尺寸；若本就在 float 则保持当前尺寸
      collapsed.value = false
      layout.setPlacement('float')
      const size = layout.clampFloatSize(floatSize.value.w, floatSize.value.h)
      layout.setFloatSize(size.w, size.h)
      const pos = layout.clampFloatPos(floatPos.value.x, floatPos.value.y, size.w, size.h)
      layout.setFloatPos(pos.x, pos.y)
    } else {
      layout.setPlacement(zone)
    }
  }

  layout.dragging = false
  layout.hoverZone = null
}

/* —— 浮窗缩放 —— */
function onResizePointerDown(e: PointerEvent, edge: ResizeEdge) {
  if (!isFloat.value || e.button !== 0) return
  e.preventDefault()
  e.stopPropagation()
  dragMode = 'resize'
  resizeEdge = edge
  startX = e.clientX
  startY = e.clientY
  originX = floatPos.value.x
  originY = floatPos.value.y
  originW = floatSize.value.w
  originH = floatSize.value.h
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  window.addEventListener('pointermove', onResizePointerMove)
  window.addEventListener('pointerup', onResizePointerUp)
  window.addEventListener('pointercancel', onResizePointerUp)
}

function onResizePointerMove(e: PointerEvent) {
  if (dragMode !== 'resize' || !resizeEdge) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  let nextX = originX
  let nextY = originY
  let nextW = originW
  let nextH = originH
  const edge = resizeEdge

  if (edge.includes('e')) nextW = originW + dx
  if (edge.includes('s')) nextH = originH + dy
  if (edge.includes('w')) {
    nextW = originW - dx
    nextX = originX + dx
  }
  if (edge.includes('n')) {
    nextH = originH - dy
    nextY = originY + dy
  }

  const size = layout.clampFloatSize(nextW, nextH)
  // 左边/上边缩放时，若触达最小尺寸则锁定对应坐标
  if (edge.includes('w')) {
    nextX = originX + (originW - size.w)
  }
  if (edge.includes('n')) {
    nextY = originY + (originH - size.h)
  }
  const pos = layout.clampFloatPos(nextX, nextY, size.w, size.h)
  layout.setFloatSize(size.w, size.h)
  layout.setFloatPos(pos.x, pos.y)
}

function onResizePointerUp() {
  window.removeEventListener('pointermove', onResizePointerMove)
  window.removeEventListener('pointerup', onResizePointerUp)
  window.removeEventListener('pointercancel', onResizePointerUp)
  dragMode = null
  resizeEdge = null
}

function snapTo(zone: SyncBarPlacement) {
  if (zone === 'float') {
    // 按钮切到窗口化：使用最小可用尺寸（可再手动放大）
    const size = layout.resetToMinFloatSize()
    const pos = layout.clampFloatPos(
      Math.round(window.innerWidth / 2 - size.w / 2),
      Math.round(window.innerHeight / 2 - size.h / 2),
      size.w,
      size.h,
    )
    layout.setFloatPos(pos.x, pos.y)
  }
  layout.setPlacement(zone)
  collapsed.value = false
}

function toggleCollapse() {
  collapsed.value = !collapsed.value
}

function onKeySnap(e: KeyboardEvent) {
  // 停靠快捷键：Ctrl+Shift + 方向键 / F（窗口化）
  // 找回面板请用顶栏「同步面板」或 Ctrl+Shift+S（在 App 层处理）
  if (!(e.ctrlKey || e.metaKey) || !e.shiftKey || !visible.value) return
  const map: Record<string, SyncBarPlacement> = {
    ArrowUp: 'top',
    ArrowDown: 'bottom',
    ArrowLeft: 'left',
    ArrowRight: 'right',
    KeyF: 'float',
  }
  const zone = map[e.code]
  if (!zone) return
  e.preventDefault()
  collapsed.value = false
  snapTo(zone)
}

let resizeObs: ResizeObserver | null = null

function measureChrome() {
  const header = document.querySelector('header')
  if (header) layout.setHeaderOffset(header.getBoundingClientRect().height)
  // 视口变小时，把浮窗钳回最小尺寸与可视区
  if (placement.value === 'float') {
    const size = layout.clampFloatSize(floatSize.value.w, floatSize.value.h)
    layout.setFloatSize(size.w, size.h)
    const pos = layout.clampFloatPos(floatPos.value.x, floatPos.value.y, size.w, size.h)
    layout.setFloatPos(pos.x, pos.y)
  }
  publishDockSize()
}

function publishDockSize() {
  if (!visible.value || !panelRef.value) {
    layout.setDockSize(0, 0)
    return
  }
  if (placement.value === 'float') {
    layout.setDockSize(0, 0)
    return
  }
  const rect = panelRef.value.getBoundingClientRect()
  layout.setDockSize(rect.width, rect.height)
}

watch(expandTick, () => {
  collapsed.value = false
})

watch([placement, collapsed, visible], async () => {
  await nextTick()
  if (visible.value) layout.recoverVisibility()
  publishDockSize()
})

onMounted(() => {
  // 恢复：清卡住的拖拽态，把飞出视口的浮窗拉回中间
  layout.recoverVisibility()
  collapsed.value = false
  window.addEventListener('keydown', onKeySnap)
  measureChrome()
  window.addEventListener('resize', measureChrome)
  if (panelRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObs = new ResizeObserver(() => publishDockSize())
    resizeObs.observe(panelRef.value)
  }
  publishDockSize()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeySnap)
  window.removeEventListener('resize', measureChrome)
  window.removeEventListener('pointermove', onTitlePointerMove)
  window.removeEventListener('pointerup', onTitlePointerUp)
  window.removeEventListener('pointercancel', onTitlePointerUp)
  window.removeEventListener('pointermove', onResizePointerMove)
  window.removeEventListener('pointerup', onResizePointerUp)
  window.removeEventListener('pointercancel', onResizePointerUp)
  resizeObs?.disconnect()
  layout.setDockSize(0, 0)
})
</script>

<template>
  <!-- 停靠预览层（拖拽时） -->
  <Teleport to="body">
    <div
      v-if="dragging && visible"
      class="dock-overlay"
      aria-hidden="true"
    >
      <div class="dock-zone dock-top" :class="{ active: hoverZone === 'top' }" />
      <div class="dock-zone dock-bottom" :class="{ active: hoverZone === 'bottom' }" />
      <div class="dock-zone dock-left" :class="{ active: hoverZone === 'left' }" />
      <div class="dock-zone dock-right" :class="{ active: hoverZone === 'right' }" />
      <div class="dock-zone dock-center" :class="{ active: hoverZone === 'float' }">
        <div class="dock-center-card">
          <span class="dock-center-title">窗口化</span>
          <span class="dock-center-sub">松手变为可移动窗口</span>
        </div>
      </div>
    </div>
  </Teleport>

  <div
    v-show="visible"
    ref="panelRef"
    class="sync-shell"
    :class="[
      `place-${placement}`,
      {
        'is-float': isFloat,
        'is-side': isSide,
        'is-dragging': dragging,
        'is-collapsed': collapsed,
      },
    ]"
    :style="shellStyle"
    role="complementary"
    aria-label="同步到 IDE"
  >
    <!-- 标题栏 / 拖拽把手（侧栏收起时变为竖向侧轨） -->
    <div
      class="sync-titlebar"
      :class="{ 'sync-titlebar--rail': isSide && collapsed }"
      @pointerdown="onTitlePointerDown"
    >
      <div class="traffic" aria-hidden="true">
        <button
          type="button"
          class="dot close"
          title="收起面板"
          aria-label="收起面板"
          @click.stop="toggleCollapse"
        />
        <button
          type="button"
          class="dot minimize"
          title="切换窗口化"
          aria-label="切换窗口化"
          @click.stop="snapTo(isFloat ? 'top' : 'float')"
        />
        <button
          type="button"
          class="dot zoom"
          title="停靠到顶部"
          aria-label="停靠到顶部"
          @click.stop="snapTo('top')"
        />
      </div>

      <div class="title-center">
        <span class="grab-pips" aria-hidden="true">
          <i /><i /><i /><i /><i /><i />
        </span>
        <span class="title-text">同步面板</span>
        <span v-if="!(isSide && collapsed)" class="title-badge">{{ placementLabel }}</span>
      </div>

      <div class="title-actions">
        <template v-if="!(isSide && collapsed)">
          <button
            type="button"
            class="icon-btn"
            title="左侧停靠"
            aria-label="左侧停靠"
            @click.stop="snapTo('left')"
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1.5" y="2" width="5" height="12" rx="1" /><rect x="8.5" y="2" width="6" height="12" rx="1" opacity=".35" /></svg>
          </button>
          <button
            type="button"
            class="icon-btn"
            title="右侧停靠"
            aria-label="右侧停靠"
            @click.stop="snapTo('right')"
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1.5" y="2" width="6" height="12" rx="1" opacity=".35" /><rect x="9.5" y="2" width="5" height="12" rx="1" /></svg>
          </button>
          <button
            type="button"
            class="icon-btn"
            title="底部停靠"
            aria-label="底部停靠"
            @click.stop="snapTo('bottom')"
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="1.5" width="12" height="6" rx="1" opacity=".35" /><rect x="2" y="9.5" width="12" height="5" rx="1" /></svg>
          </button>
          <button
            type="button"
            class="icon-btn"
            title="窗口化"
            aria-label="窗口化"
            @click.stop="snapTo('float')"
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="10" height="10" rx="1.5" /></svg>
          </button>
        </template>
        <button
          type="button"
          class="icon-btn"
          :title="collapsed ? '展开' : '收起'"
          :aria-label="collapsed ? '展开' : '收起'"
          @click.stop="toggleCollapse"
        >
          <!-- 侧栏收起：左右箭头；其余：上下箭头 -->
          <svg v-if="isSide && collapsed && placement === 'left'" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 4l4 4-4 4" stroke-linecap="round" stroke-linejoin="round" /></svg>
          <svg v-else-if="isSide && collapsed && placement === 'right'" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 4L6 8l4 4" stroke-linecap="round" stroke-linejoin="round" /></svg>
          <svg v-else-if="!collapsed" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 6l4 4 4-4" stroke-linecap="round" stroke-linejoin="round" /></svg>
          <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 10l4-4 4 4" stroke-linecap="round" stroke-linejoin="round" /></svg>
        </button>
      </div>
    </div>

    <!-- 内容 -->
    <div v-show="!collapsed" class="syncbar-body">
      <div class="syncbar-inner" :class="{ 'is-side-inner': isSide }">
        <div class="deck" :class="deckClass">
          <!-- 模式 -->
          <aside class="panel flex flex-col gap-2.5 rounded-xl border border-white/10 bg-white/[0.04] p-3">
            <div class="flex items-center justify-between gap-2">
              <h3 class="m-0 text-[11px] font-bold tracking-[0.08em] uppercase text-white/60">模式</h3>
            </div>
            <div class="flex flex-col gap-2.5 flex-1">
              <div class="flex items-center justify-between gap-2.5">
                <div>
                  <strong class="block text-[13px] font-semibold text-white">自动同步</strong>
                  <span class="block mt-0.5 text-[11px] text-white/60 leading-snug">保存后写入已选 IDE</span>
                </div>
                <label class="sync-toggle inline-flex cursor-pointer shrink-0" title="自动同步">
                  <input v-model="autoSync" type="checkbox" class="sr-only" />
                  <span class="sync-switch" aria-hidden="true" />
                </label>
              </div>
              <div class="scope-block" aria-label="当前同步范围">
                <span class="scope-block__label">同步范围</span>
                <div
                  class="scope-now"
                  :class="{ 'is-empty': !currentScope }"
                  :title="currentScope ? `当前页：${currentScope.label}` : '当前页不支持同步'"
                >
                  <span class="scope-now__dot" aria-hidden="true" />
                  <span class="scope-now__name">{{ currentScope?.label ?? '—' }}</span>
                </div>
              </div>
            </div>
          </aside>

          <!-- 目标 IDE -->
          <div class="panel flex flex-col gap-2.5 rounded-xl border border-white/10 bg-white/[0.04] p-3">
            <div class="flex items-center justify-between gap-2">
              <h3 class="m-0 text-[11px] font-bold tracking-[0.08em] uppercase text-white/60">目标 IDE</h3>
              <span class="font-mono text-[11px] font-semibold text-[#9ec0ff] bg-brand-500/20 px-1.5 py-0.5 rounded-full">
                {{ syncTargetIdes.length }}
              </span>
            </div>

            <div class="flex items-center gap-2 flex-wrap">
              <div class="inline-flex p-0.5 rounded-lg bg-black/30 border border-white/10" role="tablist" aria-label="筛选">
                <button
                  type="button"
                  role="tab"
                  class="filter-tab px-2.5 py-1 rounded-md text-[11px] font-semibold cursor-pointer transition-colors duration-150 border-0"
                  :class="filterMode === 'all' ? 'bg-brand-500/35 text-white' : 'bg-transparent text-white/55 hover:text-white'"
                  :aria-selected="filterMode === 'all'"
                  title="已安装的 IDE / CLI"
                  @click="filterMode = 'all'"
                >全部</button>
                <button
                  type="button"
                  role="tab"
                  class="filter-tab px-2.5 py-1 rounded-md text-[11px] font-semibold cursor-pointer transition-colors duration-150 border-0"
                  :class="filterMode === 'selected' ? 'bg-brand-500/35 text-white' : 'bg-transparent text-white/55 hover:text-white'"
                  :aria-selected="filterMode === 'selected'"
                  @click="filterMode = 'selected'"
                >已选</button>
                <button
                  type="button"
                  role="tab"
                  class="filter-tab px-2.5 py-1 rounded-md text-[11px] font-semibold cursor-pointer transition-colors duration-150 border-0"
                  :class="filterMode === 'cn' ? 'bg-brand-500/35 text-white' : 'bg-transparent text-white/55 hover:text-white'"
                  :aria-selected="filterMode === 'cn'"
                  @click="filterMode = 'cn'"
                >国内版</button>
              </div>
              <button type="button" class="ml-auto text-[11px] font-medium text-[#9ec0ff] hover:text-white cursor-pointer bg-transparent border-0 p-0" @click="selectAll">全选</button>
              <button type="button" class="text-[11px] font-medium text-[#9ec0ff] hover:text-white cursor-pointer bg-transparent border-0 p-0" @click="clearAll">清空</button>
            </div>

            <div
              class="tile-grid"
              :class="tileGridClass"
              role="group"
              aria-label="目标 IDE 列表"
            >
              <button
                v-for="ide in filteredIdes"
                :key="ide.key"
                type="button"
                draggable="true"
                class="ide-tile relative flex flex-col items-start gap-1.5 min-h-[58px] px-2.5 py-2 rounded-[10px] border text-left cursor-grab select-none transition-colors duration-150"
                :class="[
                  isSelected(ide.key)
                    ? 'bg-brand-500/15 border-brand-500/55 text-white selected'
                    : 'bg-white/[0.03] border-white/10 text-white/80 hover:bg-white/[0.07] hover:text-white',
                  dragIdeKey === ide.key ? 'opacity-40' : '',
                  dragOverIdeKey === ide.key && dragIdeKey ? 'ring-1 ring-white/40 bg-white/20' : '',
                ]"
                :aria-pressed="isSelected(ide.key)"
                :title="ide.desc + '（点击选择，拖动排序）'"
                @click="toggleIde(ide.key)"
                @dragstart="onIdeDragStart($event, ide.key)"
                @dragover="onIdeDragOver($event, ide.key)"
                @drop="onIdeDrop($event, ide.key)"
                @dragend="onIdeDragEnd"
              >
                <span class="text-xs font-semibold leading-tight pr-4">{{ ide.label }}</span>
                <span
                  class="font-mono text-[9px] tracking-wide"
                  :class="isSelected(ide.key) ? 'text-[#9ec0ff]/75' : 'text-white/40'"
                >{{ isCn(ide.key) ? 'CN' : 'GLOBAL' }}</span>
              </button>
              <div v-if="!filteredIdes.length" class="col-span-full py-4 text-center text-[12px] text-white/40">
                <template v-if="filterMode === 'selected'">尚未选择目标</template>
                <template v-else-if="filterMode === 'all' && !installedIdeList.length">
                  暂无已安装 IDE/CLI，请先在「AIDE 管理」检测
                </template>
                <template v-else>无匹配项</template>
              </div>
            </div>
          </div>

          <!-- 执行 -->
          <aside class="panel action-panel flex flex-col gap-2.5 justify-between rounded-xl border border-brand-500/30 p-3">
            <div class="flex items-center justify-between gap-2">
              <h3 class="m-0 text-[11px] font-bold tracking-[0.08em] uppercase text-white/60">执行</h3>
            </div>
            <div>
              <div class="font-mono text-[28px] font-semibold tracking-tight text-white leading-none">
                {{ execCountLabel }}
              </div>
              <div class="mt-1 text-[11px] text-white/60">{{ actionHint }}</div>
            </div>
            <div class="flex flex-wrap gap-1 min-h-6">
              <template v-if="needsIdeTargets">
                <template v-if="selectedIdes.length">
                  <span
                    v-for="ide in previewIdes"
                    :key="ide.key"
                    class="inline-flex items-center h-5 px-1.5 rounded-full text-[10px] font-semibold text-[#dbe8ff] bg-brand-500/25 border border-brand-500/35"
                  >{{ ide.label }}</span>
                  <span
                    v-if="previewExtra"
                    class="inline-flex items-center h-5 px-1.5 rounded-full text-[10px] font-semibold text-[#dbe8ff] bg-brand-500/25 border border-brand-500/35"
                  >+{{ previewExtra }}</span>
                </template>
                <span v-else class="text-[11px] text-white/40">尚未选择目标</span>
              </template>
              <span v-else-if="currentScope?.kind === 'cmd'" class="text-[11px] text-white/55">
                OpenCode / Claude / OpenClaw
              </span>
              <span v-else-if="currentScope?.kind === 'subagent'" class="text-[11px] text-white/55">
                OpenCode agents
              </span>
            </div>
            <button
              type="button"
              class="sync-cta inline-flex items-center justify-center gap-2 w-full h-10 rounded-[10px] border-0 text-[13px] font-bold text-white cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="!canSync"
              @click="syncCurrentScope"
            >
              <svg
                v-if="!syncing"
                class="w-[15px] h-[15px]"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                aria-hidden="true"
              >
                <path d="M4 12a8 8 0 0 1 14.9-4M20 12a8 8 0 0 1-14.9 4" stroke-linecap="round" />
                <path d="M19 4v4h-4M5 20v-4h4" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              {{ syncing ? '同步中...' : '同步到 IDE' }}
            </button>
            <div class="text-[10px] text-white/60 text-center leading-snug">
              拖标题栏可停靠四边或窗口化 · Ctrl+Shift+方向键 · 顶栏「同步面板」找回
            </div>
          </aside>
        </div>
      </div>
    </div>

    <!-- 浮窗缩放手柄 -->
    <template v-if="isFloat && !collapsed">
      <div class="resize-handle rh-n" @pointerdown="onResizePointerDown($event, 'n')" />
      <div class="resize-handle rh-s" @pointerdown="onResizePointerDown($event, 's')" />
      <div class="resize-handle rh-e" @pointerdown="onResizePointerDown($event, 'e')" />
      <div class="resize-handle rh-w" @pointerdown="onResizePointerDown($event, 'w')" />
      <div class="resize-handle rh-ne" @pointerdown="onResizePointerDown($event, 'ne')" />
      <div class="resize-handle rh-nw" @pointerdown="onResizePointerDown($event, 'nw')" />
      <div class="resize-handle rh-se" @pointerdown="onResizePointerDown($event, 'se')" />
      <div class="resize-handle rh-sw" @pointerdown="onResizePointerDown($event, 'sw')" />
    </template>
  </div>
</template>

<style scoped>
.sync-shell {
  --sync-glass: rgba(31, 35, 41, 0.94);
  color: #f7f8fa;
  position: fixed;
  z-index: 45;
  overflow: auto;
  transition: box-shadow 200ms ease, border-radius 200ms ease;
  box-sizing: border-box;
}

.sync-shell.is-dragging {
  opacity: 0.96;
  pointer-events: none;
  z-index: 55;
}

.sync-shell.place-float {
  min-width: 480px;
  min-height: 360px;
}

/* 顶部停靠 —— 贴在 Header 下方全宽（top 由 shellStyle 注入） */
.place-top {
  left: 0;
  right: 0;
  width: 100%;
  max-height: min(48vh, 520px);
  background:
    linear-gradient(90deg, rgba(22, 93, 255, 0.14) 0, rgba(22, 93, 255, 0.14) 3px, transparent 3px),
    var(--sync-glass);
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.28);
}

/* 底部停靠 */
.place-bottom {
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  max-height: min(48vh, 520px);
  background:
    linear-gradient(90deg, rgba(22, 93, 255, 0.14) 0, rgba(22, 93, 255, 0.14) 3px, transparent 3px),
    var(--sync-glass);
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 -12px 40px rgba(0, 0, 0, 0.28);
}

/* 左 / 右停靠 —— 嵌入 Header 下方（top 由 shellStyle 注入） */
.place-left,
.place-right {
  width: min(360px, 92vw);
  background: var(--sync-glass);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08), 0 16px 48px rgba(0, 0, 0, 0.28);
}

.place-left {
  border-right: 1px solid rgba(255, 255, 255, 0.1);
}

.place-right {
  border-left: 1px solid rgba(255, 255, 255, 0.1);
}

/* 窗口化 —— Apple Windowed App（宽高由 shellStyle 注入，可缩放） */
.place-float {
  border-radius: 14px;
  background: linear-gradient(160deg, rgba(42, 47, 54, 0.96), rgba(31, 35, 41, 0.94));
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    0 0 0 0.5px rgba(255, 255, 255, 0.06) inset,
    0 28px 80px rgba(0, 0, 0, 0.5),
    0 8px 24px rgba(22, 93, 255, 0.12);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
  z-index: 50;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.place-float .syncbar-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

/* 缩放手柄 */
.resize-handle {
  position: absolute;
  z-index: 6;
  touch-action: none;
}

.rh-n { top: -3px; left: 10px; right: 10px; height: 8px; cursor: ns-resize; }
.rh-s { bottom: -3px; left: 10px; right: 10px; height: 8px; cursor: ns-resize; }
.rh-e { right: -3px; top: 10px; bottom: 10px; width: 8px; cursor: ew-resize; }
.rh-w { left: -3px; top: 10px; bottom: 10px; width: 8px; cursor: ew-resize; }
.rh-ne { top: -3px; right: -3px; width: 14px; height: 14px; cursor: nesw-resize; }
.rh-nw { top: -3px; left: -3px; width: 14px; height: 14px; cursor: nwse-resize; }
.rh-se { bottom: -3px; right: -3px; width: 14px; height: 14px; cursor: nwse-resize; }
.rh-sw { bottom: -3px; left: -3px; width: 14px; height: 14px; cursor: nesw-resize; }

.rh-se::after {
  content: '';
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 8px;
  height: 8px;
  border-right: 2px solid rgba(158, 192, 255, 0.55);
  border-bottom: 2px solid rgba(158, 192, 255, 0.55);
  border-radius: 1px;
  pointer-events: none;
}

.sync-titlebar {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  padding: 6px 10px 6px 12px;
  cursor: grab;
  user-select: none;
  touch-action: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.sync-titlebar:active {
  cursor: grabbing;
}

.traffic {
  display: flex;
  align-items: center;
  gap: 7px;
  flex: none;
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 0;
  padding: 0;
  cursor: pointer;
  opacity: 0.9;
  transition: filter 150ms ease, transform 150ms ease;
}

.dot:hover {
  filter: brightness(1.08);
  transform: scale(1.06);
}

.dot:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.35);
}

.dot.close { background: #ff5f57; }
.dot.minimize { background: #febc2e; }
.dot.zoom { background: #28c840; }

.title-center {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  justify-content: center;
}

.grab-pips {
  display: grid;
  grid-template-columns: repeat(3, 3px);
  gap: 2px;
  opacity: 0.35;
  flex: none;
}

.grab-pips i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #fff;
  display: block;
}

.title-text {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: rgba(255, 255, 255, 0.88);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.title-badge {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 10px;
  font-weight: 600;
  color: #9ec0ff;
  background: rgba(22, 93, 255, 0.2);
  padding: 2px 7px;
  border-radius: 999px;
  white-space: nowrap;
  flex: none;
}

.title-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: none;
  flex-wrap: wrap;
  justify-content: flex-end;
  max-width: 48%;
}

.icon-btn {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: rgba(255, 255, 255, 0.55);
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}

.icon-btn svg {
  width: 14px;
  height: 14px;
}

.icon-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.icon-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.28);
}

.syncbar-body {
  background:
    linear-gradient(90deg, rgba(22, 93, 255, 0.1) 0, rgba(22, 93, 255, 0.1) 3px, transparent 3px),
    transparent;
}

.syncbar-inner {
  max-width: 1600px;
  margin: 0 auto;
  padding: 12px 16px 14px;
  container-type: inline-size;
  container-name: sync-deck;
  min-width: 0;
}

.syncbar-inner.is-side-inner {
  max-width: none;
  padding: 10px 12px 14px;
}

/* —— 自适应甲板：按容器宽度切换列数，避免浮窗缩小时错乱 —— */
.deck {
  display: grid;
  gap: 12px;
  align-items: stretch;
  grid-template-columns: 1fr;
  min-width: 0;
}

.deck > .panel {
  min-width: 0;
  overflow: hidden;
}

.deck--side {
  grid-template-columns: 1fr;
}

@container sync-deck (min-width: 640px) {
  .deck:not(.deck--side) {
    grid-template-columns: 148px minmax(0, 1fr);
  }
  .deck:not(.deck--side) > .action-panel {
    grid-column: 1 / -1;
  }
}

@container sync-deck (min-width: 820px) {
  .deck:not(.deck--side) {
    grid-template-columns: 160px minmax(0, 1fr) 160px;
  }
  .deck:not(.deck--side) > .action-panel {
    grid-column: auto;
  }
}

/* —— 瓦片网格：按容器宽度增减列数 —— */
.tile-grid {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  min-width: 0;
}

.tile-grid--side {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@container sync-deck (min-width: 560px) {
  .tile-grid:not(.tile-grid--side) {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@container sync-deck (min-width: 720px) {
  .tile-grid:not(.tile-grid--side) {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@container sync-deck (min-width: 960px) {
  .tile-grid:not(.tile-grid--side) {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
}

.ide-tile {
  min-width: 0;
  overflow: hidden;
}

.ide-tile .text-xs {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.is-collapsed:not(.is-side) .sync-titlebar {
  border-bottom: 0;
}

/* 左/右收起：竖向侧轨，而不是顶部横条 */
.sync-shell.is-side.is-collapsed {
  overflow: hidden;
}

.sync-titlebar--rail {
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  width: 100%;
  height: 100%;
  min-height: 100%;
  padding: 12px 6px;
  border-bottom: 0;
  cursor: grab;
}

.sync-titlebar--rail .traffic {
  flex-direction: column;
  gap: 8px;
}

.sync-titlebar--rail .title-center {
  flex: 1;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
  writing-mode: vertical-rl;
  text-orientation: mixed;
}

.sync-titlebar--rail .grab-pips {
  writing-mode: horizontal-tb;
  grid-template-columns: repeat(2, 3px);
  grid-template-rows: repeat(3, 3px);
}

.sync-titlebar--rail .title-text {
  font-size: 12px;
  letter-spacing: 0.12em;
  white-space: nowrap;
}

.sync-titlebar--rail .title-actions {
  flex-direction: column;
  max-width: none;
  width: 100%;
  align-items: center;
}

.place-left.is-collapsed {
  border-right: 1px solid rgba(255, 255, 255, 0.12);
}

.place-right.is-collapsed {
  border-left: 1px solid rgba(255, 255, 255, 0.12);
}

/* 控件样式（沿用 Split Deck） */
.sync-toggle:focus-within .sync-switch {
  box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.28);
}

/* —— 同步范围：仅展示当前页 —— */
.scope-block {
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.scope-block__label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.45);
  flex: none;
}

.scope-now {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 28px;
  padding: 0 10px 0 9px;
  border-radius: 8px;
  color: #fff;
  background: rgba(22, 93, 255, 0.18);
  border: 1px solid rgba(22, 93, 255, 0.4);
  box-shadow: inset 3px 0 0 #165dff;
  transition: background 160ms ease, border-color 160ms ease, color 160ms ease;
}

.scope-now__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
  background: #165dff;
  box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.28);
}

.scope-now__name {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1;
}

.scope-now.is-empty {
  color: rgba(255, 255, 255, 0.4);
  background: rgba(0, 0, 0, 0.22);
  border-color: rgba(255, 255, 255, 0.08);
  box-shadow: none;
}

.scope-now.is-empty .scope-now__dot {
  background: rgba(255, 255, 255, 0.25);
  box-shadow: none;
}

@media (prefers-reduced-motion: reduce) {
  .scope-now {
    transition: none !important;
  }
}

.sync-switch {
  width: 40px;
  height: 22px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  position: relative;
  transition: background 180ms ease;
  display: block;
}

.sync-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 180ms ease;
}

.sync-toggle input:checked + .sync-switch {
  background: #165dff;
}

.sync-toggle input:checked + .sync-switch::after {
  transform: translateX(18px);
}

.ide-tile.selected::after {
  content: '';
  position: absolute;
  top: 8px;
  right: 8px;
  width: 14px;
  height: 14px;
  border-radius: 4px;
  background: #165dff
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3'%3E%3Cpath d='M5 12l5 5L20 7' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")
    center / 10px no-repeat;
}

.ide-tile:focus-visible,
.filter-tab:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.28);
}

.action-panel {
  background:
    linear-gradient(160deg, rgba(22, 93, 255, 0.22), rgba(22, 93, 255, 0.05) 55%, transparent),
    rgba(255, 255, 255, 0.04);
}

.sync-cta {
  background: linear-gradient(180deg, #2f72ff 0%, #165dff 45%, #1454e8 100%);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.14) inset,
    0 8px 20px rgba(22, 93, 255, 0.32);
  transition: filter 160ms ease, opacity 160ms ease;
}

.sync-cta:hover:not(:disabled) {
  filter: brightness(1.06);
}

.sync-cta:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.28);
}

.sync-cta:disabled {
  box-shadow: none;
}

@media (prefers-reduced-motion: reduce) {
  .sync-shell,
  .sync-switch,
  .sync-switch::after,
  .ide-tile,
  .sync-cta,
  .filter-tab,
  .dot,
  .icon-btn {
    transition: none !important;
  }
}
</style>

<!-- 停靠预览层：非 scoped，挂到 body -->
<style>
.dock-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  pointer-events: none;
  background: rgba(8, 10, 14, 0.28);
}

.dock-zone {
  position: absolute;
  border-radius: 12px;
  border: 1.5px dashed rgba(158, 192, 255, 0.35);
  background: rgba(22, 93, 255, 0.08);
  transition: background 160ms ease, border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.dock-zone.active {
  background: rgba(22, 93, 255, 0.28);
  border-color: rgba(22, 93, 255, 0.85);
  border-style: solid;
  box-shadow: 0 0 0 1px rgba(22, 93, 255, 0.35), inset 0 0 40px rgba(22, 93, 255, 0.15);
}

.dock-top {
  top: 10px;
  left: 14%;
  right: 14%;
  height: 64px;
}

.dock-bottom {
  bottom: 10px;
  left: 14%;
  right: 14%;
  height: 64px;
}

.dock-left {
  top: 12%;
  bottom: 12%;
  left: 10px;
  width: 64px;
}

.dock-right {
  top: 12%;
  bottom: 12%;
  right: 10px;
  width: 64px;
}

.dock-center {
  top: 50%;
  left: 50%;
  width: min(420px, 56vw);
  height: min(220px, 36vh);
  transform: translate(-50%, -50%);
  display: grid;
  place-items: center;
  border-radius: 16px;
}

.dock-center.active {
  transform: translate(-50%, -50%) scale(1.02);
}

.dock-center-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: #dbe8ff;
  text-align: center;
}

.dock-center-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.dock-center-sub {
  font-size: 11px;
  color: rgba(219, 232, 255, 0.7);
}

@media (prefers-reduced-motion: reduce) {
  .dock-zone {
    transition: none !important;
  }
}
</style>
