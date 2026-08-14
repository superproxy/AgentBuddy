import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'

/**
 * AIDE 品牌排序 store —— 复用 navOrder 的"常用区 + 更多区"设计模式。
 *
 * 存储：
 *   - favoriteKeys: string[]  常用品牌顺序（可拖拽调整，可拖入/拖出）
 *   - moreKeys: string[]      "更多"下拉中的品牌顺序
 *
 * 持久化：后端 /api/ui-state（config/ui/ui-state.json），避免 localStorage 在 webview 重启丢失。
 *
 * 兜底：若存储中的 key 集合与 allKeys 不一致（例如新增了品牌），
 *       自动补齐缺失 key 到 moreKeys，移除已废弃 key。
 */

interface StoredOrder {
  favoriteKeys: string[]
  moreKeys: string[]
}

export const useBrandOrderStore = defineStore('brandOrder', () => {
  /** 全部品牌 key（由调用方通过 init 注入） */
  const allKeys = ref<string[]>([])
  /** 常用区顺序 */
  const favoriteKeys = ref<string[]>([])
  /** 更多区顺序 */
  const moreKeys = ref<string[]>([])
  /** 是否已初始化 */
  const ready = ref(false)
  // 是否已完成首次加载；加载完成前不回写后端
  let loaded = false
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  /** 防抖回写后端 */
  function persist() {
    if (!loaded) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      const data: StoredOrder = {
        favoriteKeys: favoriteKeys.value.slice(),
        moreKeys: moreKeys.value.slice(),
      }
      api('/api/ui-state', {
        method: 'POST',
        body: JSON.stringify({ ideBrandOrder: data }),
      }).catch(() => { /* 静默失败 */ })
    }, 200)
  }

  /** 从后端加载 */
  async function load(): Promise<StoredOrder | null> {
    try {
      const state = await api<Record<string, any>>('/api/ui-state')
      const data = state.ideBrandOrder
      if (data && typeof data === 'object' &&
          Array.isArray(data.favoriteKeys) && Array.isArray(data.moreKeys)) {
        return data as StoredOrder
      }
    } catch { /* 静默失败 */ }
    return null
  }

  /**
   * 初始化：注入全部品牌定义 + 默认常用区顺序
   * @param items  全部品牌 [{key,label}]
   * @param defaults 默认常用区 key 顺序
   */
  async function init(items: { key: string; label: string }[], defaults: string[]) {
    const keys = items.map((i) => i.key)
    allKeys.value = keys

    const valid = new Set(keys)
    const stored = await load()
    if (stored) {
      // 剔除已废弃 key，补齐新增 key 到 more
      const fav = stored.favoriteKeys.filter((k) => valid.has(k))
      const more = stored.moreKeys.filter((k) => valid.has(k))
      const seen = new Set([...fav, ...more])
      const missing = keys.filter((k) => !seen.has(k))
      favoriteKeys.value = fav
      moreKeys.value = [...more, ...missing]
      // 常用区为空时用 defaults 兜底
      if (favoriteKeys.value.length === 0 && defaults.length > 0) {
        const def = defaults.filter((k) => valid.has(k))
        const defSet = new Set(def)
        favoriteKeys.value = def
        moreKeys.value = keys.filter((k) => !defSet.has(k))
      }
    } else {
      // 首次：用 defaults 划分
      const defSet = new Set(defaults)
      favoriteKeys.value = defaults.filter((k) => keys.includes(k))
      moreKeys.value = keys.filter((k) => !defSet.has(k))
    }
    loaded = true
    ready.value = true
    persist()
  }

  /** 常用区内部拖拽：把 fromIdx 移到 toIdx */
  function moveFavorite(fromIdx: number, toIdx: number) {
    if (fromIdx < 0 || toIdx < 0) return
    if (fromIdx >= favoriteKeys.value.length || toIdx >= favoriteKeys.value.length) return
    const arr = favoriteKeys.value.slice()
    const [item] = arr.splice(fromIdx, 1)
    arr.splice(toIdx, 0, item)
    favoriteKeys.value = arr
    persist()
  }

  /** 更多区内部拖拽 */
  function moveMore(fromIdx: number, toIdx: number) {
    if (fromIdx < 0 || toIdx < 0) return
    if (fromIdx >= moreKeys.value.length || toIdx >= moreKeys.value.length) return
    const arr = moreKeys.value.slice()
    const [item] = arr.splice(fromIdx, 1)
    arr.splice(toIdx, 0, item)
    moreKeys.value = arr
    persist()
  }

  /** 从常用区移到更多区（toIdx=-1 末尾） */
  function moveToMore(key: string, toIdx = -1) {
    const idx = favoriteKeys.value.indexOf(key)
    if (idx < 0) return
    const fav = favoriteKeys.value.slice()
    fav.splice(idx, 1)
    favoriteKeys.value = fav
    const more = moreKeys.value.slice()
    if (toIdx < 0 || toIdx > more.length) more.push(key)
    else more.splice(toIdx, 0, key)
    moreKeys.value = more
    persist()
  }

  /** 从更多区移到常用区（toIdx=-1 末尾） */
  function moveToFavorites(key: string, toIdx = -1) {
    const idx = moreKeys.value.indexOf(key)
    if (idx < 0) return
    const more = moreKeys.value.slice()
    more.splice(idx, 1)
    moreKeys.value = more
    const fav = favoriteKeys.value.slice()
    if (toIdx < 0 || toIdx > fav.length) fav.push(key)
    else fav.splice(toIdx, 0, key)
    favoriteKeys.value = fav
    persist()
  }

  /** 重置为默认顺序 */
  function reset(defaults: string[]) {
    const keys = allKeys.value
    const defSet = new Set(defaults)
    favoriteKeys.value = defaults.filter((k) => keys.includes(k))
    moreKeys.value = keys.filter((k) => !defSet.has(k))
    persist()
  }

  const favoriteItems = computed(() => favoriteKeys.value)
  const moreItems = computed(() => moreKeys.value)

  return {
    allKeys,
    favoriteKeys,
    moreKeys,
    ready,
    init,
    moveFavorite,
    moveMore,
    moveToMore,
    moveToFavorites,
    reset,
    favoriteItems,
    moreItems,
  }
})
