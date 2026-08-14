import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api } from '../api/client'

export type ThemeMode = 'light' | 'dark'

// 旧 localStorage 键名（仅用于一次性迁移到后端）
const LEGACY_LS_KEY = 'agentbuddy-theme'

function readLegacyLs(): ThemeMode | undefined {
  try {
    const saved = localStorage.getItem(LEGACY_LS_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* ignore */
  }
  return undefined
}

function clearLegacyLs() {
  try {
    localStorage.removeItem(LEGACY_LS_KEY)
  } catch {
    /* ignore */
  }
}

export const useThemeStore = defineStore('theme', () => {
  // 默认浅色，加载完成后由后端状态覆盖
  const mode = ref<ThemeMode>('light')
  const loaded = ref(false)
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function apply(m: ThemeMode) {
    if (typeof document === 'undefined') return
    document.documentElement.setAttribute('data-theme', m)
  }

  function toggle() {
    mode.value = mode.value === 'light' ? 'dark' : 'light'
  }

  function set(m: ThemeMode) {
    mode.value = m
  }

  function persist(m: ThemeMode) {
    if (!loaded.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      api<{ ok: boolean }>('/api/ui-state', {
        method: 'POST',
        body: JSON.stringify({ theme: m }),
      }).catch(() => {
        /* 静默失败 */
      })
    }, 200)
  }

  // 初始应用默认值，避免首帧闪烁
  apply(mode.value)

  watch(mode, (m) => {
    apply(m)
    persist(m)
  })

  /** 启动时从后端加载；后端无数据时尝试从旧 localStorage 迁移一次 */
  async function loadFromBackend() {
    let state: Record<string, any> = {}
    try {
      state = await api<Record<string, any>>('/api/ui-state')
    } catch {
      state = {}
    }
    let next: ThemeMode | undefined
    if (state && (state.theme === 'light' || state.theme === 'dark')) {
      next = state.theme
    } else {
      // 后端无数据 → 尝试从旧 localStorage 迁移
      const legacy = readLegacyLs()
      if (legacy) {
        next = legacy
        try {
          await api('/api/ui-state', {
            method: 'POST',
            body: JSON.stringify({ theme: next }),
          })
          clearLegacyLs()
        } catch {
          /* 迁移失败不影响使用 */
        }
      }
    }
    if (next) {
      mode.value = next
      apply(next)
    }
    loaded.value = true
  }

  // 异步初始化（不阻塞渲染，加载完成前先用默认浅色）
  loadFromBackend()

  return { mode, toggle, set, loadFromBackend }
})
