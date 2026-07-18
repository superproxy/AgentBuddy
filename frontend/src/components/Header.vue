<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useThemeStore } from '../stores/theme'

interface TabItem {
  key: string
  label: string
}

const props = defineProps<{ tab: string; tabs: TabItem[] }>()
const emit = defineEmits<{
  (e: 'update:tab', v: string): void
}>()

const theme = useThemeStore()
const appVersion = ref('')
const buildTime = ref('')

const tabTrackRef = ref<HTMLElement | null>(null)
const tabBtnRefs = ref<Record<string, HTMLElement | null>>({})
const indicatorStyle = ref({ width: '0px', transform: 'translateX(0px)' })
const indicatorReady = ref(false)

const statusLabel = computed(() =>
  buildTime.value ? `构建于 ${buildTime.value.slice(0, 10)}` : '开发模式',
)

function setTabBtnRef(key: string, el: unknown) {
  tabBtnRefs.value[key] = (el as HTMLElement | null) ?? null
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
  <header class="app-header command-shell sticky top-0 z-30 relative overflow-hidden">
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
            <h1 class="text-[15px] font-bold tracking-tight leading-tight whitespace-nowrap" style="color: var(--text-primary)">
              AdeBuddy 配置工具
            </h1>
            <div class="flex items-center gap-2 mt-1">
              <span
                v-if="appVersion"
                class="font-mono text-[11px] font-medium tracking-wide"
                style="color: var(--text-tertiary)"
              >v{{ appVersion }}</span>
              <span
                class="status-pill inline-flex items-center gap-1.5 text-[11px] font-medium
                       px-2 py-0.5 rounded-full"
                :title="statusLabel"
                :style="{ color: 'var(--text-secondary)' }"
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
              :class="tab === t.key ? 'text-white font-semibold' : 'hover:text-[var(--text-primary)]'"
              :style="tab !== t.key ? { color: 'var(--text-secondary)' } : {}"
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
  background: var(--success-container);
  border: 1px solid rgba(61, 214, 140, 0.22);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
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
  background: var(--bg-sunken);
  border: 1px solid var(--border-base);
  border-radius: 14px;
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
  background: linear-gradient(180deg, var(--primary), var(--primary-hover));
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

@media (prefers-reduced-motion: reduce) {
  .tab-indicator.is-ready,
  .status-dot {
    transition: none !important;
    animation: none !important;
  }
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
