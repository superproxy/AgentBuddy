<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount, computed } from 'vue'
import { useThemeStore } from '../stores/theme'
import { useUpgradeStore } from '../stores/upgrade'
import { useNavOrderStore } from '../stores/navOrder'

interface TabItem {
  key: string
  label: string
}

const props = defineProps<{ tab: string; tabs: TabItem[]; defaultFavoriteKeys: string[] }>()
const emit = defineEmits<{
  (e: 'update:tab', v: string): void
}>()

const theme = useThemeStore()
const appVersion = ref('')
const buildTime = ref('')

const upgrade = useUpgradeStore()
const upgradeOpen = ref(false)

const nav = useNavOrderStore()

// ============ 拖拽状态 ============
// dragZone: 'fav' | 'more' — 当前正在拖拽的源区域
const dragZone = ref<'fav' | 'more' | null>(null)
const dragKey = ref<string | null>(null)
const dropZone = ref<'fav' | 'more' | null>(null)
const dropIndex = ref<number>(-1)
const moreOpen = ref(false)

function selectTab(key: string) {
  if (key === props.tab) return
  emit('update:tab', key)
  // 选了"更多"里的项后关闭下拉
  moreOpen.value = false
}

// ============ 拖拽处理（HTML5 drag-and-drop） ============
// 拖拽 key 命名约定：dataTransfer.setData('text/tab-key', key)
function onDragStartFav(e: DragEvent, key: string) {
  dragZone.value = 'fav'
  dragKey.value = key
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/tab-key', key)
  }
}
function onDragStartMore(e: DragEvent, key: string) {
  dragZone.value = 'more'
  dragKey.value = key
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/tab-key', key)
  }
}
function onDragEnd() {
  dragZone.value = null
  dragKey.value = null
  dropZone.value = null
  dropIndex.value = -1
}

// 常用区按钮拖拽 over：定位插入位置
function onDragOverFavItem(e: DragEvent, key: string, idx: number) {
  if (!dragKey.value) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  const target = e.currentTarget as HTMLElement
  const r = target.getBoundingClientRect()
  const after = e.clientX > r.left + r.width / 2
  dropZone.value = 'fav'
  // 若在同一区且拖到自己，不显示插入线
  if (dragZone.value === 'fav' && dragKey.value === key) {
    dropIndex.value = -1
  } else {
    dropIndex.value = after ? idx + 1 : idx
  }
}
// 常用区容器 over（空白处）：插到末尾
function onDragOverFavContainer(e: DragEvent) {
  if (!dragKey.value) return
  if (dragZone.value === 'fav' && dropZone.value === 'fav') return // 已在 item 上定位
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  dropZone.value = 'fav'
  dropIndex.value = nav.favoriteKeys.length
}
// 常用区 drop：执行移动
function onDropFav(e: DragEvent) {
  e.preventDefault()
  const key = dragKey.value
  const fromZone = dragZone.value
  if (!key) return
  const toIdx = dropIndex.value < 0 ? nav.favoriteKeys.length : dropIndex.value
  if (fromZone === 'fav') {
    const fromIdx = nav.favoriteKeys.indexOf(key)
    // 同区移动：修正目标索引（移除源后索引会前移）
    const adjusted = fromIdx < toIdx ? toIdx - 1 : toIdx
    nav.moveFavorite(fromIdx, adjusted)
  } else if (fromZone === 'more') {
    nav.moveToFavorites(key, toIdx)
  }
  onDragEnd()
}

// 更多区按钮拖拽 over
function onDragOverMoreItem(e: DragEvent, key: string, idx: number) {
  if (!dragKey.value) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  const target = e.currentTarget as HTMLElement
  const r = target.getBoundingClientRect()
  const after = e.clientX > r.left + r.width / 2
  dropZone.value = 'more'
  if (dragZone.value === 'more' && dragKey.value === key) {
    dropIndex.value = -1
  } else {
    dropIndex.value = after ? idx + 1 : idx
  }
}
function onDragOverMoreContainer(e: DragEvent) {
  if (!dragKey.value) return
  if (dragZone.value === 'more' && dropZone.value === 'more') return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  dropZone.value = 'more'
  dropIndex.value = nav.moreKeys.length
}
function onDropMore(e: DragEvent) {
  e.preventDefault()
  const key = dragKey.value
  const fromZone = dragZone.value
  if (!key) return
  const toIdx = dropIndex.value < 0 ? nav.moreKeys.length : dropIndex.value
  if (fromZone === 'more') {
    const fromIdx = nav.moreKeys.indexOf(key)
    const adjusted = fromIdx < toIdx ? toIdx - 1 : toIdx
    nav.moveMore(fromIdx, adjusted)
  } else if (fromZone === 'fav') {
    nav.moveToMore(key, toIdx)
  }
  onDragEnd()
}

// 插入线显示判定（用于 :class 绑定）
function showDropBefore(zone: 'fav' | 'more', idx: number): boolean {
  return dropZone.value === zone && dropIndex.value === idx
}
function showDropAfter(zone: 'fav' | 'more', idx: number): boolean {
  return (
    dropZone.value === zone &&
    dropIndex.value === idx + 1 &&
    idx === (zone === 'fav' ? nav.favoriteKeys.length - 1 : nav.moreKeys.length - 1)
  )
}

// 更多下拉切换
function toggleMore() {
  moreOpen.value = !moreOpen.value
}
function closeMore() {
  moreOpen.value = false
}

// 重置导航顺序
function resetNav() {
  nav.reset(props.defaultFavoriteKeys)
  closeMore()
}

// 把指定 key 加入/移出常用区（更多菜单项右键快捷操作，也可做成按钮）
function toggleFavorite(key: string) {
  const isInFav = nav.favoriteKeys.includes(key)
  if (isInFav) nav.moveToMore(key)
  else nav.moveToFavorites(key)
}

// 键盘导航：←/→ 在常用区循环
const favKeys = computed(() => nav.favoriteKeys)
function onTabKeydown(e: KeyboardEvent) {
  const keys = favKeys.value
  const i = keys.indexOf(props.tab)
  if (i < 0) return
  let next = -1
  if (e.key === 'ArrowRight') next = (i + 1) % keys.length
  else if (e.key === 'ArrowLeft') next = (i - 1 + keys.length) % keys.length
  else if (e.key === 'Home') next = 0
  else if (e.key === 'End') next = keys.length - 1
  if (next < 0) return
  e.preventDefault()
  selectTab(keys[next])
}

onMounted(async () => {
  try {
    const r = await fetch('/api/version')
    const d = await r.json()
    appVersion.value = d.version || ''
    buildTime.value = d.build_time || ''
  } catch {
    /* ignore */
  }
  // 初始化导航排序（方案 D：常用区 + 更多）
  nav.init(props.tabs, props.defaultFavoriteKeys)
  // 后台异步检查升级（不阻塞 UI）
  upgrade.check().catch(() => { /* 静默失败 */ })
  // 点击更多面板外部时关闭
  window.addEventListener('click', onGlobalClick)
})

function onGlobalClick(e: MouseEvent) {
  if (!moreOpen.value) return
  const target = e.target as HTMLElement
  if (!target.closest('.more-wrap')) {
    moreOpen.value = false
  }
}

async function openUpgrade() {
  upgradeOpen.value = true
  // 强制刷新一次
  await upgrade.check(true)
}

function closeUpgrade() {
  upgradeOpen.value = false
}

function ignoreUpgrade() {
  upgrade.ignoreLatest()
  upgradeOpen.value = false
}

async function downloadAsset(url: string) {
  // pywebview 桌面模式：window.open 会被忽略，走 JS-Python 桥接用系统浏览器打开
  const pw = (window as any).pywebview
  if (pw?.api?.open_external) {
    try {
      await pw.api.open_external(url)
      return
    } catch { /* 回退到 window.open */ }
  }
  // 浏览器模式回退
  window.open(url, '_blank')
}

onBeforeUnmount(() => {
  window.removeEventListener('click', onGlobalClick)
})
</script>

<template>
  <header class="app-header command-shell sticky top-0 z-30 relative">
    <div class="max-w-[1600px] mx-auto w-full">
      <div
        class="command-bar grid items-center gap-x-4 gap-y-3 px-6 py-3
               grid-cols-[minmax(0,auto)_minmax(0,1fr)_minmax(0,auto)]
               max-[1100px]:grid-cols-[1fr_auto]"
      >
        <!-- Brand -->
        <div class="brand flex items-center gap-3 min-w-0 pl-0.5 max-[1100px]:col-start-1">
          <div
            class="brand-mark relative w-[38px] h-[38px] rounded-[11px] shrink-0
                   bg-gradient-to-br from-brand-500 to-brand-700
                   grid place-items-center"
            aria-hidden="true"
          >
            <svg class="brand-icon" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <!-- 飞翼：左右展开的翅膀 + 中间上升线，如虎添翼 -->
              <path d="M16 6 L16 26" />
              <path d="M16 10 C 12 8, 7 9, 4 12 C 7 13, 11 13, 14 12" />
              <path d="M16 10 C 20 8, 25 9, 28 12 C 25 13, 21 13, 18 12" />
              <path d="M16 17 C 12 15, 8 16, 5 19 C 8 20, 12 20, 15 19" />
              <path d="M16 17 C 20 15, 24 16, 27 19 C 24 20, 20 20, 17 19" />
            </svg>
          </div>
          <div class="min-w-0">
            <h1 class="text-[15px] font-bold tracking-tight leading-tight whitespace-nowrap" style="color: var(--text-primary)">
              飞翼
            </h1>
            <div class="flex items-center gap-1.5 mt-1">
              <!-- 版本胶囊：发光状态点 + 版本号，点击检查/打开升级 -->
              <button
                type="button"
                class="version-pill"
                :class="{ 'has-upgrade': upgrade.hasUpgrade, 'is-checking': upgrade.loading }"
                :title="upgrade.hasUpgrade
                  ? `发现新版本 v${upgrade.latestVersion}（当前 v${upgrade.currentVersion}）— 点击查看`
                  : upgrade.loading ? '正在检查升级…' : `当前 v${appVersion || '—'} · 点击检查升级`"
                :aria-label="upgrade.hasUpgrade ? `发现新版本 v${upgrade.latestVersion}` : '检查升级'"
                @click="openUpgrade"
              >
                <span class="vp-dot" aria-hidden="true" />
                <span class="vp-text">
                  <template v-if="upgrade.hasUpgrade">
                    v{{ upgrade.currentVersion }}<span class="vp-sep">→</span>v{{ upgrade.latestVersion }}
                  </template>
                  <template v-else>
                    v{{ appVersion || 'dev' }}
                  </template>
                </span>
                <svg
                  v-if="upgrade.hasUpgrade"
                  class="vp-arrow"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
                >
                  <path d="M12 19V5M5 12l7-7 7 7" />
                </svg>
                <svg
                  v-if="upgrade.loading"
                  class="vp-spin-icon"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
                >
                  <path d="M21 12a9 9 0 1 1-3-6.7" />
                </svg>
                <span v-if="upgrade.hasUpgrade" class="vp-badge" aria-hidden="true">新</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Tabs（方案 D：常用区 + 更多收起） -->
        <nav
          class="tab-rail flex justify-center min-w-0 max-[1100px]:col-span-2 max-[1100px]:justify-start"
          aria-label="配置分区"
        >
          <div
            class="tab-track relative flex items-center gap-0.5 p-1 max-w-full"
            role="tablist"
            aria-orientation="horizontal"
            @keydown="onTabKeydown"
            @dragover="onDragOverFavContainer"
            @drop="onDropFav"
          >
            <div
              v-for="(t, idx) in nav.favoriteItems"
              :key="t.key"
              role="tab"
              draggable="true"
              class="tab relative z-[1] cursor-pointer
                     text-[13px] font-medium tracking-tight whitespace-nowrap
                     px-3 py-2 rounded-[10px] transition-colors duration-150
                     fav-item"
              :class="{
                'is-active text-white font-semibold': tab === t.key,
                'hover:text-[var(--text-primary)]': tab !== t.key,
                'is-dragging': dragKey === t.key,
                'drop-before': showDropBefore('fav', idx),
                'drop-after': showDropAfter('fav', idx),
              }"
              :style="tab !== t.key ? { color: 'var(--text-secondary)' } : {}"
              :aria-selected="tab === t.key"
              :tabindex="tab === t.key ? 0 : -1"
              :title="`拖拽调整顺序 · ${t.label}`"
              @click="selectTab(t.key)"
              @dragstart="onDragStartFav($event, t.key)"
              @dragend="onDragEnd"
              @dragover="onDragOverFavItem($event, t.key, idx)"
            >
              <span class="drag-handle" aria-hidden="true">⠿</span>
              <span class="tab-label">{{ t.label }}</span>
              <button
                v-if="nav.favoriteKeys.length > 1"
                type="button"
                class="fav-remove"
                title="移出常用区"
                aria-label="移出常用区"
                @click.prevent.stop="nav.moveToMore(t.key)"
              >×</button>
            </div>

            <!-- 更多收起区 -->
            <div v-if="nav.moreItems.length > 0" class="more-wrap relative">
              <button
                type="button"
                class="tab more-trigger appearance-none border-0 bg-transparent cursor-pointer
                       text-[13px] font-medium tracking-tight whitespace-nowrap
                       px-3 py-2 rounded-[10px] transition-colors duration-150
                       flex items-center gap-1"
                :class="{
                  'is-active text-white font-semibold': nav.moreKeys.includes(tab),
                  'hover:text-[var(--text-primary)]': !nav.moreKeys.includes(tab),
                  'more-open': moreOpen,
                }"
                :style="!nav.moreKeys.includes(tab) ? { color: 'var(--text-secondary)' } : {}"
                :aria-expanded="moreOpen"
                title="更多菜单"
                @click="toggleMore"
              >
                更多 {{ nav.moreKeys.length }}
                <svg
                  class="more-chev"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
                >
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>

              <!-- 更多下拉面板 -->
              <div
                v-if="moreOpen"
                class="more-panel"
                role="menu"
                @dragover="onDragOverMoreContainer"
                @drop="onDropMore"
              >
                <div class="more-panel-head">
                  <span>更多菜单（可拖入常用区）</span>
                  <button type="button" class="more-reset" title="重置为默认顺序" @click="resetNav">
                    重置
                  </button>
                </div>
                <div
                  v-for="(t, idx) in nav.moreItems"
                  :key="t.key"
                  role="menuitem"
                  draggable="true"
                  class="more-item"
                  :class="{
                    'is-active': tab === t.key,
                    'is-dragging': dragKey === t.key,
                    'drop-before': showDropBefore('more', idx),
                    'drop-after': showDropAfter('more', idx),
                  }"
                  :title="`拖拽调整顺序 · ${t.label}`"
                  @click="selectTab(t.key)"
                  @dragstart="onDragStartMore($event, t.key)"
                  @dragend="onDragEnd"
                  @dragover="onDragOverMoreItem($event, t.key, idx)"
                >
                  <span class="drag-handle" aria-hidden="true">⠿</span>
                  <span class="tab-label">{{ t.label }}</span>
                  <button
                    type="button"
                    class="more-add"
                    title="加入常用区"
                    aria-label="加入常用区"
                    @click.prevent.stop="nav.moveToFavorites(t.key)"
                  >+</button>
                </div>
              </div>
            </div>
          </div>
        </nav>

        <!-- Actions -->
        <div class="actions flex items-center justify-end max-[1100px]:col-start-2 max-[1100px]:row-start-1">
          <!-- 主题切换按钮 -->
          <button
            class="theme-toggle"
            type="button"
            :title="theme.mode === 'light' ? '切换到深色模式' : '切换到浅色模式'"
            :aria-label="theme.mode === 'light' ? '切换到深色模式' : '切换到浅色模式'"
            @click="theme.toggle()"
          >
            <!-- 太阳图标（深色模式时显示，点击切回浅色） -->
            <svg v-if="theme.mode === 'dark'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
            </svg>
            <!-- 月亮图标（浅色模式时显示，点击切到深色） -->
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </header>

  <!-- 升级检查弹层 -->
  <Teleport to="body">
    <Transition name="upgrade-modal">
      <div v-if="upgradeOpen" class="upgrade-mask" @click.self="closeUpgrade">
        <div class="upgrade-panel" role="dialog" aria-modal="true" aria-labelledby="upgrade-title">
          <header class="upgrade-head">
            <h3 id="upgrade-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              检查升级
            </h3>
            <button type="button" class="upgrade-close" aria-label="关闭" @click="closeUpgrade">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </header>

          <div class="upgrade-body">
            <!-- 加载中 -->
            <div v-if="upgrade.loading" class="upgrade-loading">
              <svg class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 12a9 9 0 1 1-3-6.7" />
              </svg>
              <span>正在检查 GitHub Release…</span>
            </div>

            <!-- 错误 -->
            <div v-else-if="upgrade.info && !upgrade.info.ok" class="upgrade-error">
              <p>检查失败：{{ upgrade.info.error || '未知错误' }}</p>
              <a :href="upgrade.info.releaseUrl || 'https://github.com/superproxy/AgentBuddy/releases'" target="_blank" rel="noopener">
                手动查看 GitHub Releases →
              </a>
            </div>

            <!-- 开发模式 -->
            <div v-else-if="upgrade.info && upgrade.info.current === 'dev'" class="upgrade-dev">
              <p>开发模式（未读取到 version.json），跳过升级检查。</p>
              <a href="https://github.com/superproxy/AgentBuddy/releases" target="_blank" rel="noopener">
                查看 GitHub Releases →
              </a>
            </div>

            <!-- 无升级 -->
            <div v-else-if="!upgrade.hasUpgrade" class="upgrade-latest">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <div>
                <p class="title">已是最新版本</p>
                <p class="meta">
                  当前 v{{ upgrade.currentVersion }}
                  <span v-if="upgrade.info?.publishedAt">
                    · 最新发布于 {{ new Date(upgrade.info.publishedAt).toLocaleDateString() }}
                  </span>
                </p>
              </div>
            </div>

            <!-- 发现新版本 -->
            <div v-else class="upgrade-new">
              <div class="new-banner">
                <div class="new-info">
                  <p class="new-title">发现新版本 v{{ upgrade.latestVersion }}</p>
                  <p class="new-meta">
                    当前 v{{ upgrade.currentVersion }}
                    <span v-if="upgrade.info?.publishedAt">
                      · 发布于 {{ new Date(upgrade.info.publishedAt).toLocaleDateString() }}
                    </span>
                  </p>
                </div>
                <span class="new-badge">NEW</span>
              </div>

              <!-- 下载按钮 -->
              <div v-if="upgrade.downloads.length" class="downloads">
                <p class="downloads-title">下载安装包：</p>
                <div class="download-list">
                  <button
                    v-for="asset in upgrade.downloads"
                    :key="asset.url"
                    type="button"
                    class="download-btn"
                    :class="{ 'preferred': asset.platform === upgrade.getPreferredDownload()?.platform }"
                    @click="downloadAsset(asset.url)"
                  >
                    <span class="platform-icon" :class="asset.platform">
                      <svg v-if="asset.platform === 'windows'" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M3 5.1L9.4 4.2v6.2H3V5.1zM10.4 4L21 2.5V10.4H10.4V4zM3 12.9h6.4v6L3 17.8v-4.9zM10.4 12.9H21v7.6L10.4 21v-8.1z"/>
                      </svg>
                      <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M17.05 12.04c-.03-2.81 2.3-4.16 2.4-4.23-1.31-1.91-3.34-2.17-4.07-2.2-1.73-.18-3.39 1.02-4.27 1.02-.89 0-2.24-1-3.69-.97-1.9.03-3.65 1.1-4.63 2.8-1.98 3.43-.51 8.5 1.42 11.28.94 1.36 2.06 2.89 3.51 2.83 1.41-.06 1.95-.91 3.66-.91 1.71 0 2.19.91 3.69.88 1.52-.03 2.49-1.38 3.42-2.75 1.08-1.58 1.53-3.11 1.55-3.19-.03-.01-2.98-1.14-3.01-4.55M14.18 3.39c.78-.95 1.31-2.27 1.16-3.59-1.12.04-2.48.75-3.29 1.69-.72.83-1.36 2.18-1.19 3.47 1.25.1 2.53-.63 3.32-1.57"/>
                      </svg>
                    </span>
                    <span class="platform-text">
                      <strong>{{ asset.platform === 'windows' ? 'Windows' : asset.platform === 'macos' ? 'macOS' : asset.platform === 'macos-dmg' ? 'macOS DMG' : 'macOS ZIP' }}</strong>
                      <em>{{ upgrade.formatSize(asset.size) }}</em>
                    </span>
                    <svg class="download-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  </button>
                </div>
                <p class="downloads-tip">
                  下载后双击安装包覆盖安装即可，配置文件不会被覆盖。
                </p>
              </div>

              <!-- Release Notes -->
              <details v-if="upgrade.info?.releaseNotes" class="release-notes" open>
                <summary>更新内容</summary>
                <pre>{{ upgrade.info.releaseNotes }}</pre>
              </details>

              <a class="view-all" :href="upgrade.info?.releaseUrl" target="_blank" rel="noopener">
                查看完整 Release 页面 →
              </a>
            </div>
          </div>

          <footer class="upgrade-foot">
            <button type="button" class="btn-ghost" @click="ignoreUpgrade" v-if="upgrade.hasUpgrade">忽略此版本</button>
            <button type="button" class="btn-primary" @click="closeUpgrade">关闭</button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.command-shell {
  background: var(--bg-header);
  border-bottom: 1px solid var(--border-base);
  box-shadow: var(--shadow-sm);
}

.command-shell::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(22, 93, 255, 0.4) 22%,
    rgba(22, 93, 255, 0.4) 78%,
    transparent 100%
  );
  pointer-events: none;
}

.brand-mark {
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.14) inset,
    0 4px 14px rgba(22, 93, 255, 0.38);
  color: #fff;
}

.brand-icon {
  width: 24px;
  height: 24px;
  color: #fff;
}

.brand-mark::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 16px;
  background: radial-gradient(circle, rgba(22, 93, 255, 0.35), transparent 68%);
  z-index: -1;
  pointer-events: none;
}

/* 版本胶囊：发光状态点 + 版本号 + 升级入口 */
.version-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--border-base);
  background: linear-gradient(180deg, var(--bg-sunken), #fbfcfd);
  color: var(--text-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  font-variant-numeric: tabular-nums;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.version-pill:hover {
  border-color: var(--primary);
  background: var(--primary-container);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(22, 93, 255, 0.18);
}

.version-pill .vp-text {
  color: var(--text-primary);
  font-weight: 600;
}

.version-pill .vp-sep {
  opacity: 0.5;
  margin: 0 1px;
  font-weight: 400;
}

/* 发光状态点：常态绿 / 检查中灰闪 / 有新版本橙脉冲 */
.version-pill .vp-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 6px rgba(61, 214, 140, 0.6);
  flex-shrink: 0;
  transition: all 200ms ease;
}

.version-pill.is-checking .vp-dot {
  background: var(--text-tertiary);
  box-shadow: none;
  animation: vp-blink 1s linear infinite;
}

@keyframes vp-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* 检查中：旋转图标 */
.version-pill.is-checking {
  cursor: progress;
  opacity: 0.85;
}

.vp-spin-icon {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  color: var(--text-tertiary);
  animation: vp-spin 0.8s linear infinite;
}

@keyframes vp-spin {
  to { transform: rotate(360deg); }
}

/* 有新版本：橙色脉冲态 */
.version-pill.has-upgrade {
  border-color: rgba(255, 125, 0, 0.4);
  background: linear-gradient(180deg, rgba(255, 125, 0, 0.06), rgba(255, 125, 0, 0.02));
}

.version-pill.has-upgrade:hover {
  border-color: var(--warning);
  background: rgba(255, 125, 0, 0.12);
  box-shadow: 0 4px 14px rgba(255, 125, 0, 0.25);
}

.version-pill.has-upgrade .vp-dot {
  background: var(--warning);
  box-shadow: 0 0 8px rgba(255, 125, 0, 0.7);
  animation: vp-glow-pulse 1.6s ease-in-out infinite;
}

@keyframes vp-glow-pulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 6px rgba(255, 125, 0, 0.6); }
  50% { transform: scale(1.25); box-shadow: 0 0 12px rgba(255, 125, 0, 0.9); }
}

.version-pill.has-upgrade .vp-text {
  color: var(--warning);
}

.version-pill.has-upgrade .vp-arrow {
  width: 11px;
  height: 11px;
  flex-shrink: 0;
  color: var(--warning);
}

.version-pill .vp-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 14px;
  height: 14px;
  padding: 0 4px;
  margin-left: 2px;
  border-radius: 7px;
  background: var(--warning);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  font-family: inherit;
  line-height: 1;
}

.version-pill.has-upgrade:hover .vp-badge {
  background: #fff;
  color: var(--warning);
}

@media (prefers-reduced-motion: reduce) {
  .version-pill,
  .vp-spin-icon,
  .version-pill .vp-dot,
  .version-pill.has-upgrade .vp-dot {
    transition: none !important;
    animation: none !important;
  }
}

.tab-track {
  background: var(--bg-sunken);
  border: 1px solid var(--border-base);
  border-radius: 14px;
  scrollbar-width: none;
}

.tab-track::-webkit-scrollbar {
  display: none;
}

/* ============ 方案 D：常用区 + 更多收起 ============ */

/* 活跃 tab 背景（替代原 indicator） */
.tab.is-active {
  background: linear-gradient(180deg, var(--primary), var(--primary-hover));
  box-shadow:
    0 2px 10px rgba(22, 93, 255, 0.35),
    0 0 0 1px rgba(255, 255, 255, 0.12) inset;
}

.tab:focus-visible {
  outline: 2px solid rgba(217, 230, 255, 0.9);
  outline-offset: 2px;
}

/* 拖拽手柄：默认半透明，hover 时显示 */
.fav-item,
.more-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.drag-handle {
  font-size: 12px;
  line-height: 1;
  color: var(--text-tertiary);
  opacity: 0;
  cursor: grab;
  transition: opacity 150ms ease;
  user-select: none;
}
.fav-item:hover .drag-handle,
.more-item:hover .drag-handle {
  opacity: 0.55;
}
.fav-item:active .drag-handle,
.more-item:active .drag-handle {
  cursor: grabbing;
}
/* 活跃态手柄颜色 */
.fav-item.is-active .drag-handle {
  color: rgba(255, 255, 255, 0.7);
}

/* 拖拽中：源项半透明 */
.fav-item.is-dragging,
.more-item.is-dragging {
  opacity: 0.35;
}

/* 插入指示线 */
.fav-item.drop-before,
.more-item.drop-before {
  box-shadow: -2px 0 0 0 var(--primary);
}
.fav-item.drop-after,
.more-item.drop-after {
  box-shadow: 2px 0 0 0 var(--primary);
}

/* 常用区移除按钮（×） */
.fav-remove {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 14px;
  line-height: 1;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 150ms ease;
  margin-left: 2px;
}
.fav-item:hover .fav-remove {
  opacity: 0.6;
}
.fav-remove:hover {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  opacity: 1;
}
.fav-item:not(.is-active) .fav-remove:hover {
  background: var(--bg-sunken);
  color: var(--text-primary);
}

/* 更多按钮 */
.more-wrap {
  margin-left: 4px;
}
.more-trigger .more-chev {
  width: 11px;
  height: 11px;
  transition: transform 200ms ease;
  opacity: 0.7;
}
.more-trigger.more-open .more-chev {
  transform: rotate(180deg);
}
.more-trigger.is-active {
  background: linear-gradient(180deg, var(--primary), var(--primary-hover));
  box-shadow: 0 2px 10px rgba(22, 93, 255, 0.35);
}

/* 更多下拉面板 */
.more-panel {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  min-width: 220px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 12px;
  box-shadow:
    0 6px 24px rgba(0, 0, 0, 0.12),
    0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 6px;
  z-index: 50;
  animation: more-panel-in 160ms cubic-bezier(0.22, 1, 0.36, 1);
}
@keyframes more-panel-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-4px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}
.more-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px 8px;
  font-size: 11px;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-base);
  margin-bottom: 4px;
}
.more-reset {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
}
.more-reset:hover {
  background: var(--primary-container);
}
.more-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  padding: 7px 10px;
  border-radius: 7px;
  cursor: pointer;
  text-align: left;
  transition: background 120ms ease, color 120ms ease;
}
.more-item:hover {
  background: var(--bg-sunken);
  color: var(--text-primary);
}
.more-item.is-active {
  color: var(--primary);
  background: var(--primary-container);
}
.more-item .tab-label {
  flex: 1;
}
.more-add {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 16px;
  line-height: 1;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 150ms ease;
}
.more-item:hover .more-add {
  opacity: 0.7;
}
.more-add:hover {
  background: var(--primary);
  color: #fff;
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .tab,
  .more-panel,
  .drag-handle,
  .more-chev {
    transition: none !important;
    animation: none !important;
  }
}

/* 升级弹层 */
.upgrade-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(2px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.upgrade-panel {
  width: 100%;
  max-width: 560px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 14px;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.24);
  overflow: hidden;
}

.upgrade-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-base);
}

.upgrade-head h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.upgrade-head h3 svg {
  width: 18px;
  height: 18px;
  color: var(--primary);
}

.upgrade-close {
  border: 0;
  background: transparent;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  color: var(--text-tertiary);
  display: inline-flex;
}

.upgrade-close:hover {
  background: var(--bg-sunken);
  color: var(--text-primary);
}

.upgrade-close svg {
  width: 16px;
  height: 16px;
}

.upgrade-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.upgrade-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 0;
  color: var(--text-tertiary);
}

.upgrade-loading .spin {
  width: 16px;
  height: 16px;
  animation: upgrade-spin 0.8s linear infinite;
}

@keyframes upgrade-spin {
  to { transform: rotate(360deg); }
}

.upgrade-error,
.upgrade-dev {
  padding: 14px;
  background: var(--bg-sunken);
  border-radius: 8px;
  text-align: center;
}

.upgrade-error p,
.upgrade-dev p {
  margin: 0 0 8px;
}

.upgrade-error a,
.upgrade-dev a {
  color: var(--primary);
  text-decoration: none;
  font-size: 12px;
}

.upgrade-error a:hover,
.upgrade-dev a:hover {
  text-decoration: underline;
}

.upgrade-latest {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  background: rgba(61, 214, 140, 0.08);
  border: 1px solid rgba(61, 214, 140, 0.22);
  border-radius: 10px;
}

.upgrade-latest svg {
  width: 22px;
  height: 22px;
  color: #3dd68c;
  flex-shrink: 0;
}

.upgrade-latest .title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.upgrade-latest .meta {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.upgrade-new {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.new-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: linear-gradient(135deg, rgba(22, 93, 255, 0.08), rgba(22, 93, 255, 0.04));
  border: 1px solid rgba(22, 93, 255, 0.2);
  border-radius: 10px;
}

.new-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--primary);
}

.new-meta {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.new-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--primary);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.downloads {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.downloads-title {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.download-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.download-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid var(--border-base);
  background: var(--bg-base);
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  color: var(--text-primary);
  transition: all 150ms ease;
  text-align: left;
}

.download-btn:hover {
  border-color: var(--primary);
  background: var(--primary-container);
  color: var(--primary);
  transform: translateY(-1px);
}

.download-btn.preferred {
  border-color: var(--primary);
  background: var(--primary-container);
}

.platform-icon {
  display: inline-flex;
  width: 26px;
  height: 26px;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--bg-elevated);
  flex-shrink: 0;
}

.platform-icon.windows {
  color: #00a4ef;
}

.platform-icon.macos,
.platform-icon.macos-dmg,
.platform-icon.macos-zip {
  color: #000;
}

.platform-icon svg {
  width: 16px;
  height: 16px;
}

.platform-text {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.platform-text strong {
  font-weight: 600;
  font-size: 13px;
}

.platform-text em {
  font-style: normal;
  font-size: 11px;
  color: var(--text-tertiary);
}

.download-arrow {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
}

.download-btn:hover .download-arrow {
  color: var(--primary);
}

.downloads-tip {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.5;
}

.release-notes {
  border: 1px solid var(--border-base);
  border-radius: 8px;
  background: var(--bg-sunken);
  padding: 10px 12px;
}

.release-notes summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  user-select: none;
}

.release-notes[open] summary {
  margin-bottom: 8px;
}

.release-notes pre {
  margin: 0;
  font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
  max-height: 240px;
  overflow-y: auto;
}

.view-all {
  display: inline-block;
  color: var(--primary);
  text-decoration: none;
  font-size: 12px;
  font-weight: 500;
}

.view-all:hover {
  text-decoration: underline;
}

.upgrade-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--border-base);
  background: var(--bg-sunken);
}

.upgrade-foot button {
  padding: 6px 14px;
  border-radius: 6px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 150ms ease;
}

.upgrade-foot .btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border-color: var(--border-base);
}

.upgrade-foot .btn-ghost:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.upgrade-foot .btn-primary {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}

.upgrade-foot .btn-primary:hover {
  background: var(--primary-hover);
  border-color: var(--primary-hover);
}

/* 弹层过渡动画 */
.upgrade-modal-enter-active,
.upgrade-modal-leave-active {
  transition: opacity 200ms ease;
}

.upgrade-modal-enter-active .upgrade-panel,
.upgrade-modal-leave-active .upgrade-panel {
  transition: transform 200ms cubic-bezier(0.22, 1, 0.36, 1), opacity 200ms ease;
}

.upgrade-modal-enter-from,
.upgrade-modal-leave-to {
  opacity: 0;
}

.upgrade-modal-enter-from .upgrade-panel,
.upgrade-modal-leave-to .upgrade-panel {
  transform: translateY(-20px) scale(0.96);
  opacity: 0;
}

/* 主题切换按钮 —— 与 market-cluster 同样的容器风格，elevated 凸起感 */
.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  margin-left: 8px;
  border-radius: 10px;
  border: 1px solid var(--border-base);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
  box-shadow: var(--shadow-sm);
  transition: all 180ms cubic-bezier(0.4, 0, 0.2, 1);
}

.theme-toggle:hover {
  background: var(--primary-container);
  color: var(--primary);
  border-color: var(--primary);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.theme-toggle:active {
  transform: translateY(0);
  box-shadow: var(--shadow-sm);
}

.theme-toggle:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.theme-toggle svg {
  width: 18px;
  height: 18px;
  transition: transform 360ms cubic-bezier(0.34, 1.56, 0.64, 1);
}

.theme-toggle:hover svg {
  transform: rotate(15deg);
}
</style>
