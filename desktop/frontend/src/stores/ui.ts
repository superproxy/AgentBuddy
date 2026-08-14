/**
 * 全局 UI 状态（toast / modal / dialog / log）
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Toast {
  id: number
  msg: string
  type: 'ok' | 'err' | 'warn'
}

export type DialogTone = 'brand' | 'danger'

export interface PromptDialogOptions {
  title: string
  message?: string
  label?: string
  placeholder?: string
  defaultValue?: string
  confirmText?: string
  cancelText?: string
  /** 校验失败返回错误文案；通过返回 null */
  validate?: (value: string) => string | null
  tone?: DialogTone
  mono?: boolean
}

export interface DialogLink {
  label: string
  href: string
}

export interface ConfirmDialogOptions {
  title: string
  message: string
  detail?: string
  confirmText?: string
  cancelText?: string
  tone?: DialogTone
  /** 可点击外链（如文档、申请页） */
  links?: DialogLink[]
}

type DialogKind = 'prompt' | 'confirm'

interface DialogState {
  visible: boolean
  kind: DialogKind
  title: string
  message: string
  detail: string
  label: string
  placeholder: string
  value: string
  error: string
  confirmText: string
  cancelText: string
  tone: DialogTone
  mono: boolean
  links: DialogLink[]
}

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<Toast[]>([])
  const modalVisible = ref(false)
  const modalTitle = ref('')
  const modalContent = ref('')
  const logVisible = ref(false)
  const logText = ref('')

  const dialog = ref<DialogState>({
    visible: false,
    kind: 'confirm',
    title: '',
    message: '',
    detail: '',
    label: '',
    placeholder: '',
    value: '',
    error: '',
    confirmText: '确认',
    cancelText: '取消',
    tone: 'brand',
    mono: false,
    links: [],
  })

  let toastId = 0
  let dialogResolve: ((value: string | boolean | null) => void) | null = null
  let dialogValidate: ((value: string) => string | null) | null = null

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

  function closeDialog(result: string | boolean | null) {
    if (!dialog.value.visible) return
    dialog.value.visible = false
    dialogValidate = null
    const resolve = dialogResolve
    dialogResolve = null
    resolve?.(result)
  }

  function askPrompt(opts: PromptDialogOptions): Promise<string | null> {
    return new Promise((resolve) => {
      if (dialogResolve) closeDialog(null)
      dialogResolve = resolve as (v: string | boolean | null) => void
      dialogValidate = opts.validate || null
      dialog.value = {
        visible: true,
        kind: 'prompt',
        title: opts.title,
        message: opts.message || '',
        detail: '',
        label: opts.label || '',
        placeholder: opts.placeholder || '',
        value: opts.defaultValue || '',
        error: '',
        confirmText: opts.confirmText || '确认',
        cancelText: opts.cancelText || '取消',
        tone: opts.tone || 'brand',
        mono: !!opts.mono,
        links: [],
      }
    })
  }

  function askConfirm(opts: ConfirmDialogOptions): Promise<boolean> {
    return new Promise((resolve) => {
      if (dialogResolve) closeDialog(null)
      dialogResolve = resolve as (v: string | boolean | null) => void
      dialogValidate = null
      dialog.value = {
        visible: true,
        kind: 'confirm',
        title: opts.title,
        message: opts.message,
        detail: opts.detail || '',
        label: '',
        placeholder: '',
        value: '',
        error: '',
        confirmText: opts.confirmText || '确认',
        cancelText: opts.cancelText || '取消',
        tone: opts.tone || 'danger',
        mono: false,
        links: opts.links || [],
      }
    })
  }

  function submitDialog() {
    if (!dialog.value.visible) return
    if (dialog.value.kind === 'confirm') {
      closeDialog(true)
      return
    }
    const raw = dialog.value.value
    const trimmed = raw.trim()
    if (dialogValidate) {
      const err = dialogValidate(trimmed)
      if (err) {
        dialog.value.error = err
        return
      }
    } else if (!trimmed) {
      dialog.value.error = '请填写内容'
      return
    }
    dialog.value.error = ''
    closeDialog(trimmed)
  }

  function cancelDialog() {
    closeDialog(dialog.value.kind === 'confirm' ? false : null)
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
    dialog,
    toast,
    showModal,
    askPrompt,
    askConfirm,
    submitDialog,
    cancelDialog,
    appendLog,
    clearLog,
  }
})
