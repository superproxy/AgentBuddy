import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'agentbuddy-theme'

function readInitial(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* ignore */
  }
  // 默认跟随系统偏好
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(readInitial())

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

  // 初始应用
  apply(mode.value)

  watch(
    mode,
    (m) => {
      apply(m)
      try {
        localStorage.setItem(STORAGE_KEY, m)
      } catch {
        /* ignore */
      }
    },
    { immediate: false },
  )

  return { mode, toggle, set }
})
