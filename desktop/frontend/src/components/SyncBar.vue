<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useSyncStore } from '../stores/sync'
import { useIdeStore } from '../stores/ide'
import { useUiStore } from '../stores/ui'
import { useCmdStore } from '../stores/cmd'
import { useSubagentStore } from '../stores/subagent'
import { runSse } from '../api/sse'
import { api, llmApi } from '../api/client'

const props = defineProps<{ tab: string }>()
const sync = useSyncStore()
const ideStore = useIdeStore()
const cmdStore = useCmdStore()
const subagentStore = useSubagentStore()
const ui = useUiStore()
const { ideList, syncTargetIdes, autoSync, syncing } = storeToRefs(sync)
const { installedIdes } = storeToRefs(ideStore)
const { onIdeDragStart, onIdeDragOver, onIdeDrop, onIdeDragEnd } = sync

type FilterMode = 'all' | 'selected' | 'cn'
type ScopeKind = 'init-ide' | 'cmd' | 'subagent' | 'rules' | 'hooks' | 'memory'
const filterMode = ref<FilterMode>('all')

/** 目标 IDE 浮层显隐 */
const popoverOpen = ref(false)
const popoverRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLElement | null>(null)

const CN_IDE_KEYS = new Set(['QoderCN', 'TraeCN', 'TraeSoloCN'])

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
  memory: { key: 'memory', label: '记忆', kind: 'memory' },
}

const currentScope = computed(() => SCOPE_META[props.tab] ?? null)
const visible = computed(
  () =>
    props.tab !== 'plugin-build' &&
    props.tab !== 'ide' &&
    props.tab !== 'marketplace' &&
    props.tab !== 'terminal' &&
    props.tab !== 'token' &&
    !!SCOPE_META[props.tab],
)

/** 「全部」= AIDE 管理页已检测到的已安装 IDE/CLI */
const installedKeySet = computed(() => new Set(installedIdes.value.map((i) => i.key)))
const installedIdeList = computed(() => {
  const fromDetect = ideList.value.filter((ide) => installedKeySet.value.has(ide.key))
  if (fromDetect.length) return fromDetect
  return []
})

const selectedIdes = computed(() =>
  ideList.value.filter((ide) => syncTargetIdes.value.includes(ide.key)),
)
const previewIdes = computed(() => selectedIdes.value.slice(0, 3))
const previewExtra = computed(() => Math.max(0, selectedIdes.value.length - 3))

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
  if (currentScope.value.kind === 'memory') return '将同步记忆到支持的 IDE'
  return `将同步 ${currentScope.value.label} 配置到 ${selectedIdes.value.length} 个 IDE`
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
  if (['cmd', 'subagent', 'rules', 'hooks', 'memory'].includes(currentScope.value.kind)) return '✓'
  return String(syncTargetIdes.value.length)
})

/** 头像背景色（按 IDE key 稳定映射） */
const AVATAR_COLORS: Record<string, string> = {
  TraeCN: 'linear-gradient(135deg, #ff6b6b, #ee5a52)',
  TraeSoloCN: 'linear-gradient(135deg, #ff6b6b, #ee5a52)',
  QoderCN: 'linear-gradient(135deg, #5b8def, #3b6fd4)',
  Cursor: 'linear-gradient(135deg, #5d3fd3, #4b2eb8)',
  Codex: 'linear-gradient(135deg, #10a37f, #0e8a6b)',
  OpenCode: 'linear-gradient(135deg, #6b7280, #4b5563)',
  Claude: 'linear-gradient(135deg, #d97757, #b85c3d)',
}
function avatarStyle(key: string) {
  return AVATAR_COLORS[key] || 'linear-gradient(135deg, #86909c, #4e5969)'
}
function avatarText(label: string) {
  return label.charAt(0).toUpperCase()
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
  const keys = filteredIdes.value.map((i) => i.key)
  const set = new Set(syncTargetIdes.value)
  keys.forEach((k) => set.add(k))
  syncTargetIdes.value = [...set]
}
function clearAll() {
  syncTargetIdes.value = []
}

function togglePopover() {
  if (!popoverOpen.value) {
    // 打开前先计算位置
    nextTick(() => updatePopoverStyle())
  }
  popoverOpen.value = !popoverOpen.value
  if (popoverOpen.value) {
    nextTick(() => updatePopoverStyle())
  }
}

/** 浮层位置：跟随 trigger 元素，定位到其左下方 */
const popoverStyle = ref<Record<string, string>>({})
function updatePopoverStyle() {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  const POP_W = 340
  const MARGIN = 8
  let left = rect.left
  // 防止溢出右侧
  if (left + POP_W + MARGIN > window.innerWidth) {
    left = window.innerWidth - POP_W - MARGIN
  }
  popoverStyle.value = {
    left: `${Math.max(MARGIN, left)}px`,
    top: `${rect.bottom + 6}px`,
  }
}

/** 点击浮层外部关闭 */
function onDocClick(e: MouseEvent) {
  if (!popoverOpen.value) return
  const t = e.target as Node
  if (popoverRef.value?.contains(t)) return
  if (triggerRef.value?.contains(t)) return
  popoverOpen.value = false
}

/** 直接设置同步模式 */
function setAutoSync(v: boolean) {
  autoSync.value = v
}

async function validateDefaultLlmSelection(targetIdes: string[]): Promise<boolean> {
  if (!targetIdes.some((ide) => ide === 'Codex' || ide === 'Claude')) return true

  const response = await llmApi.fetch()
  const config = response.data as Record<string, any>
  const llm = config.llm && typeof config.llm === 'object' ? config.llm : {}
  const gatewayEnabled = Boolean(config.proxy?.gateway?.enabled)
  const activeProvider = typeof llm._active_provider === 'string' ? llm._active_provider.trim() : ''
  const activeModel = typeof llm._active_model === 'string' ? llm._active_model.trim() : ''

  if (gatewayEnabled === Boolean(activeProvider)) {
    ui.toast('同步 Codex/Claude 前必须选择且只能选择一个默认 LLM Provider 或 LLM 网关', 'warn')
    return false
  }
  if (activeProvider) {
    const provider = llm[activeProvider]
    if (!provider || typeof provider !== 'object' || provider._enabled === false) {
      ui.toast(`默认 LLM Provider「${activeProvider}」不存在或未启用，请重新选择`, 'warn')
      return false
    }
  }
  if (!activeModel) {
    ui.toast('同步 Codex/Claude 前必须选择默认模型', 'warn')
    return false
  }
  return true
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
  if (meta.kind === 'init-ide' && meta.key === 'llm') {
    try {
      if (!(await validateDefaultLlmSelection(syncTargetIdes.value))) return
    } catch (error: any) {
      ui.toast(error?.message || '读取 LLM 配置失败', 'err')
      return
    }
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
        '/api/rules/sync',
        { method: 'POST' },
      )
      if (r.ok) ui.toast(r.message || `已同步 ${r.count} 个规则`)
      else ui.toast('同步失败: ' + (r.error || ''), 'err')
    } else if (meta.kind === 'hooks') {
      const r = await api<{ ok: boolean; message?: string; error?: string }>('/api/hooks/sync', {
        method: 'POST',
      })
      if (r.ok) ui.toast(r.message || '已同步 hooks')
      else ui.toast('同步失败: ' + (r.error || ''), 'err')
    } else if (meta.kind === 'memory') {
      const r = await api<{ ok: boolean; message?: string; error?: string }>('/api/memory/sync', {
        method: 'POST',
      })
      if (r.ok) ui.toast(r.message || '已同步记忆')
      else ui.toast('同步失败: ' + (r.error || ''), 'err')
    } else {
      for (const ide of syncTargetIdes.value) {
        let syncError = ''
        await runSse(
          '/api/sync?ide=' + encodeURIComponent(ide) + '&scope=' + meta.key,
          (line) => {
            ui.appendLog(line)
            const exitMatch = line.match(/^\[EXIT\]\s+returncode=(\d+)/)
            if (exitMatch && exitMatch[1] !== '0') syncError = line
            if (line.startsWith('[ERROR]') || line.startsWith('[TIMEOUT]')) syncError = line
          },
          { onError: () => { syncError = '连接中断' } },
        )
        if (syncError) throw new Error(`${ide}: ${syncError}`)
      }
      ui.toast('同步完成')
    }
  } finally {
    syncing.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocClick)
})
</script>

<template>
  <!-- 方案 D · 内联工具栏：放弃面板形态，压缩为 Header 下方 44px 工具栏 -->
  <div v-if="visible" class="sync-wrapper">
    <div class="sync-toolbar">
    <!-- 目标 IDE 触发器：头像组 + 数量 + caret -->
    <div
      v-if="needsIdeTargets"
      class="target-trigger"
      ref="triggerRef"
      @click="togglePopover"
      :title="actionHint"
    >
      <div class="avatars" v-if="selectedIdes.length">
        <div
          v-for="ide in previewIdes"
          :key="ide.key"
          class="avatar"
          :style="{ background: avatarStyle(ide.key) }"
        >
          {{ avatarText(ide.label) }}
        </div>
        <div v-if="previewExtra > 0" class="avatar more">+{{ previewExtra }}</div>
      </div>
      <div class="avatars" v-else>
        <div class="avatar empty">?</div>
      </div>
      <span class="label">{{ selectedIdes.length }} 个目标</span>
      <svg class="caret" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M3 5l3 3 3-3" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </div>

    <!-- 非 IDE 目标（cmd/subagent/rules/hooks）：显示动作描述 -->
    <span v-else class="target-hint">{{ actionHint }}</span>

    <div class="tb-sep"></div>

    <!-- 同步按钮 + 自动开关 -->
    <div class="sync-combo" :class="{ auto: autoSync }">
      <button
        class="sync-cta"
        :disabled="!canSync || autoSync"
        :title="autoSync ? '自动模式下，保存即触发同步' : '点击立即同步'"
        @click="syncCurrentScope"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <path d="M4 12a8 8 0 0 1 14.9-4M20 12a8 8 0 0 1-14.9 4" stroke-linecap="round" />
          <path d="M19 4v4h-4M5 20v-4h4" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        {{ autoSync ? '自动同步中' : '点击同步' }}
        <span class="count">{{ execCountLabel }}</span>
      </button>
      <button
        class="auto-toggle"
        :class="{ on: autoSync }"
        :title="autoSync ? '点击关闭自动同步' : '点击开启自动同步'"
        @click="setAutoSync(!autoSync)"
      >
        <span class="auto-dot"></span>
        <span class="auto-label">{{ autoSync ? '已自动' : '自动' }}</span>
      </button>
    </div>

    <!-- 目标 IDE 下拉浮层 -->
    <Teleport to="body">
      <div
        v-if="popoverOpen && needsIdeTargets"
        ref="popoverRef"
        class="target-popover"
        :style="popoverStyle"
      >
        <div class="pop-head">
          <span class="pop-title">
            同步 {{ currentScope?.label }} 配置到 IDE
          </span>
          <div class="pop-actions">
            <a @click="selectAll">全选</a>
            <a @click="clearAll">清空</a>
          </div>
        </div>
        <div class="pop-filter">
          <button class="ft" :class="{ active: filterMode === 'all' }" @click="filterMode = 'all'">
            全部
          </button>
          <button
            class="ft"
            :class="{ active: filterMode === 'selected' }"
            @click="filterMode = 'selected'"
          >
            已选
          </button>
          <button
            class="ft"
            :class="{ active: filterMode === 'cn' }"
            @click="filterMode = 'cn'"
          >
            国内版
          </button>
        </div>
        <div class="pop-grid">
          <div
            v-for="ide in filteredIdes"
            :key="ide.key"
            class="pop-item"
            :class="{ selected: isSelected(ide.key) }"
            @click="toggleIde(ide.key)"
            draggable="true"
            @dragstart="onIdeDragStart($event, ide.key)"
            @dragover.prevent="onIdeDragOver($event, ide.key)"
            @drop="onIdeDrop($event, ide.key)"
            @dragend="onIdeDragEnd"
          >
            <span class="check"></span>
            <span
              class="av"
              :style="{ background: avatarStyle(ide.key) }"
            >{{ avatarText(ide.label) }}</span>
            <span class="name">{{ ide.label }}</span>
            <span v-if="isCn(ide.key)" class="tag">CN</span>
          </div>
          <div v-if="!filteredIdes.length" class="pop-empty">暂无已安装 IDE</div>
        </div>
      </div>
    </Teleport>
    </div>
  </div>
</template>

<style scoped>
/* —— 同步容器：内联到 Header actions 区 —— */
.sync-wrapper {
  display: inline-flex;
}

/* —— 内联工具栏：胶囊容器，把 IDE 选择 + 同步 + 自动 视觉上合为一体 —— */
.sync-toolbar {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 4px 3px 6px;
  background: var(--bg-sunken);
  border: 1px solid var(--border-base);
  border-radius: 10px;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', sans-serif;
  font-size: 12px;
  color: var(--text-primary);
  transition: border-color 0.18s, box-shadow 0.18s;
}
.sync-toolbar:hover {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.08);
}

/* —— 范围 chip —— */
.scope-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--primary-container);
  color: var(--primary);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.scope-chip .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
}

/* —— 竖分隔线 —— */
.divider-v {
  width: 1px;
  height: 16px;
  background: var(--border-base);
  flex-shrink: 0;
}

/* —— 目标触发器 —— */
.target-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 4px 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  color: var(--text-secondary);
}
.target-trigger:hover {
  background: var(--bg-hover);
}
.target-trigger .avatars {
  display: inline-flex;
}
.target-trigger .avatar {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid var(--bg-syncbar);
  display: grid;
  place-items: center;
  font-size: 9px;
  font-weight: 700;
  color: #fff;
  margin-left: -5px;
}
.target-trigger .avatar:first-child {
  margin-left: 0;
}
.target-trigger .avatar.more {
  background: var(--text-tertiary);
}
.target-trigger .avatar.empty {
  background: var(--border-base);
  color: var(--text-tertiary);
}
.target-trigger .label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}
.target-trigger .caret {
  width: 10px;
  height: 10px;
  opacity: 0.5;
}

/* —— 非 IDE 目标提示 —— */
.target-hint {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}

/* —— 合成元素：模式分段 + 同步按钮 —— */
.sync-combo {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

/* 同步按钮 */
.sync-combo .sync-cta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px;
  background: var(--primary);
  color: var(--primary-on);
  border: none;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  font-family: inherit;
  border-radius: 7px;
  transition: background 0.2s;
  white-space: nowrap;
}
.sync-combo .sync-cta:hover:not(:disabled) {
  background: var(--primary-hover);
}
.sync-combo.auto .sync-cta {
  background: var(--border-strong);
  cursor: not-allowed;
  box-shadow: none;
  opacity: 0.7;
}
.sync-combo.auto .sync-cta:disabled {
  opacity: 0.7;
}
.sync-combo .sync-cta svg {
  width: 12px;
  height: 12px;
}
.sync-combo .sync-cta .count {
  background: rgba(255, 255, 255, 0.25);
  padding: 0 5px;
  border-radius: 999px;
  font-size: 10px;
  min-width: 14px;
  text-align: center;
}

/* 自动开关 */
.auto-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 8px 5px 6px;
  background: transparent;
  border: none;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  cursor: pointer;
  font-family: inherit;
  transition: all 0.18s;
  white-space: nowrap;
}
/* 未开启时 hover：提示可开启 */
.auto-toggle:not(.on):hover {
  background: var(--primary-container);
  color: var(--primary);
}
.auto-toggle:not(.on):hover .auto-dot {
  background: var(--primary);
}
.auto-toggle .auto-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-tertiary);
  transition: all 0.18s;
}
.auto-toggle .auto-label {
  transition: opacity 0.18s;
}
/* 已开启状态 */
.auto-toggle.on {
  background: var(--primary-container);
  color: var(--primary);
}
.auto-toggle.on .auto-dot {
  background: var(--primary);
  box-shadow: 0 0 0 2px rgba(22, 93, 255, 0.2);
}
/* 已开启时 hover：显示取消选中状态（警示色） */
.auto-toggle.on:hover {
  background: rgba(255, 77, 79, 0.1);
  color: #e5484d;
  border-color: transparent;
}
.auto-toggle.on:hover .auto-dot {
  background: #e5484d;
  box-shadow: 0 0 0 2px rgba(229, 72, 77, 0.2);
}
.auto-toggle.on:hover .auto-label::before {
  content: '✕ ';
  font-size: 10px;
}

.tb-sep {
  width: 1px;
  height: 18px;
  background: var(--border-base);
  margin: 0 2px;
  flex-shrink: 0;
}

/* —— 目标 IDE 浮层 —— */
.target-popover {
  position: fixed;
  z-index: 100;
  width: 340px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  padding: 12px;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', sans-serif;
}
.pop-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.pop-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
}
.pop-actions {
  display: flex;
  gap: 8px;
}
.pop-actions a {
  font-size: 11px;
  color: var(--primary);
  text-decoration: none;
  cursor: pointer;
  user-select: none;
}
.pop-actions a:hover {
  text-decoration: underline;
}

.pop-filter {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--bg-sunken);
  border-radius: 7px;
  margin-bottom: 10px;
}
.pop-filter .ft {
  padding: 3px 8px;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
  cursor: pointer;
  background: transparent;
  border: none;
  transition: all 0.15s;
}
.pop-filter .ft.active {
  background: var(--bg-elevated);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.pop-grid {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 280px;
  overflow-y: auto;
}
.pop-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 7px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  transition: background 0.1s;
}
.pop-item:hover {
  background: var(--bg-hover);
}
.pop-item.selected {
  background: var(--primary-container);
  color: var(--text-primary);
}
.pop-item .check {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1.5px solid var(--border-strong);
  flex-shrink: 0;
  position: relative;
  transition: background 0.15s, border-color 0.15s;
}
.pop-item.selected .check {
  background: var(--primary);
  border-color: var(--primary);
}
.pop-item.selected .check::after {
  content: '';
  position: absolute;
  left: 3px;
  top: 1px;
  width: 4px;
  height: 7px;
  border: solid #fff;
  border-width: 0 1.5px 1.5px 0;
  transform: rotate(45deg);
}
.pop-item .av {
  width: 18px;
  height: 18px;
  border-radius: 5px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  font-size: 9px;
  font-weight: 700;
  color: #fff;
}
.pop-item .name {
  flex: 1;
  font-weight: 600;
}
.pop-item .tag {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--bg-sunken);
  color: var(--text-tertiary);
}
.pop-empty {
  padding: 24px 8px;
  text-align: center;
  font-size: 11px;
  color: var(--text-tertiary);
}
</style>
