import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, serverApi } from '../api/client'

export interface UserInfo {
  id: number
  username: string
  email: string
  role: string
  token: string
}

const TOKEN_KEY = 'agentbuddy-token'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const loading = ref(false)
  const dialogOpen = ref(false)
  const dialogMode = ref<'login' | 'register'>('login')

  const isLoggedIn = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const username = computed(() => user.value?.username || '')

  /** 从 localStorage 恢复登录状态（同步，在 store 创建时立即执行） */
  function _restore() {
    try {
      const stored = localStorage.getItem(TOKEN_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        if (parsed && parsed.token) {
          user.value = parsed
        }
      }
    } catch { /* ignore */ }
  }
  // 立即执行，不等待 onMounted
  _restore()

  /** 公开恢复方法（兼容旧调用） */
  function restore() {
    _restore()
  }

  /** 获取 token（供 api 调用时添加 header） */
  function getToken(): string | null {
    return user.value?.token || null
  }

  /** 登录 */
  async function login(username: string, password: string): Promise<boolean> {
    loading.value = true
    try {
      const url = serverApi('/api/auth/login')
      if (!url) return false
      const r = await api<{ ok: boolean; data?: UserInfo; error?: string }>(url, {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      if (r.ok && r.data) {
        user.value = r.data
        localStorage.setItem(TOKEN_KEY, JSON.stringify(r.data))
        return true
      }
      return false
    } catch {
      return false
    } finally {
      loading.value = false
    }
  }

  /** 注册 */
  async function register(username: string, password: string, email?: string): Promise<{ ok: boolean; error?: string }> {
    loading.value = true
    try {
      const url = serverApi('/api/auth/register')
      if (!url) return { ok: false, error: '未配置 Server 地址' }
      const r = await api<{ ok: boolean; data?: UserInfo; error?: string }>(url, {
        method: 'POST',
        body: JSON.stringify({ username, password, email }),
      })
      if (r.ok && r.data) {
        user.value = r.data
        localStorage.setItem(TOKEN_KEY, JSON.stringify(r.data))
        return { ok: true }
      }
      return { ok: false, error: r.error || '注册失败' }
    } catch (e: any) {
      return { ok: false, error: e.message || '网络错误' }
    } finally {
      loading.value = false
    }
  }

  /** 退出登录 */
  function logout() {
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
  }

  /** 打开登录弹窗 */
  function openLogin() {
    dialogMode.value = 'login'
    dialogOpen.value = true
  }

  /** 打开注册弹窗 */
  function openRegister() {
    dialogMode.value = 'register'
    dialogOpen.value = true
  }

  /** 关闭弹窗 */
  function closeDialog() {
    dialogOpen.value = false
  }

  return {
    user, loading, dialogOpen, dialogMode,
    isLoggedIn, isAdmin, username,
    restore, getToken, login, register, logout,
    openLogin, openRegister, closeDialog,
  }
})
