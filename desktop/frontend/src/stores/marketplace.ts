import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, serverApi, getServerUrl, getAuthToken } from '../api/client'
import { useUiStore } from './ui'
import { useSkillStore } from './skill'
import { usePluginStore } from './plugin'

export interface MarketItem {
  id: string
  name: string
  version: string
  description: string
  author: string
  file: string
  size: number
  published_at: string
  tags: string[]
  downloads: number
  likes?: number
  liked?: boolean
  favorited?: boolean
  author_id?: number
  scope?: string
  team_id?: number | null
}

/** 虚拟插件：当本地市场无数据时填充，演示用 */
const MOCK_ITEMS: MarketItem[] = [
  {
    id: 'mock-spring-boot',
    name: 'SpringBoot 后端工程师',
    version: '1.4.2',
    description: '精通 Spring Boot / MyBatis / MySQL 的 Java 后端开发智能体，自带 JPA、缓存、定时任务与 SQL 调优技能。',
    author: 'agentbuddy',
    file: 'mock-spring-boot.zip',
    size: 286_720,
    published_at: '2026-06-12',
    tags: ['Java', '后端', 'Spring', 'MySQL'],
    downloads: 1284,
  },
  {
    id: 'mock-vue-architect',
    name: 'Vue 前端架构师',
    version: '2.1.0',
    description: 'Vue 3 + TypeScript + Vite 工程化专家，内置组件设计、Pinia 状态管理、Composition API 最佳实践。',
    author: 'fe-collective',
    file: 'mock-vue-architect.zip',
    size: 192_512,
    published_at: '2026-07-02',
    tags: ['前端', 'Vue', 'TypeScript', '工程化'],
    downloads: 968,
  },
  {
    id: 'mock-react-fullstack',
    name: 'React 全栈开发者',
    version: '3.0.1',
    description: 'React 18 + Next.js + TailwindCSS 全栈智能体，覆盖 SSR、Edge Runtime、Server Components。',
    author: 'fe-collective',
    file: 'mock-react-fullstack.zip',
    size: 256_000,
    published_at: '2026-06-28',
    tags: ['前端', 'React', 'Next.js', '全栈'],
    downloads: 1542,
  },
  {
    id: 'mock-python-datasci',
    name: 'Python 数据科学家',
    version: '0.9.5',
    description: 'Pandas / NumPy / Scikit-learn 数据分析与建模智能体，自带 Jupyter、可视化、特征工程技能。',
    author: 'data-lab',
    file: 'mock-python-datasci.zip',
    size: 412_872,
    published_at: '2026-05-20',
    tags: ['Python', '数据', '机器学习', '分析'],
    downloads: 723,
  },
  {
    id: 'mock-devops-engineer',
    name: 'DevOps 工程师',
    version: '1.2.0',
    description: 'Docker / Kubernetes / CI-CD 流水线专家，支持 GitHub Actions、ArgoCD、Helm 与可观测性栈。',
    author: 'platform-team',
    file: 'mock-devops-engineer.zip',
    size: 348_160,
    published_at: '2026-06-15',
    tags: ['运维', 'Docker', 'Kubernetes', 'CI/CD'],
    downloads: 1102,
  },
  {
    id: 'mock-flutter-mobile',
    name: 'Flutter 跨端开发者',
    version: '0.7.3',
    description: 'Flutter + Dart 跨端开发智能体，覆盖 iOS / Android / Web / 桌面，自带 Riverpod 与动画技能。',
    author: 'mobile-guild',
    file: 'mock-flutter-mobile.zip',
    size: 224_400,
    published_at: '2026-04-30',
    tags: ['移动', 'Flutter', 'Dart', '跨端'],
    downloads: 487,
  },
  {
    id: 'mock-security-auditor',
    name: '安全审计专家',
    version: '1.0.4',
    description: '代码安全审计与渗透测试智能体，覆盖 OWASP Top 10、依赖漏洞扫描、SAST/DAST 工具链。',
    author: 'sec-ops',
    file: 'mock-security-auditor.zip',
    size: 168_960,
    published_at: '2026-07-08',
    tags: ['安全', '审计', 'OWASP', 'SAST'],
    downloads: 312,
  },
  {
    id: 'mock-test-automation',
    name: '测试自动化工程师',
    version: '2.3.0',
    description: 'Jest / Vitest / Playwright / Cypress 测试自动化专家，覆盖单元、集成、E2E 与可视化回归。',
    author: 'qa-collective',
    file: 'mock-test-automation.zip',
    size: 198_024,
    published_at: '2026-06-22',
    tags: ['测试', 'Jest', 'Playwright', 'E2E'],
    downloads: 654,
  },
  {
    id: 'mock-tech-writer',
    name: '技术文档撰写者',
    version: '0.5.1',
    description: 'Markdown / Docusaurus / MDX 技术文档智能体，内置 API 参考模板、版本管理、SEO 优化技能。',
    author: 'docs-team',
    file: 'mock-tech-writer.zip',
    size: 92_672,
    published_at: '2026-05-08',
    tags: ['文档', 'Markdown', 'Docusaurus', '写作'],
    downloads: 248,
  },
  {
    id: 'mock-rust-systems',
    name: 'Rust 系统工程师',
    version: '0.8.0',
    description: 'Rust + Tokio + Axum 系统级开发智能体，专注高性能、零成本抽象、async 并发与内存安全。',
    author: 'systems-lab',
    file: 'mock-rust-systems.zip',
    size: 274_432,
    published_at: '2026-07-12',
    tags: ['Rust', '系统', 'Tokio', '性能'],
    downloads: 189,
  },
]

export const useMarketplaceStore = defineStore('marketplace', () => {
  const ui = useUiStore()
  const skill = useSkillStore()
  const plugin = usePluginStore()

  const items = ref<MarketItem[]>([])
  const loading = ref(false)
  const searchQuery = ref('')
  const installing = ref('')  // 正在安装的 item id
  const isMock = ref(false)  // 当前是否使用虚拟数据

  /** 浏览市场（支持搜索） */
  async function browse(q?: string) {
    loading.value = true
    try {
      const query = q !== undefined ? q : searchQuery.value
      searchQuery.value = query
      const params = query.trim() ? '?q=' + encodeURIComponent(query.trim()) + '&scope=public' : '?scope=public'
      const url = serverApi('/api/marketplace' + params)
      if (!url) {
        // 无 server URL，使用虚拟数据
        if (!query.trim()) {
          items.value = MOCK_ITEMS.slice()
          isMock.value = true
        } else {
          const ql = query.trim().toLowerCase()
          items.value = MOCK_ITEMS.filter((i) =>
            i.name.toLowerCase().includes(ql) ||
            i.description.toLowerCase().includes(ql) ||
            (i.tags || []).some((t) => t.toLowerCase().includes(ql)) ||
            (i.author || '').toLowerCase().includes(ql),
          )
          isMock.value = true
        }
        return
      }
      const r = await api<{ ok: boolean; data?: MarketItem[]; total?: number }>(url)
      if (r.ok) {
        const real = r.data || []
        if (real.length) {
          items.value = real
          isMock.value = false
        } else if (!query.trim()) {
          items.value = MOCK_ITEMS.slice()
          isMock.value = true
        } else {
          const ql = query.trim().toLowerCase()
          items.value = MOCK_ITEMS.filter((i) =>
            i.name.toLowerCase().includes(ql) ||
            i.description.toLowerCase().includes(ql) ||
            (i.tags || []).some((t) => t.toLowerCase().includes(ql)) ||
            (i.author || '').toLowerCase().includes(ql),
          )
          isMock.value = true
        }
      }
    } catch {
      // 网络错误，fallback 到虚拟数据
      items.value = MOCK_ITEMS.slice()
      isMock.value = true
    } finally {
      loading.value = false
    }
  }

  /** 发布插件到市场（先从本地导出 zip，再上传到远程 server）
   *  scope: 'public' 公共市场 | 'team' 团队空间
   *  teamId: scope=team 时指定团队 ID
   */
  async function publish(file: string, tags: string[] = [], scope: 'public' | 'team' = 'public', teamId?: number) {
    const serverUrl = getServerUrl()
    if (!serverUrl) {
      ui.toast('请先配置 Server 地址', 'err')
      return false
    }
    if (scope === 'team' && !teamId) {
      ui.toast('请选择团队空间', 'err')
      return false
    }
    try {
      // 1. 从本地导出插件 zip
      const params = new URLSearchParams({ file, format: 'zip', key_mode: 'plain' })
      const exportUrl = '/api/plugin/export?' + params.toString()
      const resp = await fetch(exportUrl)
      if (!resp.ok) {
        ui.toast('导出插件失败', 'err')
        return false
      }
      const zipBlob = await resp.blob()

      // 2. 上传到远程 server
      const fd = new FormData()
      fd.append('file', zipBlob, file.replace(/\.plugin\.yaml$/, '') + '-plugin.zip')
      fd.append('tags', JSON.stringify(tags))
      fd.append('scope', scope)
      if (scope === 'team' && teamId) fd.append('team_id', String(teamId))
      const headers: Record<string, string> = {}
      const token = getAuthToken()
      if (token) headers['Authorization'] = 'Bearer ' + token
      const r = await fetch(serverApi('/api/marketplace/publish'), {
        method: 'POST',
        body: fd,
        headers,
      })
      const result = await r.json() as { ok: boolean; data?: MarketItem; error?: string }
      if (result.ok) {
        const target = scope === 'team' ? '团队空间' : '公共市场'
        ui.toast(`已发布「${result.data?.name || file}」到${target}`)
        browse()
        return true
      } else {
        ui.toast('发布失败: ' + (result.error || ''), 'err')
        return false
      }
    } catch (e: any) {
      ui.toast('发布失败: ' + (e.message || ''), 'err')
      return false
    }
  }

  /** 从市场安装插件（从远程 server 下载 zip，再本地导入） */
  async function install(id: string) {
    if (installing.value) { ui.toast('正在安装其他插件，请稍候', 'warn'); return false }
    installing.value = id
    try {
      const serverUrl = getServerUrl()
      if (!serverUrl) {
        ui.toast('请先在设置中配置 Server 地址', 'err')
        return false
      }
      // 1. 从远程 server 下载 zip
      const dlUrl = serverApi('/api/marketplace/install?id=' + encodeURIComponent(id))
      const dlHeaders: Record<string, string> = {}
      const dlToken = getAuthToken()
      if (dlToken) dlHeaders['Authorization'] = 'Bearer ' + dlToken
      const resp = await fetch(dlUrl, { headers: dlHeaders })
      if (!resp.ok) {
        const errText = await resp.text().catch(() => '')
        ui.toast('下载插件失败: ' + (resp.status === 404 ? '插件包文件丢失' : errText || `HTTP ${resp.status}`), 'err')
        return false
      }
      const zipBlob = await resp.blob()

      // 2. 本地导入 zip（后端自动完成：导入 -> 注册 -> 环境变量生效 -> generate + sync）
      const fd = new FormData()
      const fileName = items.value.find(i => i.id === id)?.file || 'plugin.zip'
      fd.append('file', zipBlob, fileName.split('/').pop() || 'plugin.zip')
      const importResp = await fetch('/api/plugin/import', { method: 'POST', body: fd })
      const result = await importResp.json() as {
        ok: boolean; error?: string;
        plugin_count?: number; skill_count?: number; extras_count?: number;
        skipped?: any[]; env_applied?: number; synced?: boolean; sync_error?: string;
      }
      if (result.ok) {
        const parts: string[] = []
        if (result.plugin_count) parts.push(`${result.plugin_count} 个插件`)
        if (result.skill_count) parts.push(`${result.skill_count} 个技能`)
        if (result.extras_count) parts.push(`${result.extras_count} 项扩展`)
        if (result.env_applied) parts.push(`${result.env_applied} 个环境变量`)
        const detail = parts.length ? '：' + parts.join('、') : ''
        const skippedNote = result.skipped?.length ? `，跳过 ${result.skipped.length} 项` : ''
        ui.toast('安装成功' + detail + skippedNote)
        if (result.synced) {
          ui.toast('已同步到 IDE')
        } else if (result.sync_error) {
          ui.toast('同步到 IDE 失败: ' + result.sync_error, 'warn')
        }
        plugin.refreshPluginList()
        skill.loadInstalledSkills()

        const item = items.value.find(i => i.id === id)
        if (item) item.downloads = (item.downloads || 0) + 1
        return true
      } else {
        ui.toast('安装失败: ' + (result.error || ''), 'err')
        return false
      }
    } catch (e: any) {
      ui.toast('安装失败: ' + (e.message || ''), 'err')
      return false
    } finally {
      installing.value = ''
    }
  }

  /** 从市场移除 */
  async function remove(id: string) {
    if (!confirm('确认从市场移除该插件？')) return false
    const url = serverApi('/api/marketplace/remove?id=' + encodeURIComponent(id))
    if (!url) {
      ui.toast('请先在设置中配置 Server 地址', 'err')
      return false
    }
    const r = await api<{ ok: boolean; error?: string }>(url, { method: 'DELETE' })
    if (r.ok) {
      ui.toast('已从市场移除')
      items.value = items.value.filter(i => i.id !== id)
      return true
    } else {
      ui.toast('移除失败: ' + (r.error || ''), 'err')
      return false
    }
  }

  return {
    items, loading, searchQuery, installing, isMock,
    browse, publish, install, remove,
  }
})
