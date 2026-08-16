import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { serverApi, serverJsonApi, getServerUrl, getAuthToken } from '../api/client'
import { useUiStore } from './ui'
import { usePluginStore } from './plugin'

/** 会话消息：user/assistant 为对话，analysis 为本地来源分析卡片（content 存 JSON） */
export interface ChatMessage {
  role: 'user' | 'assistant' | 'analysis'
  content: string
  streaming?: boolean
}

export interface BuildSession {
  id: string            // 本地 id
  serverSessionId: string // 服务端多轮会话 id（/api/ai/chat）
  title: string
  messages: ChatMessage[]
  yaml: string          // 最新生成的 plugin.yaml
  version: number       // 第几版（每轮生成 +1）
  source: string        // 已分析的来源（构建时优先走 /api/plugin/build）
  pendingContext: string // 起点注入的上下文（随下一条消息发送，不在气泡展示）
  updatedAt: number
}

const LS_KEY = 'agentbuddy-build-chat-sessions'
const MAX_SESSIONS = 20

/** 检测输入中的来源（GitHub owner/repo 简写或 URL） */
export function detectSource(text: string): string | null {
  const t = text.trim()
  // https://github.com/owner/repo 或任意 http(s) URL
  const url = t.match(/https?:\/\/[^\s，。,'"（）()]+/i)
  if (url) return url[0]
  // owner/repo 简写（独立词，各段 2-60 字符）
  const repo = t.match(/(^|[\s（(])((?:[A-Za-z0-9][A-Za-z0-9_.-]{1,60})\/(?:[A-Za-z0-9][A-Za-z0-9._-]{1,60}))($|[\s，。'"）),])/)
  if (repo) return repo[2]
  return null
}

/** 从 SSE 文本提取 yaml 代码块（优先 ```yaml，回退找 name: 起始段） */
function extractYaml(text: string): string {
  const m = text.match(/```ya?ml?\n([\s\S]*?)```/)
  if (m) return m[1].trim()
  const lines = text.split('\n').filter(l =>
    !l.startsWith('[INFO]') && !l.startsWith('[ERROR]') && !l.startsWith('[DONE]')
    && !l.startsWith('[TURN]') && !l.startsWith('[TOOL') && !l.startsWith('[SESSION]') && !l.startsWith('[CONFIG]'))
  const start = lines.findIndex(l => l.trim().startsWith('name:'))
  if (start < 0) return ''
  let end = lines.length
  for (let i = start + 1; i < lines.length; i++) {
    const t = lines[i].trim()
    if (t === '' || lines[i].startsWith(' ') || lines[i].startsWith('\t')) continue
    if (/^[a-zA-Z_]+:/.test(t)) continue
    end = i
    break
  }
  return lines.slice(start, end).join('\n').trim()
}

/** POST + SSE 逐行回调（服务端 /api/ai/chat 是 POST 流式） */
async function ssePost(url: string, body: any, onLine: (line: string) => void): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getAuthToken()
  if (token) headers.Authorization = 'Bearer ' + token
  const resp = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) })
  if (!resp.ok || !resp.body) {
    const t = await resp.text().catch(() => '')
    throw new Error(`HTTP ${resp.status} ${t.slice(0, 120)}`)
  }
  const reader = resp.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop() || ''
    for (const p of parts) {
      const line = p.replace(/^data: ?/m, '').trim()
      if (line) onLine(line)
    }
  }
}

function newLocalId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7)
}

export const useBuildChatStore = defineStore('buildChat', () => {
  const ui = useUiStore()
  const plugin = usePluginStore()

  const sessions = ref<BuildSession[]>([])
  const activeId = ref('')
  const input = ref('')
  const sending = ref(false)
  const building = ref(false)
  const advancedOpen = ref(false)

  const active = computed(() => sessions.value.find(s => s.id === activeId.value) || null)
  const activeYaml = computed(() => active.value?.yaml || '')

  // ---- 持久化 ----
  function persist() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(sessions.value.slice(0, MAX_SESSIONS)))
    } catch { /* 空间满等忽略 */ }
  }
  function restore() {
    if (sessions.value.length) return
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (raw) sessions.value = JSON.parse(raw) || []
    } catch { sessions.value = [] }
    if (!sessions.value.length) newSession()
    else activeId.value = sessions.value[0].id
  }

  function newSession() {
    const s: BuildSession = {
      id: newLocalId(), serverSessionId: '', title: '新会话',
      messages: [], yaml: '', version: 0, source: '', pendingContext: '',
      updatedAt: Date.now(),
    }
    sessions.value.unshift(s)
    activeId.value = s.id
    if (sessions.value.length > MAX_SESSIONS) sessions.value.pop()
    persist()
  }

  function selectSession(id: string) {
    activeId.value = id
    // 服务端会话若还活着，拉取最新配置（服务端重启后会话丢失则静默降级）
    const s = active.value
    if (s && s.serverSessionId && s.yaml) {
      const url = serverApi('/api/ai/session/' + s.serverSessionId + '/config')
      if (url) {
        fetch(url, { headers: { Authorization: 'Bearer ' + (getAuthToken() || '') } })
          .then(r => (r.ok ? r.json() : null))
          .then((d: any) => {
            if (d && d.ok && d.content) {
              s.yaml = d.content
              persist()
            }
          }).catch(() => { /* 网络异常忽略 */ })
      }
    }
  }

  function removeSession(id: string) {
    const s = sessions.value.find(x => x.id === id)
    if (s?.serverSessionId) {
      const url = serverApi('/api/ai/session/' + s.serverSessionId)
      if (url) fetch(url, { method: 'DELETE' }).catch(() => { /* 忽略 */ })
    }
    sessions.value = sessions.value.filter(x => x.id !== id)
    if (activeId.value === id) {
      activeId.value = sessions.value[0]?.id || ''
      if (!sessions.value.length) newSession()
    }
    persist()
  }

  /** 分析来源（服务端能力），生成注入对话的紧凑上下文 */
  async function analyzeSource(source: string): Promise<{ meta: any; context: string } | null> {
    try {
      const r = await serverJsonApi<any>('/api/plugin/analyze', {
        method: 'POST',
        body: JSON.stringify({ source, ai: false }),
      })
      if (!r.ok || !r.data) return null
      const d = r.data
      const skills = (d.skills || []).map((s: any) => s.name).slice(0, 30)
      const mcps = Object.keys(d.mcpServers || {}).slice(0, 30)
      const envs = Object.keys(d.envVars || {})
      const context = [
        '[来源分析结果 — 服务端分析，真实数据非猜测]',
        `name: ${d.name || ''}`,
        `version: ${d.version || '1.0.0'}`,
        `description: ${String(d.description || '').slice(0, 200)}`,
        `skills(${skills.length}): ${skills.join(', ')}`,
        `mcpServers(${mcps.length}): ${mcps.join(', ')}`,
        envs.length ? `envVars: ${envs.join(', ')}` : '',
        '请基于以上真实分析结果生成/更新 plugin.yaml。',
      ].filter(Boolean).join('\n')
      return { meta: d, context }
    } catch { return null }
  }

  /** 发送一轮：来源检测 → 本地分析注入 → 服务端多轮生成 → 提取 YAML */
  async function send() {
    const s = active.value
    const text = input.value.trim()
    if (!s || !text || sending.value) return
    if (!getServerUrl()) { ui.toast('请先在设置中配置 Server 地址', 'err'); return }

    sending.value = true
    input.value = ''
    s.messages.push({ role: 'user', content: text })
    let outgoing = text
    // 起点注入的上下文（本地 skills 素材等）：随首条消息发给 AI，不在气泡中展示
    if (s.pendingContext) {
      outgoing = `${text}\n\n${s.pendingContext}`
      s.pendingContext = ''
    }

    try {
      // 1. 来源检测 + 本地分析（免 LLM、带缓存）
      const src = detectSource(text)
      if (src && src !== s.source) {
        ui.toast('检测到来源，正在本地分析…')
        const a = await analyzeSource(src)
        if (a) {
          s.source = src
          s.messages.push({
            role: 'analysis',
            content: JSON.stringify({
              source: src, name: a.meta.name, version: a.meta.version,
              description: String(a.meta.description || '').slice(0, 160),
              skills: (a.meta.skills || []).map((x: any) => x.name),
              mcpServers: Object.keys(a.meta.mcpServers || {}),
              envVars: Object.keys(a.meta.envVars || {}),
            }),
          })
          outgoing = `${text}\n\n${a.context}`
        }
      } else if (src && src === s.source) {
        outgoing = `${text}\n\n（继续基于此前 [来源分析结果] 操作）`
      }

      // 2. 标题：首条消息取前 16 字
      if (s.title === '新会话') {
        s.title = text.replace(/\s+/g, ' ').slice(0, 16) || '新会话'
      }

      // 3. 服务端多轮生成（SSE）
      const url = serverApi('/api/ai/chat')
      if (!url) { ui.toast('请先在设置中配置 Server 地址', 'err'); return }
      const asst: ChatMessage = { role: 'assistant', content: '', streaming: true }
      s.messages.push(asst)
      let raw = ''
      await ssePost(url, {
        session_id: s.serverSessionId || '',
        message: outgoing,
      }, (line) => {
        if (line.startsWith('[SESSION] ')) {
          s.serverSessionId = line.slice(10).trim()
          return
        }
        // 控制标记不进入气泡，但保留在原始流里用于 YAML 提取
        raw += line + '\n'
        const visible = line.startsWith('[TURN]') || line.startsWith('[TOOL') ||
          line.startsWith('[DONE]') || line.startsWith('[CONFIG]') || line.startsWith('[INFO]')
          ? '' : line
        if (visible) asst.content += (asst.content ? '\n' : '') + visible
      })
      asst.streaming = false

      // 4. 提取配置（生成能够确认效果：预览区展示最新版）
      const y = extractYaml(raw)
      if (y) {
        s.yaml = y
        s.version += 1
      }
      s.updatedAt = Date.now()
      persist()
    } catch (e: any) {
      const msg = e?.name === 'TypeError' ? '网络请求失败，请检查 Server 地址与网络' : (e.message || String(e))
      s.messages.push({ role: 'assistant', content: `❌ ${msg}` })
    } finally {
      sending.value = false
      persist()
    }
  }

  /** 构建当前配置：有来源走 build（打包 zip），无来源走 save-ai（存插件管理） */
  async function build(publish = false) {
    const s = active.value
    if (!s || !s.yaml || building.value) return
    building.value = true
    try {
      // 前端无 yaml 解析器：用正则取 name；完整配置经 config_yaml 传后端解析覆盖，
      // 保真 AI 多轮打磨的修改（后端 pyyaml 解析并套用，skills 仍从源仓库下载）
      const nameM = s.yaml.match(/^name:\s*(.+)$/m)
      const name = (nameM ? nameM[1] : '').trim().replace(/^['"]|['"]$/g, '')
      const r = await serverJsonApi<any>('/api/plugin/build', {
        method: 'POST',
        body: JSON.stringify({
          source: s.source || undefined,
          ai: false,
          name: name || undefined,
          config_yaml: s.yaml,
          publish,
        }),
      })
      if (r.ok) {
        ui.toast(publish ? '已在服务端构建并发布' : `服务端构建成功: ${r.data?.zipPath || ''}`)
        plugin.refreshPluginList()
      } else {
        ui.toast('构建失败: ' + (r.error || r.publishError || ''), 'err')
      }
    } finally {
      building.value = false
    }
  }

  /** 起点A-1：从来源开始（自动分析注入 + 首条消息） */
  async function startFromSource(source: string) {
    const s = active.value
    const src = source.trim()
    if (!s || !src || sending.value) return
    input.value = `帮我基于 ${src} 构建一个插件`
    await send()
  }

  /** 起点A-2：从本地已装 skills 开始（勾选素材注入 + 首条消息） */
  function startFromLocalSkills(names: string[], metas: { name: string; description?: string }[]) {
    const s = active.value
    if (!s || !names.length || sending.value) return
    const lines = metas
      .filter(m => names.includes(m.name))
      .map(m => `- ${m.name}: ${String(m.description || '').slice(0, 80)}`)
    s.pendingContext = [
      '[本地已有 skills 素材 — 用户勾选，均已安装可直接打包]',
      ...lines,
      '请基于以上已有 skills 组合成一个插件（合理命名、写描述），生成 plugin.yaml。',
    ].join('\n')
    s.messages.push({
      role: 'analysis',
      content: JSON.stringify({
        source: `本地 skills（${names.length} 个）`, name: `${names.length} 个本地 skills`,
        version: '', description: '', skills: names, mcpServers: [], envVars: [],
      }),
    })
    input.value = `请把这 ${names.length} 个本地 skills 打包成一个插件`
    void send()
  }

  return {
    sessions, activeId, active, activeYaml, input, sending, building, advancedOpen,
    restore, newSession, selectSession, removeSession, send, build,
    startFromSource, startFromLocalSkills,
  }
})
