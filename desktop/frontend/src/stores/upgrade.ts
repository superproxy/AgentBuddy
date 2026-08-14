import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'

export interface UpgradeAsset {
  platform: 'windows' | 'macos' | 'macos-dmg' | 'macos-zip'
  filename: string
  url: string
  size: number
}

export interface UpgradeInfo {
  ok: boolean
  current: string
  latest: string | null
  hasUpgrade: boolean
  releaseUrl: string
  releaseNotes: string
  publishedAt: string
  downloads: UpgradeAsset[]
  note?: string
  error?: string
}

export const useUpgradeStore = defineStore('upgrade', () => {
  const info = ref<UpgradeInfo | null>(null)
  const loading = ref(false)
  const lastChecked = ref<number>(0)  // timestamp
  /** 用户已忽略此版本（不再提示红点，但可手动打开对话框再次检查） */
  const ignoredVersion = ref<string>('')

  const hasUpgrade = computed(() => !!info.value?.hasUpgrade && info.value.latest !== ignoredVersion.value)
  const currentVersion = computed(() => info.value?.current || '')
  const latestVersion = computed(() => info.value?.latest || '')
  const downloads = computed(() => info.value?.downloads || [])

  /**
   * 检查升级。force=true 强制刷新（绕过缓存）
   */
  async function check(force = false): Promise<UpgradeInfo | null> {
    // 5 分钟内不重复检查（除非 force）
    const now = Date.now()
    if (!force && lastChecked.value && now - lastChecked.value < 5 * 60 * 1000 && info.value) {
      return info.value
    }
    loading.value = true
    try {
      const r = await api('/api/upgrade/check')
      if (r.ok) {
        info.value = {
          ok: true,
          current: r.current || '',
          latest: r.latest || null,
          hasUpgrade: !!r.has_upgrade,
          releaseUrl: r.release_url || '',
          releaseNotes: r.release_notes || '',
          publishedAt: r.published_at || '',
          downloads: (r.downloads || []).map((d: any) => ({
            platform: d.platform,
            filename: d.filename,
            url: d.url,
            size: d.size || 0,
          })),
          note: r.note,
        }
        lastChecked.value = now
        return info.value
      } else {
        info.value = { ok: false, current: '', latest: null, hasUpgrade: false, releaseUrl: '', releaseNotes: '', publishedAt: '', downloads: [], error: r.error }
        return info.value
      }
    } finally {
      loading.value = false
    }
  }

  /** 忽略当前 latest 版本（不再显示红点） */
  function ignoreLatest() {
    if (info.value?.latest) ignoredVersion.value = info.value.latest
  }

  /** 按平台获取首选下载资产 */
  function getPreferredDownload(): UpgradeAsset | null {
    const ua = navigator.userAgent || ''
    const isWindows = /Windows/i.test(ua)
    const isMac = /Macintosh|Mac OS X/i.test(ua)
    const list = downloads.value
    if (!list.length) return null
    if (isWindows) {
      return list.find((d) => d.platform === 'windows') || null
    }
    if (isMac) {
      // pkg 优先于 dmg
      return list.find((d) => d.platform === 'macos') || list.find((d) => d.platform === 'macos-dmg') || null
    }
    return list[0] || null
  }

  /** 格式化文件大小 */
  function formatSize(bytes: number): string {
    if (!bytes) return ''
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
    return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB'
  }

  return {
    info,
    loading,
    hasUpgrade,
    currentVersion,
    latestVersion,
    downloads,
    check,
    ignoreLatest,
    getPreferredDownload,
    formatSize,
  }
})
