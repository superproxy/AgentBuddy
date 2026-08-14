import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, serverApi, getServerUrl } from '../api/client'
import { runSse } from '../api/sse'
import { useUiStore } from './ui'
import { usePluginStore } from './plugin'

export const useAiGenerateStore = defineStore('aiGenerate', () => {
  const ui = useUiStore()
  const plugin = usePluginStore()

  const dialogOpen = ref(false)
  const prompt = ref('')
  const level = ref<'basic' | 'standard' | 'expert' | ''>('')
  const generating = ref(false)
  const output = ref('')
  const generatedConfig = ref('')

  function openDialog() {
    dialogOpen.value = true
    prompt.value = ''
    level.value = ''
    output.value = ''
    generatedConfig.value = ''
  }

  function closeDialog() {
    dialogOpen.value = false
  }

  async function generate() {
    if (!prompt.value.trim()) {
      ui.toast('请输入需求描述', 'warn')
      return
    }
    const serverUrl = getServerUrl()
    if (!serverUrl) {
      ui.toast('请先在设置中配置 Server 地址', 'err')
      return
    }
    generating.value = true
    output.value = ''
    generatedConfig.value = ''
    ui.clearLog()

    const url = serverApi('/api/ai/generate?prompt=' + encodeURIComponent(prompt.value.trim())
      + '&model=glm-5-2-260617'
      + (level.value ? '&level=' + level.value : ''))
    if (!url) {
      ui.toast('请先在设置中配置 Server 地址', 'err')
      generating.value = false
      return
    }
    await runSse(url, (line) => {
      output.value += line + '\n'
      ui.appendLog(line)
    }, {
      onDone: () => {
        const text = output.value
        // 1. 优先提取 ```yaml ... ``` 代码块
        const match = text.match(/```ya?ml?\n([\s\S]*?)```/)
        if (match) {
          generatedConfig.value = match[1].trim()
          generating.value = false
          return
        }
        // 2. 过滤掉 [INFO] [ERROR] [DONE] 等控制行，提取 YAML 内容
        const lines = text.split('\n').filter((l: string) =>
          !l.startsWith('[INFO]') && !l.startsWith('[ERROR]') && !l.startsWith('[DONE]')
        )
        // 找到 name: 开头的行作为 YAML 起始
        const yamlStartIdx = lines.findIndex((l: string) => l.trim().startsWith('name:'))
        if (yamlStartIdx >= 0) {
          // 找到 YAML 结束位置（下一个空行后的非缩进行 或 文件末尾）
          let yamlEnd = lines.length
          for (let i = yamlStartIdx + 1; i < lines.length; i++) {
            // YAML 内容行：空行、缩进行、或 yaml 关键字
            const trimmed = lines[i].trim()
            if (trimmed === '' || lines[i].startsWith(' ') || lines[i].startsWith('\t')) continue
            // 检查是否是 yaml 顶级 key
            if (/^[a-zA-Z_]+:/.test(trimmed)) continue
            // 否则认为 YAML 结束
            yamlEnd = i
            break
          }
          generatedConfig.value = lines.slice(yamlStartIdx, yamlEnd).join('\n').trim()
        }
        generating.value = false
      }
    })
  }

  async function save() {
    if (!generatedConfig.value) {
      ui.toast('没有可保存的配置', 'warn')
      return
    }
    // 保存到本地（通过本地 config_server）
    try {
      const data = JSON.stringify({ content: generatedConfig.value })
      const r = await api<{ ok: boolean; path?: string; name?: string; error?: string }>(
        '/api/plugin/save-ai',
        { method: 'POST', body: data }
      )
      if (r.ok) {
        ui.toast(`已保存: ${r.name}`)
        plugin.refreshPluginList()
        closeDialog()
      } else {
        ui.toast('保存失败: ' + (r.error || ''), 'err')
      }
    } catch {
      // fallback: 直接用 yaml 内容创建插件
      ui.toast('保存失败，请手动复制 YAML 内容', 'err')
    }
  }

  return {
    dialogOpen, prompt, level, generating, output, generatedConfig,
    openDialog, closeDialog, generate, save,
  }
})
