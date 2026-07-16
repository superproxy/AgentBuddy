<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'
import { useIdeStore } from '../stores/ide'
import { useSyncStore } from '../stores/sync'

const ide = useIdeStore()
const sync = useSyncStore()
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

function markText(label: string): string {
  const words = label.split(/\s+/).filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  return label.slice(0, 2)
}

function currentTab(it: any): string {
  const t = ideCardTab.value[it.key]
  if (t) return t
  const info = ideInstallInfo.value[it.key]
  if (!info) return 'cli'
  // 无 CLI（exe_path 为空）→ 默认 App tab
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

// 进入 AIDE 管理页时自动检测（首次无数据才检测，避免重复请求）
onMounted(() => {
  if (!ide.ideDetects.length) loadIdeDetect()
})
</script>

<template>
  <div class="ide-tile-view">
    <!-- Hero -->
    <section class="hero" aria-label="舰队概览">
      <div class="hero-main">
        <div class="eyebrow">
          <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
          AIDE 管理
          <span class="live">{{ ideDetecting ? '检测中' : '检测完成' }}</span>
        </div>
        <h2>你的 AI IDE 舰队一览</h2>
        <p>每个 IDE 一张磁贴：安装状态、CLI / App、会话与常用操作一眼可见。</p>
      </div>
      <div class="hero-side">
        <div class="meters" role="group" aria-label="检测统计">
          <div class="meter" aria-label="总计">
            <b>{{ ideDetectStats.total }}</b>
            <span><span class="d" aria-hidden="true"></span>总计</span>
          </div>
          <div class="meter ok" aria-label="已安装">
            <b>{{ ideDetectStats.installed }}</b>
            <span><span class="d" aria-hidden="true"></span>已安装</span>
          </div>
          <div class="meter muted" aria-label="未安装">
            <b>{{ ideDetectStats.not_installed }}</b>
            <span><span class="d" aria-hidden="true"></span>未安装</span>
          </div>
        </div>
        <button @click="loadIdeDetect" :disabled="ideDetecting" class="btn btn-sm btn-ink" type="button">
          <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          {{ ideDetecting ? '检测中' : '重新检测' }}
        </button>
      </div>
    </section>

    <!-- 加载中 -->
    <div v-if="ideDetecting || !ideInstallInfoLoaded" class="loading">
      <div class="spinner" aria-hidden="true"></div>
      <div>{{ ideDetecting ? '检测 IDE 安装状态...' : '加载安装信息...' }}</div>
    </div>

    <div v-else>
      <!-- 已安装 -->
      <div v-if="installedIdes.length" class="section">
        <h3>已安装</h3>
        <span class="count">{{ installedIdes.length }}</span>
      </div>
      <div v-if="installedIdes.length" class="grid">
        <article v-for="it in installedIdes" :key="it.key" class="tile" :class="{ 'dragging': dragIdeKey === it.key, 'drag-over': dragOverIdeKey === it.key && dragIdeKey !== it.key }" draggable="true" @dragstart="onIdeDragStart($event, it.key)" @dragover="onIdeDragOver($event, it.key)" @drop="onIdeDrop($event, it.key)" @dragend="onIdeDragEnd">
          <div class="tile-top">
            <div class="mark" aria-hidden="true">{{ markText(it.label) }}</div>
            <span class="status-pill"><span class="d" aria-hidden="true"></span>已安装</span>
          </div>
          <div class="tile-body">
            <div class="tile-title-row">
              <h3>{{ it.label }}</h3>
              <div class="ver">
                <span>{{ it.version || '—' }}</span>
                <span v-if="currentMethod(it)"> · {{ currentMethod(it) }}</span>
                <span v-if="it.type === 'non-ide'" class="nonide-badge">非IDE</span>
              </div>
            </div>
            <div class="tags">
              <button v-if="ideInstallInfo[it.key]?.cli && it.exe_path" @click="setIdeCardTab(it.key, 'cli')"
                :class="['tag', 'cli', { active: currentTab(it) === 'cli' }]" type="button">
                <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                CLI
              </button>
              <button v-if="ideInstallInfo[it.key]?.app" @click="setIdeCardTab(it.key, 'app')"
                :class="['tag', 'app', { active: currentTab(it) === 'app' }]" type="button">
                <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
                App
              </button>
              <button v-if="it.sessions_dir" @click="toggleIdeSessions(it.key)" :disabled="!!ideLoadingSessions"
                class="tag sess" type="button">
                <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
                {{ ideLoadingSessions === it.key ? '...' : '会话' }}<span v-if="ideSessionsStatsMap[it.key]" class="sess-count">{{ ideSessionsStatsMap[it.key].total }}</span>
              </button>
            </div>
            <div class="path" :title="currentPath(it) || (currentInfo(it) ? '未安装' : '—')">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
              <span>{{ currentPath(it) || (currentInfo(it) ? '未安装' : '—') }}</span>
            </div>
          </div>
          <div class="tile-foot">
            <template v-if="currentInstalled(it)">
              <button @click="launchIde(it.key, null, currentTab(it))" :disabled="ideLaunching === it.key || !!ideResuming" class="btn btn-sm btn-primary" type="button">
                <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                {{ ideLaunching === it.key ? '...' : '打开' }}
              </button>
              <button @click="syncIdeConfig(it.key)" :disabled="ideSyncing === it.key" class="btn btn-sm btn-soft" type="button">{{ ideSyncing === it.key ? '...' : '同步' }}</button>
              <button v-if="it.config_paths?.length" @click="openIdeConfig(it.key)" :disabled="ideOpeningConfig === it.key" class="btn btn-sm btn-ink" type="button">{{ ideOpeningConfig === it.key ? '...' : '配置' }}</button>
              <button v-if="currentMethod(it) && currentMethod(it) !== 'manual'" @click="reinstallIde(it.key, currentTab(it))" :disabled="ideReinstalling === busyKey(it)" class="btn btn-sm btn-amber" type="button">{{ ideReinstalling === busyKey(it) ? '...' : '重装' }}</button>
              <button v-if="currentMethod(it) && currentMethod(it) !== 'manual'" @click="uninstallIde(it.key, currentTab(it))" :disabled="ideUninstalling === busyKey(it)" class="btn btn-sm btn-red" type="button">{{ ideUninstalling === busyKey(it) ? '...' : '卸载' }}</button>
              <button v-if="currentMethod(it) && currentMethod(it) !== 'manual'" @click="uninstallIde(it.key, currentTab(it), true)" :disabled="ideUninstalling === busyKey(it) + ':force'" class="btn btn-sm btn-red" type="button" title="跳过系统卸载程序，直接强删目录">{{ ideUninstalling === busyKey(it) + ':force' ? '...' : '强删' }}</button>
            </template>
            <template v-else>
              <button v-if="currentMethod(it) && currentMethod(it) !== 'manual'" @click="installIde(it.key, currentTab(it))" :disabled="ideInstalling === busyKey(it)" class="btn btn-sm btn-primary" type="button">{{ ideInstalling === busyKey(it) ? '...' : '安装' }}</button>
              <a v-else-if="currentInfo(it)?.url" :href="currentInfo(it).url" target="_blank" class="btn btn-sm btn-ink">下载</a>
              <button v-if="it.config_paths?.length" @click="openIdeConfig(it.key)" :disabled="ideOpeningConfig === it.key" class="btn btn-sm btn-ink" type="button">{{ ideOpeningConfig === it.key ? '...' : '配置' }}</button>
            </template>
            <a v-if="ideInstallInfo[it.key]?.homepage" :href="ideInstallInfo[it.key].homepage" target="_blank" class="btn btn-sm btn-ink">官网</a>
          </div>
        </article>
      </div>

      <!-- 未安装 -->
      <div v-if="notInstalledIdes.length" class="section">
        <h3>未安装</h3>
        <span class="count">{{ notInstalledIdes.length }}</span>
      </div>
      <div v-if="notInstalledIdes.length" class="grid">
        <article v-for="it in notInstalledIdes" :key="it.key" class="tile offline" :class="{ 'dragging': dragIdeKey === it.key, 'drag-over': dragOverIdeKey === it.key && dragIdeKey !== it.key }" draggable="true" @dragstart="onIdeDragStart($event, it.key)" @dragover="onIdeDragOver($event, it.key)" @drop="onIdeDrop($event, it.key)" @dragend="onIdeDragEnd">
          <div class="tile-top">
            <div class="mark" aria-hidden="true">{{ markText(it.label) }}</div>
            <span class="status-pill off"><span class="d" aria-hidden="true"></span>未安装</span>
          </div>
          <div class="tile-body">
            <div class="tile-title-row">
              <h3>{{ it.label }}</h3>
              <div class="ver">未检测到安装</div>
            </div>
            <div class="tags">
              <span v-if="ideInstallInfo[it.key]?.cli && it.cli_names?.length" class="tag cli">
                <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                CLI
              </span>
              <span v-if="ideInstallInfo[it.key]?.app" class="tag app">
                <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
                App
              </span>
              <span v-if="(!ideInstallInfo[it.key]?.cli || !it.cli_names?.length) && !ideInstallInfo[it.key]?.app" class="tag none">可安装</span>
            </div>
            <div class="path">
              <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/></svg>
              <span>点击安装或下载获取</span>
            </div>
          </div>
          <div class="tile-foot">
            <button v-if="ideInstallInfo[it.key]?.cli && it.cli_names?.length && ideInstallInfo[it.key]?.cli?.method !== 'manual'" @click="installIde(it.key, 'cli')" :disabled="ideInstalling === it.key + ':cli'" class="btn btn-sm btn-primary" type="button">{{ ideInstalling === it.key + ':cli' ? '...' : '安装 CLI' }}</button>
            <a v-else-if="ideInstallInfo[it.key]?.cli?.url && it.cli_names?.length" :href="ideInstallInfo[it.key]?.cli?.url" target="_blank" class="btn btn-sm btn-ink">下载 CLI</a>
            <button v-if="ideInstallInfo[it.key]?.app && ideInstallInfo[it.key]?.app?.method !== 'manual'" @click="installIde(it.key, 'app')" :disabled="ideInstalling === it.key + ':app'" class="btn btn-sm btn-primary" type="button">{{ ideInstalling === it.key + ':app' ? '...' : '安装 App' }}</button>
            <a v-else-if="ideInstallInfo[it.key]?.app?.url" :href="ideInstallInfo[it.key]?.app?.url" target="_blank" class="btn btn-sm btn-ink">下载 App</a>
            <a v-if="ideInstallInfo[it.key]?.homepage" :href="ideInstallInfo[it.key]?.homepage" target="_blank" class="btn btn-sm btn-ink">官网</a>
          </div>
        </article>
      </div>
    </div>

    <!-- 会话管理抽屉 -->
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
              v-for="it in sessionableIdes" :key="it.key"
              type="button" role="tab"
              :aria-selected="expandedIde === it.key"
              :class="['sess-tab', expandedIde === it.key && 'active']"
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
                  <button
                    type="button"
                    class="btn btn-sm btn-primary"
                    :disabled="ideResuming === (expandedIde + ':' + s.id) || !!ideLaunching"
                    @click="launchIde(expandedIde, s, ideCardTab[expandedIde] || 'cli')"
                  >{{ ideResuming === (expandedIde + ':' + s.id) ? '...' : '继续' }}</button>
                  <button
                    type="button"
                    class="btn btn-sm btn-ink"
                    :disabled="exportingSession === s.id"
                    @click="exportSession(expandedIde, s)"
                  >{{ exportingSession === s.id ? '...' : '导出' }}</button>
                  <button type="button" class="btn btn-sm btn-purple" @click="openShareModal(expandedIde, s)">共享</button>
                </div>
              </li>
            </ul>
          </div>
        </aside>
      </div>
    </Transition>

    <!-- 共享会话 Modal -->
    <div v-if="shareModalOpen" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="shareModalOpen = false">
      <div class="bg-white rounded-lg p-5 w-[500px] max-w-[90vw]">
        <h3 class="text-sm font-semibold mb-3">共享会话到其他 IDE</h3>
        <div v-if="shareModalSession" class="text-xs space-y-2 mb-3">
          <div><span class="text-ink-400">源 IDE:</span> {{ shareModalSession._source_ide }}</div>
          <div><span class="text-ink-400">会话:</span> {{ shareModalSession.title || shareModalSession.id.slice(0, 12) }}</div>
          <div><span class="text-ink-400">消息数:</span> {{ shareModalSession.messages_count }}</div>
        </div>
        <div class="mb-3">
          <label class="text-xs text-ink-500 block mb-1">选择目标 IDE</label>
          <select v-model="shareTargetIde" class="w-full px-2 py-1.5 text-xs border border-ink-300 rounded-md">
            <option value="">-- 选择 --</option>
            <option v-for="t in shareTargetIdes" :key="t.key" :value="t.key">{{ t.label }}</option>
          </select>
          <div v-if="!shareTargetIdes.length" class="text-[10px] text-orange-500 mt-1">无可用目标 IDE（需已安装且有会话目录）</div>
        </div>
        <div class="text-right">
          <button @click="shareModalOpen = false" class="px-3 py-1.5 text-xs bg-ink-100 rounded hover:bg-ink-300 mr-2">取消</button>
          <button @click="importSession" :disabled="!shareTargetIde || shareImporting" class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded hover:bg-brand-600 disabled:opacity-40">{{ shareImporting ? '共享中...' : '确认共享' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ide-tile-view {
  --brand-50: #eef4ff;
  --brand-100: #d9e6ff;
  --brand-500: #165dff;
  --brand-600: #0e42d2;
  --brand-700: #0a2e9c;
  --ink-100: #f7f8fa;
  --ink-200: #e5e6eb;
  --ink-300: #c9cdd4;
  --ink-500: #86909c;
  --ink-600: #6b7280;
  --ink-700: #4e5969;
  --ink-900: #1f2329;
  --green: #00b42a;
  --green-bg: #e8ffea;
  --amber: #ff7d00;
  --amber-bg: #fff7e8;
  --red: #f53f3f;
  --red-bg: #ffece8;
  --blue-soft: #e8f3ff;
  --blue-text: #0e42d2;
  --purple: #722ed1;
  --purple-bg: #f5e8ff;
  --shadow-sm: 0 1px 2px rgba(31, 35, 41, 0.04);
  --shadow: 0 1px 2px rgba(31, 35, 41, 0.04), 0 4px 16px rgba(31, 35, 41, 0.06);
  --shadow-hover: 0 4px 8px rgba(22, 93, 255, 0.06), 0 12px 28px rgba(22, 93, 255, 0.1);
  --radius-card: 16px;
  --radius-ctl: 8px;
  --ring: 0 0 0 3px rgba(22, 93, 255, 0.28);
}

/* Hero */
.hero {
  margin-bottom: 24px;
  background: #fff;
  border: 1px solid var(--ink-200);
  border-radius: 16px;
  padding: 22px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  box-shadow: var(--shadow-sm);
}
.hero-main { min-width: 0; flex: 1; }
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--brand-600);
  margin-bottom: 8px;
}
.eyebrow svg { width: 13px; height: 13px; }
.eyebrow::after {
  content: "";
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--ink-300);
  margin: 0 2px;
}
.eyebrow .live {
  color: var(--ink-500);
  font-weight: 500;
}
.hero-main h2 {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.3;
  color: var(--ink-900);
}
.hero-main p {
  font-size: 13px;
  color: var(--ink-500);
  margin-top: 6px;
  line-height: 1.5;
  max-width: 36em;
}
.hero-side {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.meters {
  display: flex;
  align-items: stretch;
  gap: 0;
  background: var(--ink-100);
  border-radius: 12px;
  padding: 4px;
}
.meter {
  min-width: 88px;
  padding: 10px 16px;
  border-radius: 9px;
  text-align: left;
}
.meter.ok {
  background: #fff;
  box-shadow: 0 1px 2px rgba(31, 35, 41, 0.06);
}
.meter b {
  display: block;
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
  line-height: 1;
  color: var(--ink-900);
}
.meter.ok b { color: var(--green); }
.meter.muted b { color: var(--ink-500); }
.meter span {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 7px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-500);
}
.meter span .d {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--ink-300);
}
.meter.ok span .d {
  background: var(--green);
  box-shadow: 0 0 0 2px rgba(0, 180, 42, 0.18);
}

/* Loading */
.loading {
  text-align: center;
  padding: 48px 16px;
  color: var(--ink-500);
  font-size: 13px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.spinner {
  width: 24px;
  height: 24px;
  border: 2.5px solid var(--brand-100);
  border-top-color: var(--brand-500);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Section */
.section {
  margin: 28px 0 14px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.section h3 {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-500);
  white-space: nowrap;
}
.section .count {
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-500);
  background: #fff;
  border: 1px solid var(--ink-200);
  padding: 2px 8px;
  border-radius: 999px;
}
.section::after {
  content: "";
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, var(--ink-300), transparent);
}

/* Grid */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(268px, 1fr));
  gap: 16px;
}

/* Tile */
.tile {
  background: #fff;
  border-radius: var(--radius-card);
  border: 1px solid var(--ink-200);
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.tile:hover {
  border-color: var(--brand-100);
  box-shadow: var(--shadow-hover);
}
.tile:focus-within {
  border-color: var(--brand-500);
  box-shadow: var(--shadow-hover), var(--ring);
}
.tile.offline {
  background: #fafbfc;
  border-style: dashed;
  border-color: var(--ink-300);
}
.tile.offline:hover {
  border-color: var(--ink-500);
  box-shadow: var(--shadow);
}
.tile-top {
  padding: 18px 18px 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}
.mark {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(145deg, var(--brand-500) 0%, var(--brand-700) 100%);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 15px;
  letter-spacing: -0.02em;
  box-shadow: 0 4px 12px rgba(22, 93, 255, 0.28);
  position: relative;
}
.mark::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.18), transparent 55%);
  pointer-events: none;
}
.tile.offline .mark {
  background: linear-gradient(145deg, var(--ink-300), var(--ink-500));
  box-shadow: none;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--green-bg);
  color: var(--green);
  border: 1px solid #b7f0c2;
}
.status-pill .d {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 3px rgba(0, 180, 42, 0.15);
}
.status-pill.off {
  background: var(--ink-100);
  color: var(--ink-500);
  border-color: var(--ink-200);
}
.status-pill.off .d {
  box-shadow: none;
}
.tile-body {
  padding: 14px 18px 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.tile-title-row {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.tile-body h3 {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ink-900);
}
.ver {
  font-size: 12px;
  color: var(--ink-500);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.nonide-badge {
  background: var(--ink-200);
  color: var(--ink-600);
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 700;
}
.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 700;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid transparent;
  letter-spacing: 0.01em;
  cursor: default;
}
.tag svg {
  width: 11px;
  height: 11px;
}
.tag.cli {
  background: var(--blue-soft);
  color: var(--blue-text);
  border-color: #cce0ff;
}
.tag.app {
  background: var(--purple-bg);
  color: var(--purple);
  border-color: #e4ccff;
}
.tag.sess {
  background: var(--amber-bg);
  color: var(--amber);
  border-color: #ffe0b8;
  cursor: pointer;
  transition: filter 0.2s;
}
.tag.sess:hover {
  filter: brightness(0.97);
}
.tag.sess:disabled {
  opacity: 0.5;
  cursor: wait;
}
.tag.sess:focus-visible {
  outline: none;
  box-shadow: var(--ring);
}
.tag.cli.active {
  background: var(--brand-500);
  color: #fff;
  border-color: var(--brand-600);
}
.tag.app.active {
  background: var(--purple);
  color: #fff;
  border-color: #5a1fb8;
}
.sess-count {
  opacity: 0.8;
  margin-left: 1px;
}
.tag.none {
  background: var(--ink-100);
  color: var(--ink-600);
  border-color: var(--ink-200);
}
.tile.dragging {
  opacity: 0.4;
  cursor: grabbing;
}
.tile.drag-over {
  border-color: var(--ink-400, #6b7280);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
}
.path {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 10.5px;
  color: var(--ink-600);
  background: var(--ink-100);
  border: 1px solid var(--ink-200);
  padding: 8px 10px;
  border-radius: 8px;
  min-width: 0;
}
.path svg {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: var(--ink-500);
}
.path span {
  overflow-x: auto;
  white-space: nowrap;
  min-width: 0;
  cursor: text;
  user-select: text;
  scrollbar-width: thin;
  padding-bottom: 2px;
}
.tile-foot {
  margin-top: auto;
  padding: 12px 14px;
  border-top: 1px solid var(--ink-100);
  background: linear-gradient(180deg, #fafbfc 0%, #fff 100%);
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.tile.offline .tile-foot {
  background: #f7f8fa;
}

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid transparent;
  border-radius: var(--radius-ctl);
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s, color 0.2s, box-shadow 0.2s;
  line-height: 1.2;
  text-decoration: none;
}
.btn svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}
.btn:focus-visible {
  outline: none;
  box-shadow: var(--ring);
}
.btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--brand-500);
  color: #fff;
}
.btn-primary:hover {
  background: var(--brand-600);
}
.btn-soft {
  background: var(--brand-50);
  color: var(--brand-600);
  border-color: var(--brand-100);
}
.btn-soft:hover {
  background: var(--brand-100);
}
.btn-ink {
  background: #fff;
  color: var(--ink-700);
  border-color: var(--ink-200);
}
.btn-ink:hover {
  background: var(--ink-100);
  border-color: var(--ink-300);
}
.btn-amber {
  background: var(--amber-bg);
  color: var(--amber);
  border-color: #ffe4c2;
}
.btn-amber:hover {
  filter: brightness(0.97);
}
.btn-red {
  background: var(--red-bg);
  color: var(--red);
  border-color: #ffd4cc;
}
.btn-red:hover {
  filter: brightness(0.97);
}
.btn-purple {
  background: var(--purple-bg);
  color: var(--purple);
  border-color: #e8d4ff;
}
.btn-purple:hover {
  filter: brightness(0.97);
}
.btn-sm {
  padding: 6px 10px;
  font-size: 11px;
  border-radius: 7px;
}
.btn-sm svg {
  width: 12px;
  height: 12px;
}

/* —— Session drawer —— */
.sess-overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  justify-content: flex-end;
  background: rgba(31, 35, 41, 0.36);
  backdrop-filter: blur(2px);
}
.sess-drawer {
  width: 440px;
  max-width: 92vw;
  height: 100%;
  background: #fff;
  border-left: 1px solid var(--ink-200);
  box-shadow: -8px 0 32px rgba(31, 35, 41, 0.1);
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
  border-bottom: 1px solid var(--ink-200);
  background: #fff;
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
  background: var(--brand-50);
  color: var(--brand-600);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.sess-head-icon svg {
  width: 18px;
  height: 18px;
}
.sess-head-text {
  min-width: 0;
}
.sess-head-text h2 {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-900);
  letter-spacing: -0.02em;
  line-height: 1.3;
}
.sess-head-text p {
  margin-top: 3px;
  font-size: 12px;
  color: var(--ink-500);
  line-height: 1.4;
}
.sess-close {
  width: 32px;
  height: 32px;
  border: 1px solid var(--ink-200);
  background: #fff;
  border-radius: 8px;
  color: var(--ink-500);
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background-color 0.2s, border-color 0.2s, color 0.2s;
}
.sess-close svg {
  width: 16px;
  height: 16px;
}
.sess-close:hover {
  background: var(--ink-100);
  color: var(--ink-900);
  border-color: var(--ink-300);
}
.sess-close:focus-visible {
  outline: none;
  box-shadow: var(--ring);
}

.sess-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ink-200);
  background: var(--ink-100);
  flex-shrink: 0;
}
.sess-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--ink-600);
  font-size: 12px;
  font-weight: 600;
  padding: 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s, border-color 0.2s, box-shadow 0.2s;
}
.sess-tab:hover {
  background: #fff;
  color: var(--ink-900);
}
.sess-tab.active {
  background: #fff;
  color: var(--brand-600);
  border-color: var(--brand-100);
  box-shadow: 0 1px 2px rgba(31, 35, 41, 0.06);
}
.sess-tab:focus-visible {
  outline: none;
  box-shadow: var(--ring);
}
.sess-tab-count {
  font-size: 10px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--ink-500);
  background: var(--ink-100);
  border-radius: 999px;
  padding: 1px 6px;
  min-width: 1.4em;
  text-align: center;
}
.sess-tab.active .sess-tab-count {
  background: var(--brand-50);
  color: var(--brand-600);
}

.sess-body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  background: #fff;
}
.sess-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 6px;
  padding: 56px 24px;
  color: var(--ink-500);
}
.sess-empty-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: var(--ink-100);
  color: var(--ink-300);
  display: grid;
  place-items: center;
  margin-bottom: 8px;
}
.sess-empty-icon svg {
  width: 24px;
  height: 24px;
}
.sess-empty strong {
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-700);
}
.sess-empty span {
  font-size: 12px;
  color: var(--ink-500);
  max-width: 220px;
  line-height: 1.45;
}
.sess-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--brand-100);
  border-top-color: var(--brand-500);
  border-radius: 50%;
  margin-bottom: 8px;
  animation: sess-spin 0.7s linear infinite;
}
@keyframes sess-spin {
  to { transform: rotate(360deg); }
}

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
  border: 1px solid var(--ink-200);
  border-radius: 12px;
  background: #fff;
  transition: border-color 0.2s, background-color 0.2s;
}
.sess-item:hover {
  border-color: var(--brand-100);
  background: var(--brand-50);
}
.sess-item-main {
  min-width: 0;
  flex: 1;
}
.sess-item-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-900);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sess-item:hover .sess-item-title {
  color: var(--brand-700);
}
.sess-item-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  font-size: 11px;
  color: var(--ink-500);
}
.sess-item-meta .dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--ink-300);
}
.sess-item-path {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  min-width: 0;
  font-size: 10.5px;
  color: var(--ink-500);
  background: #fff;
  border: 1px solid var(--ink-200);
  border-radius: 7px;
  padding: 5px 8px;
}
.sess-item:hover .sess-item-path {
  border-color: var(--brand-100);
}
.sess-item-path svg {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: var(--ink-400, var(--ink-500));
}
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
.sess-item-actions .btn {
  min-width: 52px;
}

/* Drawer transition */
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.22s ease;
}
.drawer-enter-active .sess-drawer,
.drawer-leave-active .sess-drawer {
  transition: transform 0.22s ease;
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from .sess-drawer,
.drawer-leave-to .sess-drawer {
  transform: translateX(100%);
}

@media (prefers-reduced-motion: reduce) {
  .sess-spinner { animation: none; }
  .drawer-enter-active,
  .drawer-leave-active,
  .drawer-enter-active .sess-drawer,
  .drawer-leave-active .sess-drawer {
    transition-duration: 0.01ms;
  }
}

/* Responsive */
@media (max-width: 780px) {
  .hero {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
    padding: 18px;
  }
  .hero-side {
    flex-direction: column;
    align-items: stretch;
  }
  .meters {
    width: 100%;
  }
  .meter {
    flex: 1;
    min-width: 0;
    text-align: center;
  }
  .meter span {
    justify-content: center;
  }
  .hero-side .btn {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
</style>

