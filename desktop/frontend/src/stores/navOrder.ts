import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 导航排序与常用区状态（方案 D：常用区 + 更多收起）
 *
 * 存储：
 *   - favoriteKeys: string[]  常用区菜单 key 顺序（可拖拽调整，可拖入/拖出）
 *   - moreKeys: string[]      "更多"下拉中的菜单 key 顺序（可拖拽调整）
 *
 * 持久化：localStorage['agentbuddy-nav-order-v1']
 *
 * 兜底：若存储中的 key 集合与 allKeys 不一致（例如新增了菜单），
 *       自动补齐缺失 key 到 moreKeys，移除已废弃 key。
 */

const STORAGE_KEY = 'agentbuddy-nav-order-v1'

interface StoredOrder {
  favoriteKeys: string[]
  moreKeys: string[]
}

export const useNavOrderStore = defineStore('navOrder', () => {
  /** 全部菜单 key（由调用方通过 init 注入，顺序即"更多"区默认顺序） */
  const allKeys = ref<string[]>([])
  /** 全部菜单 label 映射 */
  const allLabels = ref<Record<string, string>>({})
  /** 常用区顺序 */
  const favoriteKeys = ref<string[]>([])
  /** 更多区顺序 */
  const moreKeys = ref<string[]>([])
  /** 是否已初始化 */
  const ready = ref(false)

  function persist() {
    try {
      const data: StoredOrder = {
        favoriteKeys: favoriteKeys.value.slice(),
        moreKeys: moreKeys.value.slice(),
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch {
      /* 忽略 */
    }
  }

  function load(): StoredOrder | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return null
      const data = JSON.parse(raw) as StoredOrder
      if (!Array.isArray(data.favoriteKeys) || !Array.isArray(data.moreKeys)) return null
      return data
    } catch {
      return null
    }
  }

  /**
   * 初始化：注入全部菜单定义 + 默认常用区顺序
   * @param items  全部菜单 [{key,label}]，顺序即"更多"区默认顺序
   * @param defaults 默认常用区 key 顺序
   */
  function init(items: { key: string; label: string }[], defaults: string[]) {
    const keys = items.map((i) => i.key)
    const labelMap: Record<string, string> = {}
    items.forEach((i) => (labelMap[i.key] = i.label))
    allKeys.value = keys
    allLabels.value = labelMap

    const valid = new Set(keys)
    const stored = load()
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

  const favoriteItems = computed(() =>
    favoriteKeys.value.map((k) => ({ key: k, label: allLabels.value[k] ?? k })),
  )
  const moreItems = computed(() =>
    moreKeys.value.map((k) => ({ key: k, label: allLabels.value[k] ?? k })),
  )

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
