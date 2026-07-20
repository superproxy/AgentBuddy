import { defineStore } from 'pinia'
import { reactive, computed, ref } from 'vue'
import { api } from '../api/client'
import { useUiStore } from './ui'

export const useKeysStore = defineStore('keys', () => {
  const ui = useUiStore()
  const keysData = reactive<any>({ mcp: {} })
  const keysPath = ref<string>('')
  const loaded = ref(false)
  const listQuery = ref('')

  const keyEntries = computed(() => {
    const mcp = keysData.mcp || {}
    const q = listQuery.value.trim().toLowerCase()
    const entries = Object.entries(mcp).map(([k, v]: [string, any]) => ({
      key: k,
      value: typeof v === 'string' ? v : JSON.stringify(v),
    }))
    if (!q) return entries
    return entries.filter((e) => e.key.toLowerCase().includes(q) || e.value.toLowerCase().includes(q))
  })

  const keyCount = computed(() => Object.keys(keysData.mcp || {}).length)

  async function loadKeys() {
    const r = await api('/api/keys')
    if (r.ok) {
      // 清空再赋值（保持响应式）
      Object.keys(keysData.mcp).forEach((k) => delete keysData.mcp[k])
      const data = r.data?.data?.mcp || {}
      Object.keys(data).forEach((k) => {
        keysData.mcp[k] = data[k]
      })
      keysPath.value = r.data?.path || ''
      loaded.value = true
    } else {
      ui.toast('加载密钥失败: ' + r.error, 'err')
    }
  }

  async function saveKeys() {
    const r = await api('/api/keys', { method: 'POST', body: JSON.stringify({ data: keysData }) })
    r.ok ? ui.toast('keys.yaml 已保存') : ui.toast('保存失败: ' + r.error, 'err')
  }

  async function addKey() {
    const key = await ui.askPrompt({
      title: '添加密钥 / 环境变量',
      message: '写入 config/mcp/keys.yaml，作为 ${KEY} 占位符的 fallback。占位符优先取 OS 环境变量，其次取此处。',
      label: '变量名称',
      placeholder: '例如 TAVILY_API_KEY / MODELSCOPE_TOKEN / OPENAI_API_KEY',
      confirmText: '添加',
      mono: true,
      validate: (v) => {
        if (!v) return '请输入变量名称'
        if (keysData.mcp[v]) return '变量已存在'
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(v)) return '仅支持字母、数字、下划线，且不能以数字开头'
        return null
      },
    })
    if (!key) return
    keysData.mcp[key.trim()] = ''
    ui.toast('已添加: ' + key.trim())
  }

  async function deleteKey(key: string) {
    const ok = await ui.askConfirm({
      title: '删除密钥？',
      message: '删除后不可恢复。',
      detail: key,
      confirmText: '确认删除',
      tone: 'danger',
    })
    if (!ok) return
    const r = await api('/api/keys/key/' + encodeURIComponent(key), { method: 'DELETE' })
    if (r.ok) {
      delete keysData.mcp[key]
      ui.toast('已删除')
    } else {
      ui.toast('删除失败: ' + r.error, 'err')
    }
  }

  async function updateValue(key: string, value: string) {
    keysData.mcp[key] = value
  }

  return {
    keysData,
    keysPath,
    loaded,
    listQuery,
    keyEntries,
    keyCount,
    loadKeys,
    saveKeys,
    addKey,
    deleteKey,
    updateValue,
  }
})
