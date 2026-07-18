import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
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
      const params = query.trim() ? '?q=' + encodeURIComponent(query.trim()) : ''
      const r = await api<{ ok: boolean; data?: MarketItem[]; total?: number }>('/api/marketplace' + params)
      if (r.ok) {
        const real = r.data || []
        if (real.length) {
          // 真实数据存在：使用真实数据，但若用户搜索则后端已过滤
          items.value = real
          isMock.value = false
        } else if (!query.trim()) {
          // 无真实数据 + 无搜索：填充虚拟插件
          items.value = MOCK_ITEMS.slice()
          isMock.value = true
        } else {
          // 无真实数据 + 有搜索：对虚拟数据做前端过滤
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
    } finally {
      loading.value = false
    }
  }

  /** 发布插件到市场 */
  async function publish(file: string, tags: string[] = []) {
    const r = await api<{ ok: boolean; data?: MarketItem; error?: string }>(
      '/api/marketplace/publish',
      { method: 'POST', body: JSON.stringify({ file, tags }) }
    )
    if (r.ok) {
      ui.toast(`已发布「${r.data?.name || file}」到市场`)
      browse()  // 刷新列表
    } else {
      ui.toast('发布失败: ' + (r.error || ''), 'err')
    }
    return r.ok
  }

  /** 从市场安装插件 */
  async function install(id: string) {
    if (installing.value) { ui.toast('正在安装其他插件，请稍候', 'warn'); return false }
    installing.value = id
    try {
      const r = await api<{
        ok: boolean; error?: string;
        plugin_count?: number; skill_count?: number; extras_count?: number;
        skipped?: any[]
      }>('/api/marketplace/install?id=' + encodeURIComponent(id))
      if (r.ok) {
        const parts: string[] = []
        if (r.plugin_count) parts.push(`${r.plugin_count} 个插件`)
        if (r.skill_count) parts.push(`${r.skill_count} 个技能`)
        if (r.extras_count) parts.push(`${r.extras_count} 项扩展`)
        const detail = parts.length ? '：' + parts.join('、') : ''
        const skippedNote = r.skipped?.length ? `，跳过 ${r.skipped.length} 项` : ''
        ui.toast('安装成功' + detail + skippedNote)
        // 刷新相关列表
        plugin.refreshPluginList()
        skill.loadInstalledSkills()
        // 增加本地下载计数
        const item = items.value.find(i => i.id === id)
        if (item) item.downloads = (item.downloads || 0) + 1
        return true
      } else {
        ui.toast('安装失败: ' + (r.error || ''), 'err')
        return false
      }
    } finally {
      installing.value = ''
    }
  }

  /** 从市场移除 */
  async function remove(id: string) {
    if (!confirm('确认从市场移除该插件？')) return false
    const r = await api<{ ok: boolean; error?: string }>(
      '/api/marketplace/remove?id=' + encodeURIComponent(id),
      { method: 'DELETE' }
    )
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
