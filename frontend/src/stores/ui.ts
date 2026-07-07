/**
 * 全局 UI 状态（toast / modal / log）—— 从 config_ui.html L1251-1276 迁移。
 * 原来散落在 setup() 的本地 ref，现在集中到 Pinia store，任意组件可调。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Toast {
  id: number
  msg: string
  type: 'ok' | 'err' | 'warn'
}

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<Toast[]>([])
  const modalVisible = ref(false)
  const modalTitle = ref('')
  const modalContent = ref('')
  const logVisible = ref(false)
  const logText = ref('')

  let toastId = 0

  function toast(msg: string, type: Toast['type'] = 'ok') {
    const id = ++toastId
    toasts.value.push({ id, msg, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, 3000)
  }

  function showModal(title: string, content: string) {
    modalTitle.value = title
    modalContent.value = content
    modalVisible.value = true
  }

  /** 追加一行日志并自动展开日志面板 */
  function appendLog(text: string) {
    logText.value += text + '\n'
    logVisible.value = true
  }

  function clearLog() {
    logText.value = ''
  }

  return {
    toasts,
    modalVisible,
    modalTitle,
    modalContent,
    logVisible,
    logText,
    toast,
    showModal,
    appendLog,
    clearLog,
  }
})
