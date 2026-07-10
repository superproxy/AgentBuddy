<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useSyncLayoutStore } from '../stores/syncLayout'

interface TabItem {
  key: string
  label: string
}

const props = defineProps<{ tab: string; tabs: TabItem[] }>()
const emit = defineEmits<{
  (e: 'update:tab', v: string): void
  (e: 'restore-sync'): void
}>()

const layout = useSyncLayoutStore()
const appVersion = ref('')
const buildTime = ref('')

const tabTrackRef = ref<HTMLElement | null>(null)
const tabBtnRefs = ref<Record<string, HTMLElement | null>>({})
const indicatorStyle = ref({ width: '0px', transform: 'translateX(0px)' })
const indicatorReady = ref(false)

const showRestoreSync = computed(() => props.tab !== 'plugin-build')
const statusLabel = computed(() =>
  buildTime.value ? `构建于 ${buildTime.value.slice(0, 10)}` : '开发模式',
)

function setTabBtnRef(key: string, el: unknown) {
  tabBtnRefs.value[key] = (el as HTMLElement | null) ?? null
}

function restoreSyncPanel() {
  layout.resetToTopDock()
  if (props.tab === 'ide') emit('update:tab', 'env')
  emit('restore-sync')
}

function selectTab(key: string) {
  if (key === props.tab) return
  emit('update:tab', key)
}

function moveIndicator(animate = true) {
  const track = tabTrackRef.value
  const btn = tabBtnRefs.value[props.tab]
  if (!track || !btn) return

  const left = btn.offsetLeft
  const width = btn.offsetWidth
  if (!animate) indicatorReady.value = false
  indicatorStyle.value = {
    width: `${width}px`,
    transform: `translateX(${left}px)`,
  }
  if (!animate) {
    requestAnimationFrame(() => {
      indicatorReady.value = true
    })
  } else {
    indicatorReady.value = true
  }

  btn.scrollIntoView({ inline: 'nearest', block: 'nearest', behavior: animate ? 'smooth' : 'auto' })
}

function onTabKeydown(e: KeyboardEvent) {
  const keys = props.tabs.map((t) => t.key)
  const i = keys.indexOf(props.tab)
  if (i < 0) return

  let next = -1
  if (e.key === 'ArrowRight') next = (i + 1) % keys.length
  else if (e.key === 'ArrowLeft') next = (i - 1 + keys.length) % keys.length
  else if (e.key === 'Home') next = 0
  else if (e.key === 'End') next = keys.length - 1
  if (next < 0) return

  e.preventDefault()
  const key = keys[next]
  selectTab(key)
  nextTick(() => tabBtnRefs.value[key]?.focus())
}

function onResize() {
  moveIndicator(false)
}

watch(
  () => props.tab,
  async () => {
    await nextTick()
    moveIndicator(true)
  },
)

watch(
  () => props.tabs,
  async () => {
    await nextTick()
    moveIndicator(false)
  },
  { deep: true },
)

onMounted(async () => {
  try {
    const r = await fetch('/api/version')
    const d = await r.json()
    appVersion.value = d.version || ''
    buildTime.value = d.build_time || ''
  } catch {
    /* ignore */
  }
  await nextTick()
  moveIndicator(false)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <header class="app-header command-shell sticky top-0 z-30 text-white relative overflow-hidden">
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
                   grid place-items-center font-bold text-[17px] tracking-tight"
            aria-hidden="true"
          >
            A
          </div>
          <div class="min-w-0">
            <h1 class="text-[15px] font-bold tracking-tight leading-tight whitespace-nowrap">
              AdeBuddy 配置工具
            </h1>
            <div class="flex items-center gap-2 mt-1">
              <span
                v-if="appVersion"
                class="font-mono text-[11px] font-medium text-white/40 tracking-wide"
              >v{{ appVersion }}</span>
              <span
                class="status-pill inline-flex items-center gap-1.5 text-[11px] font-medium
                       text-white/70 px-2 py-0.5 rounded-full"
                :title="statusLabel"
              >
                <span class="status-dot" aria-hidden="true" />
                <span class="max-[560px]:sr-only">{{ statusLabel }}</span>
              </span>
            </div>
          </div>
        </div>

        <!-- Tabs -->
        <nav
          class="tab-rail flex justify-center min-w-0 max-[1100px]:col-span-2 max-[1100px]:justify-start"
          aria-label="配置分区"
        >
          <div
            ref="tabTrackRef"
            class="tab-track relative flex items-center gap-0.5 p-1 max-w-full overflow-x-auto"
            role="tablist"
            aria-orientation="horizontal"
            @keydown="onTabKeydown"
          >
            <div
              class="tab-indicator"
              :class="{ 'is-ready': indicatorReady }"
              :style="indicatorStyle"
              aria-hidden="true"
            />
            <button
              v-for="t in tabs"
              :key="t.key"
              :ref="(el) => setTabBtnRef(t.key, el)"
              type="button"
              role="tab"
              class="tab relative z-[1] appearance-none border-0 bg-transparent cursor-pointer
                     text-[13px] font-medium tracking-tight whitespace-nowrap
                     px-3 py-2 rounded-[10px] transition-colors duration-150"
              :class="tab === t.key ? 'text-white font-semibold' : 'text-white/55 hover:text-white/90'"
              :aria-selected="tab === t.key"
              :tabindex="tab === t.key ? 0 : -1"
              @click="selectTab(t.key)"
            >
              {{ t.label }}
            </button>
          </div>
        </nav>

        <!-- Actions -->
        <div class="actions flex items-center justify-end max-[1100px]:col-start-2 max-[1100px]:row-start-1">
          <div class="market-cluster inline-flex items-stretch p-0.5 rounded-xl" aria-label="快捷操作">
            <button
              v-if="showRestoreSync"
              type="button"
              class="market-btn"
              title="找回同步面板（Ctrl+Shift+S）"
              @click="restoreSyncPanel"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                <path d="M3 3v5h5" />
                <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                <path d="M16 16h5v5" />
              </svg>
              <span class="label">同步面板</span>
            </button>
            <a
              class="market-btn"
              href="https://www.modelscope.cn/mcp"
              target="_blank"
              rel="noopener noreferrer"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
              <span class="label">MCP 市场</span>
              <svg class="ext-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
                <path d="M7 17L17 7M8 7h9v9" />
              </svg>
            </a>
            <a
              class="market-btn"
              href="https://www.modelscope.cn/skills"
              target="_blank"
              rel="noopener noreferrer"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
              </svg>
              <span class="label">Skills 市场</span>
              <svg class="ext-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
                <path d="M7 17L17 7M8 7h9v9" />
              </svg>
            </a>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.command-shell {
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.05), transparent 42%),
    linear-gradient(135deg, #1a1d22 0%, #242930 100%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 8px 24px rgba(31, 35, 41, 0.22);
}

.command-shell::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(22, 93, 255, 0.55) 22%,
    rgba(217, 230, 255, 0.55) 50%,
    rgba(22, 93, 255, 0.55) 78%,
    transparent 100%
  );
  pointer-events: none;
}

.brand-mark {
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.14) inset,
    0 4px 14px rgba(22, 93, 255, 0.38);
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

.status-pill {
  background: rgba(61, 214, 140, 0.08);
  border: 1px solid rgba(61, 214, 140, 0.22);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #3dd68c;
  box-shadow: 0 0 0 3px rgba(61, 214, 140, 0.18);
}

@media (prefers-reduced-motion: no-preference) {
  .status-dot {
    animation: pulse-dot 2.4s ease-in-out infinite;
  }
}

@keyframes pulse-dot {
  0%,
  100% {
    box-shadow: 0 0 0 3px rgba(61, 214, 140, 0.16);
  }
  50% {
    box-shadow: 0 0 0 5px rgba(61, 214, 140, 0.08);
  }
}

.tab-track {
  background: rgba(0, 0, 0, 0.32);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 14px;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.04) inset;
  scrollbar-width: none;
}

.tab-track::-webkit-scrollbar {
  display: none;
}

.tab-indicator {
  position: absolute;
  top: 4px;
  left: 0;
  height: calc(100% - 8px);
  border-radius: 10px;
  background: linear-gradient(180deg, #165dff, #0e42d2);
  box-shadow:
    0 2px 10px rgba(22, 93, 255, 0.45),
    0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  pointer-events: none;
  z-index: 0;
  will-change: transform, width;
}

.tab-indicator.is-ready {
  transition:
    transform 200ms cubic-bezier(0.22, 1, 0.36, 1),
    width 200ms cubic-bezier(0.22, 1, 0.36, 1);
}

.tab:focus-visible {
  outline: 2px solid rgba(217, 230, 255, 0.9);
  outline-offset: 2px;
}

.market-cluster {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.09);
}

.market-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: rgba(255, 255, 255, 0.78);
  text-decoration: none;
  padding: 7px 12px;
  border-radius: 9px;
  border: 0;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  transition:
    background 150ms ease,
    color 150ms ease;
}

.market-btn + .market-btn {
  position: relative;
}

.market-btn + .market-btn::before {
  content: '';
  position: absolute;
  left: 0;
  top: 22%;
  bottom: 22%;
  width: 1px;
  background: rgba(255, 255, 255, 0.1);
}

.market-btn:hover {
  background: rgba(22, 93, 255, 0.28);
  color: #fff;
}

.market-btn:focus-visible {
  outline: 2px solid rgba(217, 230, 255, 0.9);
  outline-offset: 2px;
}

.market-btn svg {
  width: 14px;
  height: 14px;
  opacity: 0.72;
  flex-shrink: 0;
  transition: opacity 150ms ease;
}

.market-btn:hover svg {
  opacity: 1;
}

.ext-icon {
  width: 11px;
  height: 11px;
  opacity: 0.4;
  margin-left: -1px;
}

@media (max-width: 560px) {
  .market-btn .label {
    display: none;
  }

  .market-btn {
    padding: 8px 10px;
  }

  .market-btn + .market-btn::before {
    display: none;
  }

  .ext-icon {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tab-indicator.is-ready,
  .market-btn,
  .market-btn svg,
  .status-dot {
    transition: none !important;
    animation: none !important;
  }
}
</style>
