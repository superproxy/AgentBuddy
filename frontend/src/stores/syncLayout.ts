/**
 * SyncBar 窗口化布局状态 —— 四边停靠 / 中心浮动（类 Apple 窗口化 App）
 */
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type SyncBarPlacement = 'top' | 'bottom' | 'left' | 'right' | 'float'

export interface FloatPos {
  x: number
  y: number
}

export interface FloatSize {
  w: number
  h: number
}

const PLACEMENT_KEY = 'myagent.syncBar.placement'
const FLOAT_POS_KEY = 'myagent.syncBar.floatPos'
const FLOAT_SIZE_KEY = 'myagent.syncBar.floatSize'
const VALID: SyncBarPlacement[] = ['top', 'bottom', 'left', 'right', 'float']

/**
 * 最小浮窗尺寸：保证标题栏 + 三栏堆叠（窄屏自适应）时内容不挤压错乱。
 * 宽 ≥ 480：两列瓦片 + 单列甲板；高 ≥ 360：标题栏 + 模式/目标/执行可滚动。
 */
const MIN_W = 480
const MIN_H = 360
const DEFAULT_W = 860
const DEFAULT_H = 440

function loadPlacement(): SyncBarPlacement {
  try {
    const v = localStorage.getItem(PLACEMENT_KEY)
    if (v && VALID.includes(v as SyncBarPlacement)) return v as SyncBarPlacement
  } catch {
    /* ignore */
  }
  return 'top'
}

function loadFloatPos(): FloatPos {
  try {
    const raw = localStorage.getItem(FLOAT_POS_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      if (typeof p?.x === 'number' && typeof p?.y === 'number') return p
    }
  } catch {
    /* ignore */
  }
  return { x: 72, y: 96 }
}

function loadFloatSize(): FloatSize {
  try {
    const raw = localStorage.getItem(FLOAT_SIZE_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      if (typeof p?.w === 'number' && typeof p?.h === 'number') {
        return { w: Math.max(MIN_W, p.w), h: Math.max(MIN_H, p.h) }
      }
    }
  } catch {
    /* ignore */
  }
  return { w: DEFAULT_W, h: DEFAULT_H }
}

export const useSyncLayoutStore = defineStore('syncLayout', () => {
  const placement = ref<SyncBarPlacement>(loadPlacement())
  const floatPos = ref<FloatPos>(loadFloatPos())
  const floatSize = ref<FloatSize>(loadFloatSize())
  const dragging = ref(false)
  const hoverZone = ref<SyncBarPlacement | null>(null)
  /** 面板占用尺寸，供主内容区避让 */
  const dockSize = ref({ width: 0, height: 0 })
  const headerOffset = ref(108)

  watch(placement, (v) => {
    try {
      localStorage.setItem(PLACEMENT_KEY, v)
    } catch {
      /* ignore */
    }
  })

  watch(
    floatPos,
    (v) => {
      try {
        localStorage.setItem(FLOAT_POS_KEY, JSON.stringify(v))
      } catch {
        /* ignore */
      }
    },
    { deep: true },
  )

  watch(
    floatSize,
    (v) => {
      try {
        localStorage.setItem(FLOAT_SIZE_KEY, JSON.stringify(v))
      } catch {
        /* ignore */
      }
    },
    { deep: true },
  )

  function setPlacement(next: SyncBarPlacement) {
    placement.value = next
  }

  function setFloatPos(x: number, y: number) {
    floatPos.value = { x, y }
  }

  function setFloatSize(w: number, h: number) {
    const clamped = clampFloatSize(w, h)
    floatSize.value = clamped
  }

  /** 拖离停靠时落到最小可用尺寸 */
  function resetToMinFloatSize() {
    floatSize.value = clampFloatSize(MIN_W, MIN_H)
    return { ...floatSize.value }
  }

  function setDockSize(width: number, height: number) {
    dockSize.value = { width, height }
  }

  function setHeaderOffset(px: number) {
    headerOffset.value = Math.max(0, Math.round(px))
  }

  function clampFloatPos(x: number, y: number, w = DEFAULT_W, h = DEFAULT_H): FloatPos {
    const pad = 12
    const maxX = Math.max(pad, window.innerWidth - w - pad)
    const maxY = Math.max(pad, window.innerHeight - h - pad)
    return {
      x: Math.min(Math.max(pad, x), maxX),
      y: Math.min(Math.max(pad, y), maxY),
    }
  }

  function clampFloatSize(w: number, h: number): FloatSize {
    const maxW = Math.max(MIN_W, window.innerWidth - 24)
    const maxH = Math.max(MIN_H, window.innerHeight - 24)
    return {
      w: Math.min(Math.max(MIN_W, Math.round(w)), maxW),
      h: Math.min(Math.max(MIN_H, Math.round(h)), maxH),
    }
  }

  return {
    placement,
    floatPos,
    floatSize,
    dragging,
    hoverZone,
    dockSize,
    headerOffset,
    MIN_W,
    MIN_H,
    setPlacement,
    setFloatPos,
    setFloatSize,
    resetToMinFloatSize,
    setDockSize,
    setHeaderOffset,
    clampFloatPos,
    clampFloatSize,
  }
})
