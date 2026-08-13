<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMarketplaceStore } from '../stores/marketplace'
import { usePluginStore } from '../stores/plugin'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'
import { serverApi, api, getAuthToken } from '../api/client'

const mkt = useMarketplaceStore()
const { items, loading, searchQuery, installing, isMock } = storeToRefs(mkt)

const pluginStore = usePluginStore()
const { plugins, installingPlugin } = storeToRefs(pluginStore)
const { refreshPluginList, onTogglePlugin, editPlugin, publishToMarketplace } = pluginStore

const ui = useUiStore()
const auth = useAuthStore()

// === Tab 切换 ===
type TabKey = 'market' | 'mine' | 'team'
// 支持从独立菜单（我的发布）进入时直接定位到对应 Tab
const props = defineProps<{ initialTab?: TabKey }>()
const activeTab = ref<TabKey>(props.initialTab || 'market')

// === 我的发布 + 收藏 + 点赞 ===
const myPlugins = ref<any[]>([])
const myFavorites = ref<any[]>([])
const myLiked = ref<any[]>([])
const myLoading = ref(false)

async function loadMyPlugins() {
  if (!auth.isLoggedIn) return
  myLoading.value = true
  try {
    const url = serverApi('/api/marketplace/mine')
    if (!url) return
    const r = await api<{ ok: boolean; data?: any[] }>(url)
    if (r.ok) myPlugins.value = r.data || []
  } catch { /* ignore */ } finally {
    myLoading.value = false
  }
}

async function deletePlugin(id: string) {
  if (!confirm('确定删除这个插件？')) return
  try {
    const url = serverApi('/api/marketplace/remove?id=' + encodeURIComponent(id))
    if (!url) return
    await fetch(url, { method: 'DELETE', headers: { Authorization: 'Bearer ' + getAuthToken() } })
    myPlugins.value = myPlugins.value.filter((p: any) => p.id !== id)
    // 同步刷新公共市场列表
    items.value = items.value.filter((i: any) => i.id !== id)
    // 如果在团队详情页，同步刷新团队插件
    if (selectedSpaceId.value) {
      teamPlugins.value = teamPlugins.value.filter((p: any) => p.id !== id)
    }
  } catch { /* ignore */ }
}

// 点赞/取消点赞
async function toggleLike(p: any) {
  if (!auth.isLoggedIn) { ui.toast('请先登录', 'warn'); auth.openLogin(); return }
  try {
    const url = serverApi(`/api/marketplace/${p.id}/like`)
    if (!url) return
    const r = await api<{ ok: boolean; data?: { liked: boolean } }>(url, { method: 'POST' })
    if (r.ok && r.data) {
      p.liked = r.data.liked
      p.likes = (p.likes || 0) + (r.data.liked ? 1 : -1)
    }
  } catch { /* ignore */ }
}

// 收藏/取消收藏
async function toggleFavorite(p: any) {
  if (!auth.isLoggedIn) { ui.toast('请先登录', 'warn'); auth.openLogin(); return }
  try {
    const url = serverApi(`/api/marketplace/${p.id}/favorite`)
    if (!url) return
    const r = await api<{ ok: boolean; data?: { favorited: boolean } }>(url, { method: 'POST' })
    if (r.ok && r.data) {
      p.favorited = r.data.favorited
      ui.toast(r.data.favorited ? '已收藏' : '已取消收藏', r.data.favorited ? 'ok' : 'warn')
    }
  } catch { /* ignore */ }
}

// 下载插件 zip（fetch blob → 触发浏览器下载，兼容 Electron 跨域）
async function downloadPlugin(p: any) {
  try {
    const url = serverApi('/api/marketplace/download?id=' + encodeURIComponent(p.id))
    if (!url) { ui.toast('请先配置 Server 地址', 'err'); return }
    const headers: Record<string, string> = {}
    const token = getAuthToken()
    if (token) headers['Authorization'] = 'Bearer ' + token
    const resp = await fetch(url, { headers })
    if (!resp.ok) { ui.toast('下载失败: HTTP ' + resp.status, 'err'); return }
    const blob = await resp.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = (p.name || 'plugin') + '-v' + (p.version || '1.0.0') + '.zip'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(a.href)
  } catch (e: any) {
    ui.toast('下载失败: ' + (e.message || ''), 'err')
  }
}

// 加载收藏列表
async function loadFavorites() {
  if (!auth.isLoggedIn) return
  try {
    const url = serverApi('/api/marketplace/favorites')
    if (!url) return
    const r = await api<{ ok: boolean; data?: any[] }>(url)
    if (r.ok) myFavorites.value = r.data || []
  } catch { /* ignore */ }
}

// 加载点赞列表
async function loadLiked() {
  if (!auth.isLoggedIn) return
  try {
    const url = serverApi('/api/marketplace/liked')
    if (!url) return
    const r = await api<{ ok: boolean; data?: any[] }>(url)
    if (r.ok) myLiked.value = r.data || []
  } catch { /* ignore */ }
}

watch(activeTab, (tab) => {
  if (tab === 'mine') { loadMyPlugins(); loadFavorites(); loadLiked() }
  if (tab === 'team') loadTeams()
})

// === 团队空间（真实 API） ===
interface TeamMember {
  id: number
  username: string
  email: string
  role: 'owner' | 'member'
  joined_at: string
}
interface TeamSpace {
  id: number
  name: string
  description: string
  owner_id: number
  created_at: string
  role: string
  member_count: number
}

const teamSpaces = ref<TeamSpace[]>([])
const teamsLoading = ref(false)
const teamSearchQuery = ref('')
const selectedSpaceId = ref<number | null>(null)
const createSpaceOpen = ref(false)
const inviteOpen = ref(false)
const newSpaceName = ref('')
const newSpaceDesc = ref('')
const inviteInput = ref('')
const inviteError = ref('')
const teamMembers = ref<TeamMember[]>([])
const membersLoading = ref(false)
const teamPlugins = ref<any[]>([])
const teamPluginsLoading = ref(false)

const filteredTeamSpaces = computed(() => {
  if (!teamSearchQuery.value.trim()) return teamSpaces.value
  const q = teamSearchQuery.value.trim().toLowerCase()
  return teamSpaces.value.filter(s =>
    s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q),
  )
})

const selectedSpace = computed(() => teamSpaces.value.find(s => s.id === selectedSpaceId.value))

async function loadTeams() {
  if (!auth.isLoggedIn) return
  teamsLoading.value = true
  try {
    const url = serverApi('/api/teams')
    if (!url) return
    const r = await api<{ ok: boolean; data?: TeamSpace[] }>(url)
    if (r.ok) teamSpaces.value = r.data || []
  } catch { /* ignore */ } finally {
    teamsLoading.value = false
  }
}

async function openSpaceDetail(id: number) {
  selectedSpaceId.value = id
  await Promise.all([loadTeamMembers(id), loadTeamPlugins(id)])
}

async function loadTeamMembers(teamId: number) {
  membersLoading.value = true
  try {
    const url = serverApi(`/api/teams/${teamId}/members`)
    if (!url) return
    const r = await api<{ ok: boolean; data?: TeamMember[] }>(url)
    if (r.ok) teamMembers.value = r.data || []
  } catch { /* ignore */ } finally {
    membersLoading.value = false
  }
}

async function loadTeamPlugins(teamId: number) {
  teamPluginsLoading.value = true
  try {
    const url = serverApi(`/api/marketplace?scope=team&team_id=${teamId}`)
    if (!url) return
    const r = await api<{ ok: boolean; data?: any[] }>(url)
    if (r.ok) {
      teamPlugins.value = (r.data || []).filter((p: any) => p.team_id === teamId)
    }
  } catch { /* ignore */ } finally {
    teamPluginsLoading.value = false
  }
}

function backToSpaceList() {
  selectedSpaceId.value = null
  teamMembers.value = []
  teamPlugins.value = []
}

function showCreateSpace() {
  newSpaceName.value = ''
  newSpaceDesc.value = ''
  createSpaceOpen.value = true
}

async function createSpace() {
  if (!newSpaceName.value.trim()) {
    ui.toast('请输入空间名称', 'warn')
    return
  }
  try {
    const url = serverApi('/api/teams')
    if (!url) return
    const r = await api<{ ok: boolean; data?: TeamSpace }>(url, {
      method: 'POST',
      body: JSON.stringify({ name: newSpaceName.value.trim(), description: newSpaceDesc.value.trim() }),
    })
    if (r.ok) {
      ui.toast(`团队空间「${newSpaceName.value}」创建成功`, 'ok')
      createSpaceOpen.value = false
      await loadTeams()
      if (r.data) openSpaceDetail(r.data.id)
    } else {
      ui.toast(r.error || '创建失败', 'err')
    }
  } catch { ui.toast('网络错误', 'err') }
}

function showInvite() {
  inviteInput.value = ''
  inviteError.value = ''
  inviteOpen.value = true
}

async function sendInvite() {
  if (!inviteInput.value.trim()) {
    inviteError.value = '请输入用户名'
    return
  }
  if (!selectedSpaceId.value) return
  try {
    const url = serverApi(`/api/teams/${selectedSpaceId.value}/invite`)
    if (!url) return
    const r = await api<{ ok: boolean; error?: string }>(url, {
      method: 'POST',
      body: JSON.stringify({ username: inviteInput.value.trim() }),
    })
    if (r.ok) {
      ui.toast(`已向 ${inviteInput.value} 发送邀请，等待对方确认`, 'ok')
      inviteOpen.value = false
      await loadTeamMembers(selectedSpaceId.value)
      await loadTeams()
    } else {
      inviteError.value = r.error || '邀请失败'
    }
  } catch { inviteError.value = '网络错误' }
}

async function removeMember(username: string) {
  if (!selectedSpaceId.value) return
  if (!confirm(`确定移除 ${username}？`)) return
  try {
    const url = serverApi(`/api/teams/${selectedSpaceId.value}/members/${username}`)
    if (!url) return
    await fetch(url, { method: 'DELETE', headers: { Authorization: 'Bearer ' + getAuthToken() } })
    await loadTeamMembers(selectedSpaceId.value)
    await loadTeams()
  } catch { /* ignore */ }
}

async function deleteTeamPlugin(pluginId: string) {
  if (!confirm('确定删除这个插件？')) return
  try {
    const url = serverApi('/api/marketplace/remove?id=' + encodeURIComponent(pluginId))
    if (!url) return
    await fetch(url, { method: 'DELETE', headers: { Authorization: 'Bearer ' + getAuthToken() } })
    teamPlugins.value = teamPlugins.value.filter(p => p.id !== pluginId)
    // 同步刷新公共市场列表和我的发布
    items.value = items.value.filter((i: any) => i.id !== pluginId)
    myPlugins.value = myPlugins.value.filter((p: any) => p.id !== pluginId)
  } catch { /* ignore */ }
}

// === 发布对话框 ===
const publishDialogOpen = ref(false)
const publishFile = ref('')
const publishScope = ref<'public' | 'team'>('public')
const publishTeamId = ref<number | null>(null)

function openPublishDialog(file: string) {
  publishFile.value = file
  publishScope.value = 'public'
  publishTeamId.value = null
  publishDialogOpen.value = true
}

async function doPublish() {
  publishDialogOpen.value = false
  await publishToMarketplace(publishFile.value, publishScope.value, publishTeamId.value || undefined)
  // 如果在团队详情页，刷新团队插件
  if (publishScope.value === 'team' && publishTeamId.value && selectedSpaceId.value === publishTeamId.value) {
    await loadTeamPlugins(publishTeamId.value)
  }
}

// 热门推荐：从服务端市场数据按 downloads + likes 排序，取前 4
const featuredPlugins = computed(() => {
  return items.value
    .slice()
    .sort((a, b) => ((b.downloads || 0) + (b.likes || 0)) - ((a.downloads || 0) + (a.likes || 0)))
    .slice(0, 4)
})

type SortKey = 'new' | 'hot' | 'name'
type ViewMode = 'grid' | 'list'

const activeTags = ref<string[]>([])
const activeAuthor = ref('')
const sort = ref<SortKey>('new')
const view = ref<ViewMode>('grid')

let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => mkt.browse(), 300)
}

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatDate(iso: string): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch {
    return iso
  }
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  return parts.slice(0, 2).map((w) => w[0]!.toUpperCase()).join('')
}

const tagCounts = computed(() => {
  const map: Record<string, number> = {}
  for (const item of items.value) {
    for (const t of item.tags || []) map[t] = (map[t] || 0) + 1
  }
  return Object.entries(map)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([tag, count]) => ({ tag, count }))
})

const authorCounts = computed(() => {
  const map: Record<string, number> = {}
  for (const item of items.value) {
    const a = item.author || 'unknown'
    map[a] = (map[a] || 0) + 1
  }
  return Object.entries(map)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([author, count]) => ({ author, count }))
})

const suggestTags = computed(() => tagCounts.value.slice(0, 6).map((t) => t.tag))

const totalDownloads = computed(() => items.value.reduce((s, i) => s + (i.downloads || 0), 0))

const hasFilters = computed(
  () => activeTags.value.length > 0 || !!activeAuthor.value || !!searchQuery.value.trim(),
)

const filteredItems = computed(() => {
  let list = items.value.slice()
  if (activeTags.value.length) {
    list = list.filter((item) => activeTags.value.every((t) => (item.tags || []).includes(t)))
  }
  if (activeAuthor.value) {
    list = list.filter((item) => item.author === activeAuthor.value)
  }
  if (sort.value === 'hot') list.sort((a, b) => (b.downloads || 0) - (a.downloads || 0))
  else if (sort.value === 'name') list.sort((a, b) => a.name.localeCompare(b.name))
  else list.sort((a, b) => (b.published_at || '').localeCompare(a.published_at || ''))
  return list
})

function toggleTag(tag: string) {
  const i = activeTags.value.indexOf(tag)
  if (i >= 0) activeTags.value = activeTags.value.filter((t) => t !== tag)
  else activeTags.value = [...activeTags.value, tag]
}

function toggleAuthor(author: string) {
  activeAuthor.value = activeAuthor.value === author ? '' : author
}

function clearFilters() {
  activeTags.value = []
  activeAuthor.value = ''
  searchQuery.value = ''
  mkt.browse('')
}

function setView(mode: ViewMode) {
  view.value = mode
}

function setSort(key: SortKey) {
  sort.value = key
}

function applySuggest(tag: string) {
  toggleTag(tag)
}

onMounted(() => {
  mkt.browse()
  refreshPluginList()
  if (auth.isLoggedIn) loadTeams()
  // 从独立菜单（我的发布）进入时，初始 Tab 为 mine，需主动加载
  if (activeTab.value === 'mine') { loadMyPlugins(); loadFavorites(); loadLiked() }
})
</script>

<template>
  <div class="mkt-page">
    <!-- Tab 栏 -->
    <nav class="mkt-tabs" role="tablist">
      <button
        type="button"
        class="mkt-tab"
        :class="{ active: activeTab === 'market' }"
        role="tab"
        :aria-selected="activeTab === 'market'"
        @click="activeTab = 'market'"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        插件市场
        <span class="mkt-tab-badge">{{ items.length }}</span>
      </button>
      <button
        v-if="auth.isLoggedIn"
        type="button"
        class="mkt-tab"
        :class="{ active: activeTab === 'mine' }"
        role="tab"
        :aria-selected="activeTab === 'mine'"
        @click="activeTab = 'mine'"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        我的
        <span class="mkt-tab-badge">{{ myPlugins.length + myFavorites.length + myLiked.length }}</span>
      </button>
      <button
        type="button"
        class="mkt-tab"
        :class="{ active: activeTab === 'team' }"
        role="tab"
        :aria-selected="activeTab === 'team'"
        @click="activeTab = 'team'"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        团队空间
        <span class="mkt-tab-badge">{{ teamSpaces.length }}</span>
      </button>
    </nav>

    <!-- === 插件市场 === -->
    <div v-show="activeTab === 'market'">
    <!-- Hero：搜索优先 -->
    <header class="mkt-hero">
      <div class="mkt-search">
        <span class="mkt-search-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
        </span>
        <input
          v-model="searchQuery"
          type="search"
          placeholder="搜索插件名称、描述、标签…"
          autocomplete="off"
          aria-label="搜索插件"
          @input="onSearch"
          @keyup.enter="mkt.browse()"
        />
        <button type="button" class="mkt-search-go" :disabled="loading" @click="mkt.browse()">
          {{ loading ? '…' : '搜索' }}
        </button>
      </div>

      <div v-if="suggestTags.length" class="mkt-suggests">
        <span>试试</span>
        <button
          v-for="tag in suggestTags"
          :key="tag"
          type="button"
          class="mkt-chip"
          :class="{ on: activeTags.includes(tag) }"
          @click="applySuggest(tag)"
        >{{ tag }}</button>
      </div>
    </header>

    <!-- 热门推荐：本地未安装的精选插件 -->
    <section v-if="featuredPlugins.length" class="mkt-featured">
      <header class="mkt-featured-head">
        <h2><span class="star" aria-hidden="true">★</span> 热门推荐</h2>
        <span class="mkt-featured-count">{{ featuredPlugins.length }} 个</span>
      </header>
      <div class="mkt-featured-grid">
        <article v-for="p in featuredPlugins" :key="p.id" class="mkt-featured-card">
          <div class="mkt-featured-top">
            <div class="mkt-featured-avatar" aria-hidden="true">{{ initials(p.name) }}</div>
            <span class="mkt-featured-tag">推荐</span>
          </div>
          <div class="mkt-featured-body">
            <h3>{{ p.name }}<span class="mkt-ver">v{{ p.version }}</span></h3>
            <p class="mkt-featured-desc" :title="p.description">{{ p.description || '暂无描述' }}</p>
          </div>
          <div class="mkt-featured-meta">
            <span class="mkt-chip brand">⬇ {{ p.downloads || 0 }}</span>
            <span class="mkt-chip">♥ {{ p.likes || 0 }}</span>
            <span class="mkt-chip">by {{ p.author }}</span>
          </div>
          <div class="mkt-featured-foot">
            <button
              type="button"
              class="mkt-btn mkt-btn-primary"
              @click="mkt.install(p.id)"
            >
              {{ mkt.installing === p.id ? '安装中…' : '安装' }}
            </button>
            <div class="mkt-featured-ops">
              <a class="mkt-btn mkt-btn-ghost" @click="downloadPlugin(p)" href="javascript:void(0)">下载</a>
            </div>
          </div>
        </article>
      </div>
    </section>

    <div class="mkt-workspace">
      <div class="mkt-main">
        <div class="mkt-toolbar">
          <h2>全部插件<em>· {{ filteredItems.length }} 个</em>
            <span v-if="isMock" class="mock-flag" title="当前为内置示例数据，发布本地插件后将自动替换">示例</span>
          </h2>
          <div class="mkt-toolbar-right">
            <div class="mkt-view-toggle" role="group" aria-label="视图切换">
              <button
                type="button"
                :class="{ on: view === 'grid' }"
                title="卡片视图"
                :aria-pressed="view === 'grid'"
                @click="setView('grid')"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
              </button>
              <button
                type="button"
                :class="{ on: view === 'list' }"
                title="列表视图"
                :aria-pressed="view === 'list'"
                @click="setView('list')"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
              </button>
            </div>
            <div class="mkt-sort" role="group" aria-label="排序">
              <button type="button" :class="{ on: sort === 'new' }" @click="setSort('new')">最新</button>
              <button type="button" :class="{ on: sort === 'hot' }" @click="setSort('hot')">最热</button>
              <button type="button" :class="{ on: sort === 'name' }" @click="setSort('name')">名称</button>
            </div>
          </div>
        </div>

        <div v-if="loading && !items.length" class="mkt-empty">
          <div class="mkt-spinner" aria-hidden="true" />
          <h3>加载中…</h3>
        </div>

        <div v-else-if="!items.length" class="mkt-empty">
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
          <h3>市场暂无插件</h3>
          <p>在「插件管理」页点击「分享到市场」即可发布。</p>
        </div>

        <div v-else-if="!filteredItems.length" class="mkt-empty">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
          <h3>没有匹配的插件</h3>
          <p>换个关键词，或清除右侧筛选后再试。</p>
          <button type="button" class="mkt-btn mkt-btn-primary" @click="clearFilters">清除筛选</button>
        </div>

        <div
          v-else
          class="mkt-grid"
          :class="{ 'view-list': view === 'list' }"
          aria-live="polite"
        >
          <article v-for="item in filteredItems" :key="item.id" class="mkt-card">
            <button
              v-if="auth.isLoggedIn"
              type="button"
              class="mkt-fav-star"
              :class="{ on: item.favorited }"
              :title="item.favorited ? '取消收藏' : '收藏'"
              @click="toggleFavorite(item)"
            >
              <svg viewBox="0 0 24 24" :fill="item.favorited ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            </button>
            <div class="mkt-card-top">
              <div class="mkt-avatar" aria-hidden="true">{{ initials(item.name) }}</div>
              <div class="min-w-0">
                <h3>
                  {{ item.name }}
                  <span class="mkt-ver">v{{ item.version }}</span>
                </h3>
                <p class="mkt-desc">{{ item.description || '无描述' }}</p>
              </div>
            </div>

            <div v-if="item.tags?.length" class="mkt-tags">
              <span v-for="tag in item.tags" :key="tag" class="mkt-tag">{{ tag }}</span>
            </div>

            <div class="mkt-meta">
              <span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                {{ item.author || '-' }}
              </span>
              <span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                {{ item.downloads || 0 }}
              </span>
              <span>{{ formatSize(item.size) }}</span>
              <span>{{ formatDate(item.published_at) }}</span>
            </div>

            <div class="mkt-actions">
              <button
                type="button"
                class="mkt-btn"
                :class="item.liked ? 'mkt-btn-liked' : 'mkt-btn-ghost'"
                :title="item.liked ? '取消点赞' : '点赞'"
                @click="toggleLike(item)"
              >
                <svg viewBox="0 0 24 24" :fill="item.liked ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
                {{ item.likes || 0 }}
              </button>
              <button
                type="button"
                class="mkt-btn mkt-btn-primary"
                :disabled="!!installing || isMock"
                :title="isMock ? '示例数据，无法真实安装' : ''"
                @click="mkt.install(item.id)"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M8 11l4 4 4-4M5 21h14"/></svg>
                {{ installing === item.id ? '安装中…' : '安装' }}
              </button>
              <a
                v-if="!isMock"
                class="mkt-btn mkt-btn-ghost"
                @click="downloadPlugin(item)"
                href="javascript:void(0)"
              >下载</a>
              <button
                v-else
                type="button"
                class="mkt-btn mkt-btn-ghost"
                disabled
                title="示例数据，无法下载"
              >下载</button>
            </div>
          </article>
        </div>
      </div>

      <!-- 右侧筛选 -->
      <aside class="mkt-filter" aria-label="市场筛选">
        <div class="mkt-filter-h">
          <strong>市场筛选</strong>
          <button type="button" class="mkt-filter-clear" :disabled="!hasFilters" @click="clearFilters">清除</button>
        </div>

        <div class="mkt-filter-section">
          <div class="mkt-filter-label">标签</div>
          <div v-if="!tagCounts.length" class="mkt-filter-empty">暂无标签</div>
          <div v-else class="mkt-filter-tags">
            <button
              v-for="{ tag, count } in tagCounts"
              :key="tag"
              type="button"
              class="mkt-filter-tag"
              :class="{ on: activeTags.includes(tag) }"
              :aria-pressed="activeTags.includes(tag)"
              @click="toggleTag(tag)"
            >
              <span class="box" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg>
              </span>
              {{ tag }}
              <span class="n">{{ count }}</span>
            </button>
          </div>
        </div>

        <div class="mkt-filter-section">
          <div class="mkt-filter-label">作者</div>
          <div v-if="!authorCounts.length" class="mkt-filter-empty">暂无作者</div>
          <div v-else class="mkt-filter-authors">
            <button
              v-for="{ author, count } in authorCounts"
              :key="author"
              type="button"
              class="mkt-filter-author"
              :class="{ on: activeAuthor === author }"
              :aria-pressed="activeAuthor === author"
              @click="toggleAuthor(author)"
            >
              {{ author }}
              <span class="n">{{ count }}</span>
            </button>
          </div>
        </div>

        <div class="mkt-filter-hint">
          可多选标签，与顶部搜索、建议标签联动。没有想要的包？在「插件管理」页分享到市场。
        </div>
      </aside>
    </div>
    </div><!-- /插件市场 -->

    <!-- === 我的（发布 + 收藏）=== -->
    <div v-show="activeTab === 'mine'">
      <div v-if="myLoading" class="mkt-empty">加载中...</div>
      <template v-else>
        <!-- 我的发布 -->
        <div v-if="myPlugins.length" class="mkt-mine-section">
          <h3 class="mkt-mine-title">我的发布 <span>{{ myPlugins.length }}</span></h3>
          <div class="mkt-grid">
            <div v-for="p in myPlugins" :key="p.id" class="mkt-card">
              <div class="mkt-card-head">
                <span class="mkt-card-name">{{ p.name }}</span>
                <span class="mkt-card-ver">v{{ p.version }}</span>
              </div>
              <p class="mkt-card-desc">{{ p.description || '暂无描述' }}</p>
              <div class="mkt-card-meta">
                <span>⬇ {{ p.downloads || 0 }}</span>
                <span>❤ {{ p.likes || 0 }}</span>
                <span v-if="p.scope === 'team'" style="color:var(--green)">团队</span>
                <span v-else style="color:var(--brand-500)">公共</span>
              </div>
              <div class="mkt-card-actions">
                <button class="mkt-btn mkt-btn-ghost" :class="{ 'mkt-btn-liked': p.liked }" @click="toggleLike(p)">
                  <svg viewBox="0 0 24 24" :fill="p.liked ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" style="width:14px;height:14px" aria-hidden="true"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
                  {{ p.likes || 0 }}
                </button>
                <a class="mkt-btn mkt-btn-ghost" @click="downloadPlugin(p)" href="javascript:void(0)">下载</a>
                <button class="mkt-btn mkt-btn-ghost" :disabled="mkt.installing === p.id" @click="mkt.install(p.id)">
                  {{ mkt.installing === p.id ? '安装中…' : '安装' }}
                </button>
                <button class="mkt-btn-danger" @click="deletePlugin(p.id)">删除</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 我的收藏 -->
        <div v-if="myFavorites.length" class="mkt-mine-section">
          <h3 class="mkt-mine-title">我的收藏 <span>{{ myFavorites.length }}</span></h3>
          <div class="mkt-grid">
            <div v-for="p in myFavorites" :key="p.id" class="mkt-card">
              <div class="mkt-card-head">
                <span class="mkt-card-name">{{ p.name }}</span>
                <span class="mkt-card-ver">v{{ p.version }}</span>
              </div>
              <p class="mkt-card-desc">{{ p.description || '暂无描述' }}</p>
              <div class="mkt-card-meta">
                <span>⬇ {{ p.downloads || 0 }}</span>
                <span>❤ {{ p.likes || 0 }}</span>
                <span>by {{ p.author }}</span>
              </div>
              <div class="mkt-card-actions">
                <button class="mkt-btn mkt-btn-ghost" :class="{ 'mkt-btn-liked': p.liked }" @click="toggleLike(p)">
                  <svg viewBox="0 0 24 24" :fill="p.liked ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" style="width:14px;height:14px" aria-hidden="true"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
                  {{ p.likes || 0 }}
                </button>
                <button class="mkt-btn mkt-btn-ghost" :class="{ 'mkt-btn-liked': p.favorited }" @click="toggleFavorite(p); myFavorites = myFavorites.filter(x => x.id !== p.id)">
                  <svg viewBox="0 0 24 24" :fill="p.favorited ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" style="width:14px;height:14px" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                </button>
                <a class="mkt-btn mkt-btn-ghost" @click="downloadPlugin(p)" href="javascript:void(0)">下载</a>
              </div>
            </div>
          </div>
        </div>

        <!-- 我的点赞 -->
        <div v-if="myLiked.length" class="mkt-mine-section">
          <h3 class="mkt-mine-title">我的点赞 <span>{{ myLiked.length }}</span></h3>
          <div class="mkt-grid">
            <div v-for="p in myLiked" :key="p.id" class="mkt-card">
              <div class="mkt-card-head">
                <span class="mkt-card-name">{{ p.name }}</span>
                <span class="mkt-card-ver">v{{ p.version }}</span>
              </div>
              <p class="mkt-card-desc">{{ p.description || '暂无描述' }}</p>
              <div class="mkt-card-meta">
                <span>⬇ {{ p.downloads || 0 }}</span>
                <span>❤ {{ p.likes || 0 }}</span>
                <span>by {{ p.author }}</span>
              </div>
              <div class="mkt-card-actions">
                <button class="mkt-btn mkt-btn-ghost" :class="{ 'mkt-btn-liked': p.liked }" @click="toggleLike(p); myLiked = myLiked.filter(x => x.id !== p.id)">
                  <svg viewBox="0 0 24 24" :fill="p.liked ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" style="width:14px;height:14px" aria-hidden="true"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
                  {{ p.likes || 0 }}
                </button>
                <button class="mkt-btn mkt-btn-ghost" :class="{ 'mkt-btn-liked': p.favorited }" @click="toggleFavorite(p)">
                  <svg viewBox="0 0 24 24" :fill="p.favorited ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" style="width:14px;height:14px" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                </button>
                <a class="mkt-btn mkt-btn-ghost" @click="downloadPlugin(p)" href="javascript:void(0)">下载</a>
              </div>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="!myPlugins.length && !myFavorites.length && !myLiked.length" class="mkt-empty">
          <p>你还没有发布、收藏或点赞任何插件</p>
          <p style="font-size:12px;color:var(--text-tertiary)">在插件市场点击星标收藏，或在「插件构建」中创建插件后发布</p>
        </div>
      </template>
    </div>

    <!-- === 团队空间 === -->
    <div v-show="activeTab === 'team'">
      <!-- 空间列表视图 -->
      <div v-if="!selectedSpace">
        <div class="team-toolbar">
          <div class="mkt-search" style="max-width: 480px">
            <span class="mkt-search-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
            </span>
            <input
              v-model="teamSearchQuery"
              type="search"
              placeholder="搜索团队空间…"
              style="padding-left: 44px; height: 40px; border-radius: 12px; border: 1.5px solid var(--color-ink-300, #c9cdd4); background: var(--bg-elevated); width: 100%; font-size: 13px;"
            />
          </div>
          <button type="button" class="mkt-btn mkt-btn-primary" @click="showCreateSpace">
            <svg viewBox="0 0 24 24" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            创建团队空间
          </button>
        </div>

        <div v-if="teamsLoading" class="mkt-empty">加载中...</div>
        <div v-else-if="!filteredTeamSpaces.length" class="mkt-empty">
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          <h3>暂无团队空间</h3>
          <p>创建团队空间，邀请成员协作管理内部插件。</p>
          <button type="button" class="mkt-btn mkt-btn-primary" @click="showCreateSpace">创建团队空间</button>
        </div>

        <div v-else class="team-grid">
          <article
            v-for="space in filteredTeamSpaces"
            :key="space.id"
            class="team-card"
            @click="openSpaceDetail(space.id)"
          >
            <span class="team-role" :class="space.role === 'owner' ? 'role-owner' : 'role-member'">
              {{ space.role === 'owner' ? 'Owner' : 'Member' }}
            </span>
            <div class="team-card-head">
              <svg class="team-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              <h3>{{ space.name }}</h3>
            </div>
            <p class="team-card-desc">{{ space.description || '暂无描述' }}</p>
            <div class="team-card-meta">
              <span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg> {{ space.member_count }} 成员</span>
            </div>
          </article>
        </div>
      </div>

      <!-- 空间详情视图 -->
      <div v-else>
        <button type="button" class="team-back" @click="backToSpaceList">
          <svg viewBox="0 0 24 24" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>
          返回空间列表
        </button>

        <div class="team-detail-header">
          <div class="team-detail-info">
            <div class="team-detail-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            </div>
            <div>
              <div class="team-detail-name">{{ selectedSpace.name }}</div>
              <div class="team-detail-meta">{{ teamPlugins.length }} 个插件 · {{ teamMembers.length }} 名成员</div>
            </div>
          </div>
          <div class="team-detail-actions">
            <button v-if="selectedSpace.role === 'owner'" type="button" class="mkt-btn mkt-btn-ghost" @click="showInvite">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>
              邀请成员
            </button>
          </div>
        </div>

        <!-- 成员管理 -->
        <div class="team-members-panel">
          <h3>成员管理</h3>
          <div v-if="membersLoading" class="mkt-empty">加载中...</div>
          <div v-else class="team-members-list">
            <div v-for="m in teamMembers" :key="m.id" class="team-member-row">
              <div class="team-member-info">
                <span class="team-avatar team-avatar-lg">{{ m.username.charAt(0).toUpperCase() }}</span>
                <div>
                  <div class="team-member-name">{{ m.username }}</div>
                  <div class="team-member-email">{{ m.email || '无邮箱' }}</div>
                </div>
              </div>
              <span class="team-role" :class="m.role === 'owner' ? 'role-owner' : 'role-member'">
                {{ m.role === 'owner' ? 'Owner' : 'Member' }}
              </span>
              <button
                v-if="selectedSpace.role === 'owner' && m.role !== 'owner'"
                class="mkt-btn-danger"
                style="font-size:12px;padding:4px 10px"
                @click="removeMember(m.username)"
              >移除</button>
            </div>
          </div>
        </div>

        <!-- 空间内插件 -->
        <div style="margin-top:16px">
          <h3 style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--text-secondary)">团队插件</h3>
          <div v-if="teamPluginsLoading" class="mkt-empty">加载中...</div>
          <div v-else-if="teamPlugins.length === 0" class="mkt-empty">
            <p>暂无插件</p>
            <p style="font-size:12px;color:var(--text-tertiary)">在「插件构建」中发布插件时选择此团队空间</p>
          </div>
          <div v-else class="mkt-grid">
            <div v-for="p in teamPlugins" :key="p.id" class="mkt-card">
              <div class="mkt-card-head">
                <span class="mkt-card-name">{{ p.name }}</span>
                <span class="mkt-card-ver">v{{ p.version }}</span>
              </div>
              <p class="mkt-card-desc">{{ p.description || '暂无描述' }}</p>
              <div class="mkt-card-meta">
                <span>⬇ {{ p.downloads || 0 }}</span>
                <span>❤ {{ p.likes || 0 }}</span>
                <span style="color:var(--green)">团队</span>
              </div>
              <div class="mkt-card-actions">
                <a class="mkt-btn mkt-btn-ghost" @click="downloadPlugin(p)" href="javascript:void(0)">下载</a>
                <button class="mkt-btn mkt-btn-ghost" :disabled="mkt.installing === p.id" @click="mkt.install(p.id)">
                  {{ mkt.installing === p.id ? '安装中…' : '安装' }}
                </button>
                <button v-if="selectedSpace.role === 'owner' || p.author_id === auth.user?.id" class="mkt-btn-danger" @click="deleteTeamPlugin(p.id)">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div><!-- /团队空间 -->

    <!-- === 发布插件弹窗 === -->
    <Teleport to="body">
      <Transition name="upgrade-modal">
        <div v-if="publishDialogOpen" class="upgrade-mask" @click.self="publishDialogOpen = false">
          <div class="upgrade-panel" role="dialog" aria-modal="true" style="max-width: 480px">
            <header class="upgrade-head">
              <h3>发布插件</h3>
              <button type="button" class="upgrade-close" aria-label="关闭" @click="publishDialogOpen = false">
                <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </header>
            <div class="upgrade-body">
              <label style="display:block;font-size:13px;font-weight:600;margin-bottom:10px">发布到</label>
              <div style="display:flex;gap:10px;margin-bottom:16px">
                <label style="flex:1;display:flex;align-items:center;gap:8px;padding:12px;border:1px solid var(--color-ink-300,#c9cdd4);border-radius:8px;cursor:pointer" :style="{ borderColor: publishScope === 'public' ? 'var(--brand-500,#6366f1)' : '' }">
                  <input type="radio" v-model="publishScope" value="public" style="accent-color:var(--brand-500,#6366f1)" />
                  <div>
                    <div style="font-size:14px;font-weight:600">公共市场</div>
                    <div style="font-size:12px;color:var(--text-tertiary)">所有人可见可下载</div>
                  </div>
                </label>
                <label v-if="auth.isLoggedIn && teamSpaces.length > 0" style="flex:1;display:flex;align-items:center;gap:8px;padding:12px;border:1px solid var(--color-ink-300,#c9cdd4);border-radius:8px;cursor:pointer" :style="{ borderColor: publishScope === 'team' ? 'var(--brand-500,#6366f1)' : '' }">
                  <input type="radio" v-model="publishScope" value="team" style="accent-color:var(--brand-500,#6366f1)" />
                  <div>
                    <div style="font-size:14px;font-weight:600">团队空间</div>
                    <div style="font-size:12px;color:var(--text-tertiary)">仅团队成员可见</div>
                  </div>
                </label>
              </div>
              <!-- 选择团队 -->
              <div v-if="publishScope === 'team' && teamSpaces.length > 0" style="margin-bottom:16px">
                <label style="display:block;font-size:13px;font-weight:600;margin-bottom:6px">选择团队</label>
                <select v-model="publishTeamId" style="width:100%;padding:10px 12px;border:1px solid var(--color-ink-300,#c9cdd4);border-radius:8px;font-size:14px;background:var(--bg-base,#f7f8fa)">
                  <option :value="null" disabled>请选择团队空间</option>
                  <option v-for="t in teamSpaces" :key="t.id" :value="t.id">{{ t.name }}（{{ t.role === 'owner' ? 'Owner' : 'Member' }}）</option>
                </select>
              </div>
              <p v-if="publishScope === 'team' && teamSpaces.length === 0" style="font-size:13px;color:var(--text-tertiary)">你还没有加入任何团队，请先创建团队空间</p>
            </div>
            <footer class="upgrade-foot">
              <button type="button" class="mkt-btn mkt-btn-ghost" @click="publishDialogOpen = false">取消</button>
              <button type="button" class="mkt-btn mkt-btn-primary" :disabled="publishScope === 'team' && !publishTeamId" @click="doPublish">发布</button>
            </footer>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- === 创建团队空间弹窗 === -->
    <Teleport to="body">
      <Transition name="upgrade-modal">
        <div v-if="createSpaceOpen" class="upgrade-mask" @click.self="createSpaceOpen = false">
          <div class="upgrade-panel" role="dialog" aria-modal="true" style="max-width: 480px">
            <header class="upgrade-head">
              <h3>创建团队空间</h3>
              <button type="button" class="upgrade-close" aria-label="关闭" @click="createSpaceOpen = false">
                <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </header>
            <div class="upgrade-body">
              <div style="margin-bottom: 16px">
                <label style="display:block;font-size:13px;font-weight:600;margin-bottom:6px">空间名称</label>
                <input v-model="newSpaceName" type="text" placeholder="如：后端架构组" style="width:100%;padding:10px 12px;border:1px solid var(--color-ink-300,#c9cdd4);border-radius:8px;font-size:14px;background:var(--bg-base,#f7f8fa)" />
              </div>
              <div style="margin-bottom: 16px">
                <label style="display:block;font-size:13px;font-weight:600;margin-bottom:6px">描述</label>
                <input v-model="newSpaceDesc" type="text" placeholder="简要描述空间用途" style="width:100%;padding:10px 12px;border:1px solid var(--color-ink-300,#c9cdd4);border-radius:8px;font-size:14px;background:var(--bg-base,#f7f8fa)" />
              </div>
              <p style="font-size:12px;color:var(--color-ink-500,#86909c)">创建后你将自动成为团队 Owner，可在空间详情中邀请成员</p>
            </div>
            <footer class="upgrade-foot">
              <button type="button" class="mkt-btn mkt-btn-ghost" @click="createSpaceOpen = false">取消</button>
              <button type="button" class="mkt-btn mkt-btn-primary" @click="createSpace">创建空间</button>
            </footer>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- === 邀请成员弹窗 === -->
    <Teleport to="body">
      <Transition name="upgrade-modal">
        <div v-if="inviteOpen" class="upgrade-mask" @click.self="inviteOpen = false">
          <div class="upgrade-panel" role="dialog" aria-modal="true" style="max-width: 480px">
            <header class="upgrade-head">
              <h3>邀请成员加入「{{ selectedSpace?.name }}」</h3>
              <button type="button" class="upgrade-close" aria-label="关闭" @click="inviteOpen = false">
                <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </header>
            <div class="upgrade-body">
              <label style="display:block;font-size:13px;font-weight:600;margin-bottom:6px">用户名</label>
              <input
                v-model="inviteInput"
                type="text"
                placeholder="输入已注册的用户名"
                style="width:100%;padding:10px 12px;border:1px solid var(--color-ink-300,#c9cdd4);border-radius:8px;font-size:14px;background:var(--bg-base,#f7f8fa)"
                @keydown.enter="sendInvite"
              />
              <div v-if="inviteError" style="margin-top:8px;font-size:12px;color:var(--red,#f53f3f);background:rgba(245,63,63,0.08);padding:8px 12px;border-radius:6px">{{ inviteError }}</div>
              <p style="margin-top:8px;font-size:12px;color:var(--color-ink-500,#86909c)">用户需先注册才能被邀请</p>
            </div>
            <footer class="upgrade-foot">
              <button type="button" class="mkt-btn mkt-btn-ghost" @click="inviteOpen = false">取消</button>
              <button type="button" class="mkt-btn mkt-btn-primary" @click="sendInvite">邀请</button>
            </footer>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<!-- 弹窗样式（非 scoped，因为 Header.vue 的 scoped 样式不跨组件生效） -->
<style>
.upgrade-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(2px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.upgrade-panel {
  width: 100%;
  max-width: 560px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-elevated, #fff);
  border: 1px solid var(--border-base, #e5e7eb);
  border-radius: 14px;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.24);
  overflow: hidden;
}
.upgrade-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-base, #e5e7eb);
}
.upgrade-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #1f2329);
}
.upgrade-close {
  border: 0;
  background: transparent;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  color: var(--text-tertiary, #86909c);
  display: inline-flex;
}
.upgrade-close:hover {
  background: var(--bg-sunken, #f7f8fa);
  color: var(--text-primary, #1f2329);
}
.upgrade-close svg {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}
.upgrade-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
  font-size: 13px;
  color: var(--text-secondary, #4e5969);
  line-height: 1.6;
}
.upgrade-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--border-base, #e5e7eb);
  background: var(--bg-sunken, #f7f8fa);
}
.upgrade-modal-enter-active,
.upgrade-modal-leave-active {
  transition: opacity 0.2s ease;
}
.upgrade-modal-enter-active .upgrade-panel,
.upgrade-modal-leave-active .upgrade-panel {
  transition: transform 0.2s ease;
}
.upgrade-modal-enter-from,
.upgrade-modal-leave-to {
  opacity: 0;
}
.upgrade-modal-enter-from .upgrade-panel,
.upgrade-modal-leave-to .upgrade-panel {
  transform: scale(0.96) translateY(-8px);
}
</style>

<style scoped>
.mkt-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* === Tab 栏 === */
.mkt-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--color-ink-200, #e5e6eb);
  background: var(--bg-elevated, #fff);
  border-radius: 12px 12px 0 0;
  overflow: hidden;
}
.mkt-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ink-500, #86909c);
  cursor: pointer;
  border: 0;
  background: transparent;
  border-bottom: 2px solid transparent;
  transition: color .15s, border-color .15s;
}
.mkt-tab:hover { color: var(--color-ink-900, #1f2329); }
.mkt-tab.active {
  color: var(--color-brand-500, #165dff);
  border-bottom-color: var(--color-brand-500, #165dff);
}
.mkt-tab svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; }
.mkt-tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 700;
  background: var(--color-ink-200, #e5e6eb);
  color: var(--color-ink-500, #86909c);
}
.mkt-tab.active .mkt-tab-badge {
  background: var(--color-brand-500, #165dff);
  color: #fff;
}

/* === 团队空间 === */
.team-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.team-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}
.team-card {
  position: relative;
  background: var(--bg-elevated, #fff);
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 14px;
  padding: 20px;
  cursor: pointer;
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
  transition: border-color .2s, transform .2s, box-shadow .2s;
}
.team-card:hover {
  border-color: var(--color-brand-500, #165dff);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(22, 93, 255, .08);
}
.team-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.team-card-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-ink-900, #1f2329);
}
.team-icon {
  width: 20px;
  height: 20px;
  stroke: var(--color-orange, #ff7d00);
  fill: none;
  stroke-width: 2;
  flex-shrink: 0;
}
.team-card-desc {
  font-size: 13px;
  color: var(--color-ink-700, #4e5969);
  margin-bottom: 12px;
  line-height: 1.5;
}
.team-card-meta {
  font-size: 12px;
  color: var(--color-ink-500, #86909c);
  display: flex;
  gap: 12px;
}
.team-card-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}
.team-card-meta svg {
  width: 12px;
  height: 12px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}
.team-card-members {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
}
.team-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  border: 2px solid var(--bg-elevated, #fff);
  background: var(--color-brand-500, #165dff);
}
.team-avatar:nth-child(2) { background: #722ed1; }
.team-avatar:nth-child(3) { background: #00b42a; }
.team-avatar.team-avatar-lg {
  width: 36px;
  height: 36px;
  font-size: 13px;
}
.team-more {
  font-size: 12px;
  color: var(--color-ink-500, #86909c);
  margin-left: 4px;
}
.team-role {
  position: absolute;
  top: 16px;
  right: 16px;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}
.role-owner {
  background: var(--color-brand-50, #eef4ff);
  color: var(--color-brand-600, #0e42d2);
}
.role-member {
  background: var(--color-ink-100, #f7f8fa);
  color: var(--color-ink-500, #86909c);
}

/* 团队空间详情 */
.team-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  color: var(--color-brand-500, #165dff);
  font-size: 13px;
  font-weight: 600;
  border: 0;
  background: transparent;
  margin-bottom: 16px;
  padding: 0;
}
.team-back svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 2; }
.team-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding: 20px;
  background: var(--bg-elevated, #fff);
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 14px;
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
}
.team-detail-info {
  display: flex;
  align-items: center;
  gap: 16px;
}
.team-detail-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 125, 0, .1);
}
.team-detail-icon svg {
  width: 28px;
  height: 28px;
  stroke: var(--color-orange, #ff7d00);
  fill: none;
  stroke-width: 2;
}
.team-detail-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-ink-900, #1f2329);
}
.team-detail-meta {
  font-size: 13px;
  color: var(--color-ink-500, #86909c);
  margin-top: 4px;
}
.team-detail-actions {
  display: flex;
  gap: 8px;
}

/* 成员管理 */
.team-members-panel {
  background: var(--bg-elevated, #fff);
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 14px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
}
.team-members-panel h3 {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--color-ink-900, #1f2329);
}
.team-members-list {
  display: flex;
  flex-direction: column;
}
.team-member-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-ink-200, #e5e6eb);
}
.team-member-row:last-child { border-bottom: none; }
.team-member-info {
  display: flex;
  align-items: center;
  gap: 10px;
}
.team-member-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ink-900, #1f2329);
}
.team-member-email {
  font-size: 12px;
  color: var(--color-ink-500, #86909c);
}

/* 热门推荐 */
.mkt-featured {
  background: var(--bg-elevated, #fff);
  border: 1px solid #e5e6eb;
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
}
.mkt-featured-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 14px; }
.mkt-featured-head h2 {
  margin: 0; font-size: 15px; font-weight: 700; color: #1f2329;
  display: inline-flex; align-items: center; gap: 6px;
}
.mkt-featured-head .star { color: #ff7d00; font-size: 15px; }
.mkt-featured-count { font-size: 12px; color: #86909c; font-weight: 500; font-variant-numeric: tabular-nums; }
.mkt-featured-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.mkt-featured-card {
  display: flex; flex-direction: column; gap: 10px; padding: 14px; border-radius: 14px;
  border: 1px solid #d9e6ff; background: linear-gradient(180deg, #eef4ff 0%, #fff 32%) #fff;
  transition: border-color .18s ease, box-shadow .18s ease;
}
.mkt-featured-card:hover { border-color: #165dff; box-shadow: 0 4px 16px rgba(22, 93, 255, .08); }
.mkt-featured-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.mkt-featured-avatar {
  width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center;
  background: #165dff; color: #fff; font-weight: 750; font-size: 13px;
}
.mkt-featured-tag {
  font-size: 10.5px; font-weight: 700; padding: 3px 8px; border-radius: 999px;
  background: #165dff; color: #fff; letter-spacing: .02em;
}
.mkt-featured-body h3 { margin: 0; font-size: 14px; font-weight: 700; color: #1f2329; }
.mkt-ver { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; color: #86909c; margin-left: 6px; font-weight: 500; }
.mkt-featured-desc {
  margin: 4px 0 0; font-size: 12.5px; color: #86909c; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; min-height: 2.9em;
}
.mkt-featured-meta { display: flex; flex-wrap: wrap; gap: 6px; }
.mkt-chip { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 999px; background: #f7f8fa; color: #4e5969; }
.mkt-chip.brand { background: #eef4ff; color: #165dff; }
.mkt-featured-foot {
  margin-top: auto; display: flex; justify-content: space-between; align-items: center; gap: 6px;
  padding-top: 10px; border-top: 1px solid #f7f8fa; flex-wrap: wrap;
}
.mkt-featured-ops { display: flex; gap: 2px; flex-wrap: wrap; align-items: center; }
.mkt-btn {
  height: 28px; padding: 0 10px; border-radius: 7px; font-size: 11px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; gap: 4px;
  white-space: nowrap; border: 1px solid transparent; cursor: pointer; transition: background .18s ease;
}
.mkt-btn:disabled { opacity: .45; cursor: not-allowed; }
.mkt-btn-primary { background: #165dff; color: #fff; }
.mkt-btn-primary:hover:not(:disabled) { background: #0e42d2; }
.mkt-btn-ghost { background: transparent; color: #4e5969; }
.mkt-btn-ghost:hover:not(:disabled) { background: #f7f8fa; color: #1f2329; }
@media (max-width: 1100px) { .mkt-featured-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 820px) { .mkt-featured-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 540px) { .mkt-featured-grid { grid-template-columns: 1fr; } }

.mkt-hero {
  text-align: center;
  padding: 4px 4px;
}
.mkt-search {
  position: relative;
  max-width: 640px;
  margin: 0 auto;
}
.mkt-search input {
  width: 100%;
  height: 48px;
  padding: 0 108px 0 44px;
  border: 1.5px solid var(--color-ink-300, #c9cdd4);
  border-radius: 14px;
  background: var(--bg-elevated);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-ink-900, #1f2329);
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
  transition: border-color .2s ease, box-shadow .2s ease;
}
.mkt-search input::placeholder {
  color: var(--color-ink-500, #86909c);
  font-weight: 400;
}
.mkt-search input:focus {
  outline: none;
  border-color: var(--color-brand-500, #165dff);
  box-shadow: 0 0 0 3px rgba(22, 93, 255, .15), var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
}
.mkt-search-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: var(--color-ink-500, #86909c);
  pointer-events: none;
}
.mkt-search-icon svg {
  width: 100%;
  height: 100%;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}
.mkt-search-go {
  position: absolute;
  right: 7px;
  top: 50%;
  transform: translateY(-50%);
  height: 34px;
  padding: 0 14px;
  border: 0;
  border-radius: 10px;
  background: var(--color-brand-500, #165dff);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background .2s ease;
}
.mkt-search-go:hover:not(:disabled) { background: var(--color-brand-600, #0e42d2); }
.mkt-search-go:disabled { opacity: .55; cursor: not-allowed; }

.mkt-suggests {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
}
.mkt-suggests > span {
  font-size: 12px;
  color: var(--color-ink-500, #86909c);
  align-self: center;
}
.mkt-chip {
  border: 1px solid var(--color-ink-200, #e5e6eb);
  background: var(--bg-elevated);
  color: var(--color-ink-700, #4e5969);
  font-size: 12px;
  font-weight: 500;
  padding: 6px 11px;
  border-radius: 999px;
  cursor: pointer;
  transition: border-color .2s, color .2s, background .2s;
}
.mkt-chip:hover,
.mkt-chip.on {
  border-color: var(--color-brand-500, #165dff);
  color: var(--color-brand-600, #0e42d2);
  background: var(--color-brand-50, #eef4ff);
}

.mkt-workspace {
  display: grid;
  grid-template-columns: 1fr 240px;
  gap: 14px;
  align-items: start;
}
.mkt-main { min-width: 0; }

.mkt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.mkt-toolbar h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-ink-900, #1f2329);
}
.mkt-toolbar h2 em {
  font-style: normal;
  color: var(--color-ink-500, #86909c);
  font-weight: 500;
  margin-left: 6px;
}
.mkt-toolbar h2 .mock-flag {
  font-size: 10.5px;
  color: var(--color-brand-600, #0e42d2);
  background: var(--color-brand-50, #eef4ff);
  padding: 2px 7px;
  border-radius: 999px;
  font-weight: 700;
  margin-left: 8px;
  vertical-align: middle;
}
.mkt-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.mkt-sort,
.mkt-view-toggle {
  display: flex;
  gap: 3px;
  background: var(--bg-elevated);
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 10px;
  padding: 3px;
}
.mkt-sort button {
  border: 0;
  background: transparent;
  color: var(--color-ink-500, #86909c);
  font-size: 12px;
  font-weight: 500;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.mkt-sort button.on {
  background: var(--color-brand-50, #eef4ff);
  color: var(--color-brand-600, #0e42d2);
}
.mkt-view-toggle button {
  border: 0;
  background: transparent;
  width: 32px;
  height: 28px;
  border-radius: 8px;
  color: var(--color-ink-500, #86909c);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.mkt-view-toggle button svg {
  width: 15px;
  height: 15px;
  stroke: currentColor;
  fill: none;
  stroke-width: 1.8;
}
.mkt-view-toggle button.on {
  background: var(--color-brand-50, #eef4ff);
  color: var(--color-brand-600, #0e42d2);
}

.mkt-filter {
  position: sticky;
  top: 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 14px;
  padding: 14px 12px 16px;
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
}
.mkt-filter-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 4px 12px;
  border-bottom: 1px solid var(--color-ink-200, #e5e6eb);
  margin-bottom: 12px;
}
.mkt-filter-h strong {
  font-size: 13px;
  font-weight: 700;
}
.mkt-filter-clear {
  border: 0;
  background: transparent;
  color: var(--color-brand-600, #0e42d2);
  font-size: 11px;
  font-weight: 600;
  padding: 4px;
  cursor: pointer;
}
.mkt-filter-clear:hover:not(:disabled) { text-decoration: underline; }
.mkt-filter-clear:disabled {
  color: var(--color-ink-300, #c9cdd4);
  cursor: not-allowed;
  text-decoration: none;
}
.mkt-filter-section + .mkt-filter-section { margin-top: 14px; }
.mkt-filter-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--color-ink-500, #86909c);
  padding: 0 4px;
  margin: 0 0 8px;
}
.mkt-filter-empty {
  font-size: 12px;
  color: var(--color-ink-500, #86909c);
  padding: 4px 8px;
}
.mkt-filter-tags,
.mkt-filter-authors {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mkt-filter-tag {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 8px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--color-ink-700, #4e5969);
  cursor: pointer;
  transition: background .15s, color .15s;
}
.mkt-filter-tag:hover { background: var(--color-ink-100, #f7f8fa); }
.mkt-filter-tag.on {
  background: var(--color-brand-50, #eef4ff);
  color: var(--color-brand-700, #0a2e9c);
}
.mkt-filter-tag .box {
  width: 14px;
  height: 14px;
  border: 1.5px solid var(--color-ink-300, #c9cdd4);
  border-radius: 3px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.mkt-filter-tag.on .box {
  background: var(--color-brand-500, #165dff);
  border-color: var(--color-brand-500, #165dff);
}
.mkt-filter-tag .box svg {
  width: 10px;
  height: 10px;
  stroke: #fff;
  fill: none;
  stroke-width: 3;
  opacity: 0;
}
.mkt-filter-tag.on .box svg { opacity: 1; }
.mkt-filter-tag .n,
.mkt-filter-author .n {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-ink-500, #86909c);
}
.mkt-filter-tag.on .n { color: var(--color-brand-600, #0e42d2); }
.mkt-filter-author {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  border: 1px solid transparent;
  background: transparent;
  text-align: left;
  padding: 8px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--color-ink-700, #4e5969);
  cursor: pointer;
  transition: background .15s, border-color .15s, color .15s;
}
.mkt-filter-author:hover { background: var(--color-ink-100, #f7f8fa); }
.mkt-filter-author.on {
  background: var(--color-brand-50, #eef4ff);
  border-color: var(--color-brand-100, #d9e6ff);
  color: var(--color-brand-700, #0a2e9c);
}
.mkt-filter-hint {
  margin-top: 14px;
  padding: 10px;
  background: var(--color-ink-100, #f7f8fa);
  border-radius: 8px;
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--color-ink-700, #4e5969);
}

.mkt-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.mkt-grid.view-list {
  grid-template-columns: 1fr;
  gap: 8px;
}

.mkt-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 14px;
  padding: 16px;
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
  transition: border-color .2s ease, transform .2s ease, box-shadow .2s ease;
}
.mkt-card:hover {
  border-color: var(--color-brand-100, #d9e6ff);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(22, 93, 255, .08);
}
.mkt-grid.view-list .mkt-card {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
  padding: 12px 14px;
}
.mkt-grid.view-list .mkt-card:hover { transform: none; }
.mkt-grid.view-list .mkt-card-top {
  flex: 1;
  min-width: 200px;
}
.mkt-grid.view-list .mkt-desc {
  -webkit-line-clamp: 1;
}
.mkt-grid.view-list .mkt-actions {
  margin-top: 0;
  padding-top: 0;
  margin-left: auto;
}
.mkt-grid.view-list .mkt-btn-danger { margin-left: 0; }

.mkt-card-top {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.mkt-avatar {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 11px;
  background: linear-gradient(145deg, var(--color-brand-100, #d9e6ff), var(--color-brand-50, #eef4ff));
  color: var(--color-brand-600, #0e42d2);
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 14px;
}
.mkt-card h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--color-ink-900, #1f2329);
}
.mkt-ver {
  font-size: 11px;
  color: var(--color-ink-500, #86909c);
  font-weight: 500;
  margin-left: 6px;
}
.mkt-desc {
  margin: 4px 0 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--color-ink-700, #4e5969);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.mkt-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.mkt-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-brand-600, #0e42d2);
  background: var(--color-brand-50, #eef4ff);
  padding: 3px 8px;
  border-radius: 6px;
}
.mkt-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 11px;
  color: var(--color-ink-500, #86909c);
}
.mkt-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.mkt-meta svg {
  width: 12px;
  height: 12px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}

.mkt-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
  padding-top: 4px;
  align-items: center;
}

.mkt-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid transparent;
  cursor: pointer;
  text-decoration: none;
  transition: background .15s, border-color .15s, color .15s, opacity .15s;
}
.mkt-btn svg {
  width: 14px;
  height: 14px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}
.mkt-btn-primary {
  background: var(--color-brand-500, #165dff);
  color: #fff;
}
.mkt-btn-primary:hover:not(:disabled) { background: var(--color-brand-600, #0e42d2); }
.mkt-btn-primary:disabled { opacity: .55; cursor: not-allowed; }
.mkt-btn-ghost {
  background: var(--bg-elevated);
  border-color: var(--color-ink-300, #c9cdd4);
  color: var(--color-ink-700, #4e5969);
}
.mkt-btn-ghost:hover:not(:disabled) {
  border-color: var(--color-brand-500, #165dff);
  color: var(--color-brand-600, #0e42d2);
}
.mkt-btn-ghost:disabled { opacity: .55; cursor: not-allowed; }
.mkt-btn-danger {
  margin-left: auto;
  background: transparent;
  color: var(--color-ink-500, #86909c);
  border: 0;
  padding: 0 6px;
}
.mkt-btn-danger:hover { color: #f53f3f; }

.mkt-btn-liked { color: #f53f3f !important; border-color: rgba(245,63,63,0.3) !important; }
.mkt-btn-liked:hover { background: rgba(245,63,63,0.06); }

/* 收藏星标 */
.mkt-fav-star {
  position: absolute; top: 8px; right: 8px; z-index: 1;
  width: 28px; height: 28px; display: grid; place-items: center;
  border: none; background: transparent; cursor: pointer;
  color: var(--color-ink-300, #c9cdd4); border-radius: 6px; transition: .15s;
}
.mkt-fav-star:hover { background: var(--bg-sunken, #f3f4f6); color: #ff7d00; }
.mkt-fav-star.on { color: #ff7d00; }
.mkt-fav-star svg { width: 16px; height: 16px; }

/* 我的页面分区 */
.mkt-mine-section { margin-bottom: 24px; }
.mkt-mine-title {
  font-size: 14px; font-weight: 700; margin: 0 0 12px;
  display: flex; align-items: center; gap: 6px;
}
.mkt-mine-title span {
  font-size: 11px; font-weight: 500; color: var(--text-tertiary);
  background: var(--bg-sunken, #f3f4f6); padding: 1px 6px; border-radius: 999px;
}

.mkt-empty {
  text-align: center;
  padding: 48px 20px;
  background: var(--bg-elevated);
  border: 1px dashed var(--color-ink-300, #c9cdd4);
  border-radius: 14px;
}
.mkt-empty svg {
  width: 40px;
  height: 40px;
  stroke: var(--color-brand-500, #165dff);
  fill: none;
  stroke-width: 1.6;
  margin-bottom: 12px;
}
.mkt-empty h3 {
  margin: 0 0 6px;
  font-size: 15px;
  color: var(--color-ink-900, #1f2329);
}
.mkt-empty p {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--color-ink-500, #86909c);
}
.mkt-spinner {
  width: 28px;
  height: 28px;
  margin: 0 auto 12px;
  border: 2.5px solid var(--color-brand-100, #d9e6ff);
  border-top-color: var(--color-brand-500, #165dff);
  border-radius: 50%;
  animation: mkt-spin .7s linear infinite;
}
@keyframes mkt-spin { to { transform: rotate(360deg); } }

@media (max-width: 1000px) {
  .mkt-workspace { grid-template-columns: 1fr; }
  .mkt-filter { position: static; }
}
@media (max-width: 640px) {
  .mkt-stats { grid-template-columns: 1fr; }
  .mkt-grid:not(.view-list) { grid-template-columns: 1fr; }
  .mkt-search input { padding-right: 88px; height: 44px; font-size: 13px; }
  .mkt-grid.view-list .mkt-card {
    flex-direction: column;
    align-items: stretch;
  }
  .mkt-grid.view-list .mkt-actions { margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .mkt-card,
  .mkt-chip,
  .mkt-btn,
  .mkt-search input { transition: none; }
  .mkt-spinner { animation: none; }
}
</style>
