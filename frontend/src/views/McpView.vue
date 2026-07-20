<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMcpStore, MCP_SOURCE_ORDER, MCP_SOURCE_LABELS, PULSEMCP_DOCS_URL, PULSEMCP_API_URL, PULSEMCP_MAILTO, type McpSourceId } from '../stores/mcp'

const emit = defineEmits<{ 'go-tab': [key: string] }>()

const mcp = useMcpStore()
const {
  mcpTemplate, mcpConfigData, mcpTab, mcpMarketQ, mcpMarketResults, mcpSearched,
  mcpMarketLoading, mcpMarketMeta, mcpMarketSources, pulseMcpConfigured,
  mcpForm, editingMcp, editMcpForm,
  listFilter, listQuery,
  filteredServers, mcpEnabledCount, mcpDisabledCount, mcpKeyCount, mcpServerEntries,
} = storeToRefs(mcp)
const {
  searchMcpMarket, toggleMarketSource, getMcpDetail, addMarketMcpToTemplate,
  fetchMcpDetail, resolveMcpInstallConfig,
  parsePastedMcp, addManualMcp, toggleAllMcp,
  startEditMcp, cancelEditMcp, saveEditMcp,
  toggleMcpDisabled, deleteMcpEntry, saveMcpConfig,
  loadPulseMcpStatus,
} = mcp

type DrawerMode = 'add' | 'edit' | null
const drawer = ref<DrawerMode>(null)
const marketInput = ref<HTMLInputElement | null>(null)

function gotoKeys() {
  emit('go-tab', 'keys')
}

const previewItem = ref<any>(null)
const previewPayload = ref<{ data?: any; install?: any; install_error?: string } | null>(null)
const previewLoading = ref(false)

const drawerTitle = computed(() => {
  if (drawer.value === 'add') return '添加 MCP'
  if (drawer.value === 'edit') return editingMcp.value ? `编辑 · ${editingMcp.value}` : '编辑'
  return ''
})

const drawerSub = computed(() => {
  if (drawer.value === 'add') return '选中条目后，右侧预览可直接确认配置'
  return ''
})

const sourceMetaItems = computed(() => {
  const sources = mcpMarketMeta.value?.sources || {}
  return MCP_SOURCE_ORDER
    .filter((src) => mcpMarketSources.value.includes(src) || sources[src])
    .map((src) => {
      const info = sources[src] || {}
      return {
        id: src,
        label: info.label || MCP_SOURCE_LABELS[src],
        count: info.count ?? 0,
        error: info.error || '',
      }
    })
})

const previewResolved = computed(() => {
  if (!previewItem.value || !previewPayload.value) return null
  return resolveMcpInstallConfig(previewItem.value, previewPayload.value)
})
const previewJson = computed(() => {
  const r = previewResolved.value
  if (!r?.cfg) return ''
  return JSON.stringify({ [r.key]: r.cfg }, null, 2)
})
const previewCanAdd = computed(() => !!previewResolved.value?.cfg && !previewLoading.value)
const previewRepoUrl = computed(() => {
  const item = previewItem.value
  const data = previewPayload.value?.data || {}
  return (
    item?.repo_url
    || data?.repository?.url
    || data?.repo_url
    || item?.homepage
    || ''
  )
})

const SUGGESTS = ['filesystem', 'github', 'browser', '地图']

function marketItemKey(item: any) {
  return String(item?.source || '') + ':' + String(item?.id || item?.name || '')
}
function isPreviewSelected(item: any) {
  return !!previewItem.value && marketItemKey(previewItem.value) === marketItemKey(item)
}
function clearPreview() {
  previewItem.value = null
  previewPayload.value = null
  previewLoading.value = false
}
async function selectMarketItem(item: any) {
  previewItem.value = item
  previewPayload.value = null
  previewLoading.value = true
  try {
    const r = await fetchMcpDetail(item)
    if (!r.ok) {
      previewPayload.value = { install_error: r.error || '获取失败' }
      return
    }
    previewPayload.value = r
  } finally {
    previewLoading.value = false
  }
}
async function addPreviewToConfigured() {
  if (!previewItem.value) return
  await addMarketMcpToTemplate(previewItem.value, previewPayload.value || undefined)
}
function setAddTab(tab: 'market' | 'manual') {
  mcpTab.value = tab
  if (tab === 'manual') clearPreview()
  else nextTick(() => marketInput.value?.focus())
}

async function openDrawer(mode: DrawerMode, editName?: string) {
  if (mode === 'edit' && editName) startEditMcp(editName)
  if (mode === 'add') {
    mcpTab.value = 'market'
    clearPreview()
    loadPulseMcpStatus()
  }
  drawer.value = mode
  await nextTick()
  if (mode === 'add') marketInput.value?.focus()
}
function closeDrawer() {
  if (drawer.value === 'edit') cancelEditMcp()
  clearPreview()
  drawer.value = null
}
async function saveEditAndClose() {
  await saveEditMcp()
  if (!editingMcp.value) drawer.value = null
}
async function addManualAndMaybeClose() {
  const before = Object.keys(mcpTemplate.value.mcpServers || {}).length
  await addManualMcp()
  const after = Object.keys(mcpTemplate.value.mcpServers || {}).length
  if (after > before) closeDrawer()
}
function suggestSearch(q: string) {
  mcpMarketQ.value = q
  searchMcpMarket()
}
function isSourceOn(src: McpSourceId) {
  return mcpMarketSources.value.includes(src)
}
const pulseMcpEnabled = computed(() => mcpMarketSources.value.includes('pulsemcp'))
async function confirmDeleteFromEdit() {
  const name = editingMcp.value
  if (!name) return
  await deleteMcpEntry(name)
  if (!mcpTemplate.value.mcpServers?.[name]) closeDrawer()
}

watch(mcpMarketResults, (list) => {
  if (!previewItem.value) return
  const still = list.some((item) => marketItemKey(item) === marketItemKey(previewItem.value))
  if (!still) clearPreview()
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && drawer.value) {
    e.preventDefault()
    closeDrawer()
  }
}
onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  loadPulseMcpStatus()
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="mcp-page">
    <div class="mcp-head flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0">
        <h1 class="text-[15px] font-semibold text-ink-900 m-0">MCP 配置</h1>
        <p class="text-xs text-ink-500 mt-1 mb-0">集中管理 MCP 服务 · 快速添加、编辑、同步与密钥设置</p>
  
      </div>
      <div class="btn-cluster">
        <button type="button" class="btn btn-secondary" @click="gotoKeys">
          <svg viewBox="0 0 24 24"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
          密钥
        </button>
        <button type="button" class="btn btn-soft" @click="openDrawer('add')">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
          添加 MCP
        </button>
      </div>
    </div>

    <div class="kpis">
      <div class="kpi brand"><b>{{ mcpServerEntries.length }}</b><span>已配置</span><em>模板中的服务总数</em></div>
      <div class="kpi live"><b>{{ mcpEnabledCount }}</b><span>启用中</span><em>将写入 mcp.json</em></div>
      <div class="kpi"><b>{{ mcpKeyCount }}</b><span>密钥</span><em>mcp.yaml · mcp</em></div>
      <div class="kpi warn"><b>{{ mcpDisabledCount }}</b><span>已禁用</span><em>可随时重新启用</em></div>
    </div>

    <section class="panel">
      <div class="toolbar">
        <div class="toolbar-left">
          <label class="search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#86909c" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
            <input v-model="listQuery" placeholder="筛选名称 / 命令 / 类型" />
          </label>
          <div class="seg" role="group" aria-label="启停筛选">
            <button type="button" :class="{ on: listFilter === 'all' }" @click="listFilter = 'all'">全部</button>
            <button type="button" :class="{ on: listFilter === 'on' }" @click="listFilter = 'on'">启用</button>
            <button type="button" :class="{ on: listFilter === 'off' }" @click="listFilter = 'off'">禁用</button>
          </div>
        </div>
        <div class="btn-cluster">
          <div class="btn-pair" role="group" aria-label="批量启停">
            <button type="button" class="btn btn-ghost btn-sm" @click="toggleAllMcp(true)">
              <svg viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
              全选
            </button>
            <button type="button" class="btn btn-ghost btn-sm" @click="toggleAllMcp(false)">
              <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>
              全不选
            </button>
          </div>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:72px">启用</th>
              <th>服务</th>
              <th style="width:100px">类型</th>
              <th>命令 / URL</th>
              <th style="width:90px">状态</th>
              <th style="width:132px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filteredServers" :key="s.name" :class="{ disabled: !s.enabled }">
              <td>
                <button
                  type="button"
                  class="switch"
                  :class="{ on: s.enabled }"
                  :aria-label="(s.enabled ? '禁用' : '启用') + ' ' + s.name"
                  @click="toggleMcpDisabled(s.name, !s.enabled)"
                />
              </td>
              <td><div class="name">{{ s.name }}</div></td>
              <td><span class="type-pill">{{ s.type }}</span></td>
              <td><div class="cmd" :title="s.cmd">{{ s.cmd || '—' }}</div></td>
              <td>
                <span class="status" :class="s.enabled ? 'on' : 'off'"><i />{{ s.enabled ? '启用' : '禁用' }}</span>
              </td>
              <td>
                <div class="ops">
                  <button type="button" class="btn btn-soft btn-sm" @click="openDrawer('edit', s.name)">
                    <svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                    编辑
                  </button>
                  <button type="button" class="btn btn-danger btn-icon btn-sm" :aria-label="'删除 ' + s.name" title="删除" @click="deleteMcpEntry(s.name)">
                    <svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!filteredServers.length">
              <td colspan="6" class="empty-cell">
                {{ mcpServerEntries.length ? '无匹配结果' : '暂无已配置 MCP，点击「添加 MCP」开始' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <Teleport to="body">
      <Transition name="mcp-studio">
        <div v-if="drawer" class="drawer-root">
          <div class="drawer-overlay" @click="closeDrawer" />

          <!-- MVP-C：添加 = 三栏目录工作室 -->
          <div
            v-if="drawer === 'add'"
            class="studio"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mcp-drawer-title"
          >
            <aside class="studio-nav">
              <div class="nav-brand">
                <b>Catalog</b>
                <button type="button" class="btn btn-icon btn-ghost" aria-label="关闭" @click="closeDrawer">
                  <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>
                </button>
              </div>
              <div>
                <div class="section-label">方式</div>
                <div class="mode-list">
                  <button type="button" class="mode" :class="{ on: mcpTab === 'market' }" @click="setAddTab('market')">
                    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
                    市场搜索
                  </button>
                  <button type="button" class="mode" :class="{ on: mcpTab === 'manual' }" @click="setAddTab('manual')">
                    <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
                    手动添加
                  </button>
                  <button type="button" class="mode" @click="gotoKeys">
                    <svg viewBox="0 0 24 24"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
                    密钥
                  </button>
                </div>
              </div>
              <div v-show="mcpTab === 'market'">
                <div class="section-label">数据源</div>
                <div class="src-list" role="group" aria-label="数据源过滤">
                  <button
                    v-for="src in MCP_SOURCE_ORDER"
                    :key="src"
                    type="button"
                    class="nav-src"
                    :class="{ on: isSourceOn(src), locked: src === 'pulsemcp' && !pulseMcpConfigured }"
                    :data-src="src"
                    :aria-pressed="isSourceOn(src)"
                    :title="src === 'pulsemcp' ? (pulseMcpConfigured ? 'PulseMCP（已配置 API Key）' : 'PulseMCP 需 API Key') : undefined"
                    @click="toggleMarketSource(src)"
                  >
                    <span class="box" aria-hidden="true">
                      <svg v-if="isSourceOn(src)" viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg>
                    </span>
                    {{ MCP_SOURCE_LABELS[src] }}
                    <span v-if="src === 'pulsemcp'" class="key-badge">Key</span>
                  </button>
                </div>
              </div>
            </aside>

            <section class="studio-catalog">
              <div class="cat-h">
                <div>
                  <h3 id="mcp-drawer-title">{{ drawerTitle }}</h3>
                  <p class="sub">{{ drawerSub }}</p>
                </div>
              </div>

              <template v-if="mcpTab === 'market'">
                <div class="cat-search">
                  <input
                    ref="marketInput"
                    v-model="mcpMarketQ"
                    placeholder="关键词，如：filesystem、github、地图…"
                    @keydown.enter="searchMcpMarket"
                  />
                  <button type="button" class="btn btn-primary" :disabled="mcpMarketLoading" @click="searchMcpMarket">
                    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
                    搜索
                  </button>
                </div>

                <div v-if="pulseMcpEnabled" class="pulse-tip" :class="{ ok: pulseMcpConfigured }">
                  <div class="pulse-tip-text">
                    <template v-if="pulseMcpConfigured">PulseMCP 已配置 API Key，将使用稳定的 v0.1 接口。</template>
                    <template v-else>
                      PulseMCP 需配置 <code>PULSEMCP_API_KEY</code>（可选 <code>PULSEMCP_TENANT_ID</code>）并重启应用。
                    </template>
                  </div>
                  <div class="pulse-tip-links">
                    <a :href="PULSEMCP_DOCS_URL" target="_blank" rel="noopener noreferrer">API 文档</a>
                    <a :href="PULSEMCP_API_URL" target="_blank" rel="noopener noreferrer">申请 / 了解</a>
                    <a :href="PULSEMCP_MAILTO">邮件申请</a>
                  </div>
                </div>

                <div class="meta-bar">
                  <template v-if="mcpMarketLoading"><span>正在并行查询各源…</span></template>
                  <template v-else-if="mcpSearched">
                    <span>共 <strong>{{ mcpMarketResults.length }}</strong> 条 · 已跨源去重</span>
                  </template>
                  <template v-else>
                    <span>并行检索已选市场；PulseMCP 默认关闭（需 Key）</span>
                  </template>
                  <div v-if="mcpSearched && sourceMetaItems.length" class="src-meta">
                    <span
                      v-for="m in sourceMetaItems"
                      :key="m.id"
                      :class="{ err: !!m.error }"
                      :title="m.error || undefined"
                    >{{ m.label }} · {{ m.error ? '失败' : m.count }}</span>
                  </div>
                </div>

                <div class="results">
                  <div v-if="mcpMarketLoading" class="m-loading">
                    <div class="spinner" aria-hidden="true" />
                    聚合搜索中…
                  </div>
                  <div v-else-if="!mcpSearched" class="m-hint">
                    输入关键词，从多个 MCP 市场一次搜齐。<br />选中结果后在右侧预览配置。
                    <div class="suggest-row">
                      <button v-for="s in SUGGESTS" :key="s" type="button" class="suggest" @click="suggestSearch(s)">{{ s }}</button>
                    </div>
                  </div>
                  <div v-else-if="!mcpMarketResults.length" class="m-empty">无结果。换个关键词，或调整左侧数据源。</div>
                  <template v-else>
                    <article
                      v-for="s in mcpMarketResults"
                      :key="marketItemKey(s)"
                      class="m-card"
                      :class="['from-' + String(s.source || '').toLowerCase(), { sel: isPreviewSelected(s) }]"
                      tabindex="0"
                      @click="selectMarketItem(s)"
                      @keydown.enter.prevent="selectMarketItem(s)"
                    >
                      <div class="m-card-top">
                        <h4 :title="s.name">{{ s.name }}</h4>
                        <div class="m-tags">
                          <span
                            class="src-tag"
                            :class="String(s.source || '').toLowerCase()"
                            :title="'来源：' + (s.source_label || s.source)"
                          >
                            <span class="dot" aria-hidden="true" />
                            {{ s.source_label || MCP_SOURCE_LABELS[s.source as McpSourceId] || s.source }}
                          </span>
                          <span v-if="s.is_hosted" class="host-tag">Hosted</span>
                        </div>
                      </div>
                      <div class="meta" :title="[s.id, s.author || s.owner].filter(Boolean).join(' · ')">
                        {{ [s.id, s.author || s.owner].filter(Boolean).join(' · ') || '—' }}
                      </div>
                      <p>{{ s.description || '暂无描述' }}</p>
                    </article>
                  </template>
                </div>
              </template>

              <template v-else>
                <div class="results form-pad">
                  <div class="manual-form">
                    <div class="field"><label>name *</label><input v-model="mcpForm.name" placeholder="my-mcp" /></div>
                    <div class="field">
                      <label>type</label>
                      <select v-model="mcpForm.type">
                        <option value="">stdio（默认）</option>
                        <option value="http">http</option>
                        <option value="streamableHttp">streamableHttp</option>
                      </select>
                    </div>
                    <div class="field"><label>command</label><input v-model="mcpForm.command" placeholder="npx" /></div>
                    <div class="field"><label>args</label><input v-model="mcpForm.args" placeholder="-y, package" /></div>
                    <div class="field full"><label>url</label><input v-model="mcpForm.url" placeholder="http 类型填写" /></div>
                    <div class="field full"><label>headers</label><textarea v-model="mcpForm.headers" rows="2" placeholder='{"Authorization":"Bearer xxx"}' /></div>
                    <div class="field full"><label>env</label><textarea v-model="mcpForm.env" rows="2" placeholder='{"API_KEY":"xxx"}' /></div>
                    <div class="field full"><label>Smithery 粘贴</label><textarea v-model="mcpForm.paste" rows="3" placeholder="粘贴完整 MCP 配置 JSON，自动解析" /></div>
                  </div>
                </div>
              </template>
            </section>

            <aside class="studio-preview">
              <template v-if="mcpTab === 'manual'">
                <div class="prev-h">
                  <div class="eyebrow">手动配置</div>
                  <h4>{{ mcpForm.name.trim() || '未命名服务' }}</h4>
                  <div class="id">{{ mcpForm.type || 'stdio' }} · 填写左侧表单后添加</div>
                </div>
                <div class="prev-b">
                  <p class="desc">支持粘贴 Smithery / 完整 mcpServers JSON，点「解析粘贴」自动填入字段。</p>
                  <div class="kv">
                    <div><label>Command</label><b>{{ mcpForm.command || '—' }}</b></div>
                    <div><label>Args</label><b>{{ mcpForm.args || '—' }}</b></div>
                    <div><label>URL</label><b>{{ mcpForm.url || '—' }}</b></div>
                  </div>
                </div>
                <div class="prev-f">
                  <div class="row">
                    <button type="button" class="btn btn-secondary" @click="parsePastedMcp">解析粘贴</button>
                    <button type="button" class="btn btn-primary" @click="addManualAndMaybeClose">
                      <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
                      添加到已配置
                    </button>
                  </div>
                </div>
              </template>

              <template v-else-if="previewItem">
                <div class="prev-h">
                  <div class="eyebrow">配置预览</div>
                  <h4>{{ previewItem.name || previewItem.id }}</h4>
                  <div class="id">
                    {{ previewItem.source_label || previewItem.source || 'market' }}
                    <template v-if="previewItem.id"> · {{ previewItem.id }}</template>
                  </div>
                </div>
                <div class="prev-b">
                  <p class="desc">{{ previewItem.description || '暂无描述' }}</p>
                  <div v-if="previewLoading" class="m-loading compact">
                    <div class="spinner" aria-hidden="true" />
                    加载配置…
                  </div>
                  <template v-else-if="previewResolved?.cfg">
                    <p v-if="previewPayload?.install?.resolved_from === 'repo'" class="auto-hint">
                      已从仓库自动生成配置；如有 Token 占位符，请到「密钥配置」补全。
                    </p>
                    <div class="kv">
                      <div><label>Local name</label><b>{{ previewResolved.key }}</b></div>
                      <div><label>Type</label><b>{{ previewResolved.cfg.type || (previewResolved.cfg.url ? 'http' : 'stdio') }}</b></div>
                      <div v-if="previewResolved.cfg.command"><label>Command</label><b>{{ previewResolved.cfg.command }}</b></div>
                      <div v-if="previewResolved.cfg.args"><label>Args</label><b>{{ (previewResolved.cfg.args || []).join(' ') }}</b></div>
                      <div v-if="previewResolved.cfg.url"><label>URL</label><b>{{ previewResolved.cfg.url }}</b></div>
                    </div>
                    <pre class="code">{{ previewJson }}</pre>
                  </template>
                  <div v-else class="m-empty compact">
                    <p>{{ previewPayload?.install_error || previewResolved?.error || '无法自动生成配置，请改用手动添加' }}</p>
                    <a
                      v-if="previewRepoUrl"
                      class="repo-link"
                      :href="previewRepoUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                    >打开仓库</a>
                    <button type="button" class="btn btn-soft" @click="setAddTab('manual')">改用手动添加</button>
                  </div>
                </div>
                <div class="prev-f">
                  <div class="row">
                    <button type="button" class="btn btn-secondary" @click="getMcpDetail(previewItem)">查看完整</button>
                    <button type="button" class="btn btn-primary" :disabled="!previewCanAdd" @click="addPreviewToConfigured">
                      <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
                      添加到已配置
                    </button>
                  </div>
                </div>
              </template>

              <div v-else class="empty-prev">
                <p>在中间列表选中一条结果<br />即可在此预览并添加</p>
              </div>
            </aside>
          </div>

          <!-- 编辑 / 密钥：紧凑居中面板 -->
          <aside
            v-else
            class="studio studio-sm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mcp-drawer-title"
          >
            <div class="sm-panel">
              <div class="cat-h">
                <div>
                  <h3 id="mcp-drawer-title">{{ drawerTitle }}</h3>
                  <p v-if="drawerSub" class="sub">{{ drawerSub }}</p>
                </div>
                <button type="button" class="btn btn-icon btn-ghost" aria-label="关闭" @click="closeDrawer">
                  <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>
                </button>
              </div>
              <div class="sm-body">
                <template v-if="drawer === 'edit'">
                  <div class="field"><label>type</label>
                    <select v-model="editMcpForm.type">
                      <option value="">stdio</option>
                      <option value="http">http</option>
                      <option value="streamableHttp">streamableHttp</option>
                    </select>
                  </div>
                  <div class="field"><label>command</label><input v-model="editMcpForm.command" /></div>
                  <div class="field"><label>args</label><input v-model="editMcpForm.args" placeholder="逗号分隔" /></div>
                  <div class="field"><label>url</label><input v-model="editMcpForm.url" /></div>
                  <div class="field"><label>headers</label><textarea v-model="editMcpForm.headers" rows="3" /></div>
                  <div class="field"><label>env</label><textarea v-model="editMcpForm.env" rows="3" /></div>
                  <div class="danger-zone">
                    <button type="button" class="btn btn-danger-outline" @click="confirmDeleteFromEdit">
                      <svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>
                      删除此服务
                    </button>
                  </div>
                </template>
                <template v-else>
                  <!-- drawer 只允许 'add' | 'edit'，密钥已迁移到独立 Tab -->
                </template>
              </div>
              <div class="prev-f">
                <div class="row" v-if="drawer === 'edit'">
                  <button type="button" class="btn btn-secondary" @click="closeDrawer">取消</button>
                  <button type="button" class="btn btn-primary" @click="saveEditAndClose">
                    <svg viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>
                    保存更改
                  </button>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.mcp-page,
.drawer-root {
  --red: #f53f3f;
  --red-bg: #ffece8;
  --red-border: #f9c2c0;
  --green: #00b42a;
  --green-bg: #e8ffea;
  --amber: #ff7d00;
  --amber-bg: #fff7e8;
  --purple: #722ed1;
  --purple-bg: #f5e8ff;
}
.mcp-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-bottom: 12px;
}
.mcp-head { margin: 0; }

.btn {
  height: 34px; padding: 0 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  white-space: nowrap; border: 1px solid transparent; cursor: pointer;
  transition: background .18s ease, color .18s ease, border-color .18s ease;
  background: none; color: inherit; user-select: none;
}
.btn svg { width: 14px; height: 14px; flex-shrink: 0; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn-sm { height: 28px; padding: 0 10px; font-size: 11px; border-radius: 7px; }
.btn-sm svg { width: 13px; height: 13px; }
.btn-icon { width: 32px; padding: 0; }
.btn-icon.btn-sm { width: 28px; }
.btn-primary { background: var(--primary); color: #fff; box-shadow: 0 1px 2px rgba(22,93,255,.22); }
.btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
.btn-soft { background: var(--primary-container); color: var(--primary-hover); border-color: var(--primary-container-strong); }
.btn-soft:hover:not(:disabled) { background: #d9e6ff; }
.btn-secondary { background: var(--bg-elevated); color: var(--text-secondary); border-color: var(--border-base); }
.btn-secondary:hover:not(:disabled) { background: var(--bg-base); border-color: var(--border-strong); }
.btn-ghost { background: transparent; color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { background: var(--bg-base); color: var(--text-primary); }
.btn-danger { background: transparent; color: var(--text-tertiary); }
.btn-danger:hover:not(:disabled), .btn-danger:focus-visible { background: var(--red-bg); color: var(--red); border-color: var(--red-border); }
.btn-danger-outline { background: var(--bg-elevated); color: var(--red); border-color: var(--red-border); }
.btn-danger-outline:hover:not(:disabled) { background: var(--red-bg); }

.btn-cluster { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.btn-cluster .split { width: 1px; height: 20px; background: var(--border-base); margin: 0 2px; }
.btn-pair {
  display: inline-flex; border-radius: 8px; overflow: hidden;
  border: 1px solid var(--border-base); background: var(--bg-elevated);
}
.btn-pair .btn { border-radius: 0; border: none; height: 32px; border-right: 1px solid var(--border-base); }
.btn-pair .btn:last-child { border-right: none; }

.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi {
  background: var(--bg-elevated); border-radius: 12px; padding: 16px 18px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
  border: 1px solid rgba(0,0,0,.03); position: relative; overflow: hidden;
}
.kpi::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--border-strong); }
.kpi.live::before { background: var(--green); }
.kpi.warn::before { background: var(--amber); }
.kpi.brand::before { background: var(--primary); }
.kpi b { display: block; font-size: 22px; font-variant-numeric: tabular-nums; line-height: 1.1; color: var(--text-primary); }
.kpi span { font-size: 12px; color: var(--text-tertiary); }
.kpi em { font-style: normal; font-size: 11px; color: var(--text-tertiary); margin-top: 6px; display: block; }

.panel {
  background: var(--bg-elevated); border-radius: 14px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
  border: 1px solid rgba(0,0,0,.03); overflow: hidden;
}
.toolbar {
  display: flex; justify-content: space-between; gap: 14px; flex-wrap: wrap;
  padding: 14px 18px; border-bottom: 1px solid var(--border-base); align-items: center;
}
.toolbar-left { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.search {
  display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px;
  border: 1px solid var(--border-strong); border-radius: 8px; background: var(--bg-elevated); min-width: 220px;
}
.search input { border: none; outline: none; flex: 1; font-size: 12px; min-width: 0; background: transparent; }
.seg { display: inline-flex; background: var(--bg-base); padding: 3px; border-radius: 8px; }
.seg button {
  height: 28px; padding: 0 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
  color: var(--text-tertiary); border: none; background: transparent; cursor: pointer;
}
.seg button.on { background: var(--bg-elevated); color: var(--primary-hover); box-shadow: 0 1px 2px rgba(0,0,0,.06); }

.table-wrap { max-height: min(560px, 62vh); overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left; font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase;
  letter-spacing: .04em; padding: 11px 18px; background: var(--bg-base); border-bottom: 1px solid var(--border-base);
  position: sticky; top: 0; z-index: 1;
}
td { padding: 13px 18px; border-bottom: 1px solid #f7f8fa; vertical-align: middle; }
th:first-child, td:first-child { padding-left: 18px; }
th:last-child, td:last-child { padding-right: 18px; }
tr:hover td { background: var(--bg-base); }
tr.disabled td { opacity: .62; }
.name { font-weight: 650; color: var(--text-primary); }
.cmd {
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; color: var(--text-tertiary);
  max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.type-pill {
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10px; padding: 2px 7px; border-radius: 4px;
  background: var(--bg-base); color: var(--text-secondary); border: 1px solid var(--border-base);
}
.status { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; }
.status i { width: 7px; height: 7px; border-radius: 50%; background: var(--border-strong); display: inline-block; }
.status.on { color: var(--green); }
.status.on i { background: var(--green); box-shadow: 0 0 0 3px var(--green-bg); }
.status.off { color: var(--text-tertiary); }
.switch {
  width: 36px; height: 20px; border-radius: 999px; background: var(--border-strong); position: relative;
  border: none; cursor: pointer; transition: background .2s; padding: 0;
}
.switch::after {
  content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
  background: var(--bg-elevated); transition: transform .2s; box-shadow: 0 1px 2px rgba(0,0,0,.15);
}
.switch.on { background: var(--primary); }
.switch.on::after { transform: translateX(16px); }
.ops { display: inline-flex; align-items: center; gap: 4px; padding: 2px; border-radius: 9px; }
tr:hover .ops { background: var(--bg-base); }
.ops .btn-soft { border-color: transparent; background: transparent; color: var(--primary-hover); }
.ops .btn-soft:hover { background: var(--bg-elevated); border-color: var(--primary-container-strong); }
.empty-cell { text-align: center; color: var(--text-tertiary); padding: 36px !important; }

.drawer-root {
  position: fixed; inset: 0; z-index: 60;
  display: flex; align-items: center; justify-content: center;
  padding: 24px; box-sizing: border-box;
}
.drawer-overlay { position: absolute; inset: 0; background: rgba(31,35,41,.4); }

.studio {
  position: relative; z-index: 1;
  width: min(980px, 100%); height: min(640px, calc(100vh - 48px));
  background: var(--bg-elevated); border-radius: 18px;
  box-shadow: 0 28px 72px rgba(15,20,30,.28);
  display: flex; align-items: stretch; overflow: hidden;
}
.studio-sm {
  width: min(480px, 100%); height: auto; max-height: min(86vh, 720px);
  display: flex; flex-direction: column;
}
.sm-panel { display: flex; flex-direction: column; min-height: 0; flex: 1; width: 100%; }
.sm-body { flex: 1; overflow: auto; padding: 16px 18px; min-height: 0; }
.studio-nav {
  width: 180px; flex: 0 0 180px;
  background: linear-gradient(180deg, #f7f9fd, #eef3fb);
  border-right: 1px solid var(--border-base);
  padding: 14px 12px; display: flex; flex-direction: column; gap: 14px;
  overflow: auto; min-height: 0; z-index: 2;
}
.studio-catalog {
  flex: 1 1 0%;
  min-width: 260px; min-height: 0;
  display: flex; flex-direction: column;
  background: var(--bg-elevated); overflow: hidden; z-index: 1;
}
.studio-preview {
  width: 280px; flex: 0 0 280px;
  border-left: 1px solid var(--border-base);
  background: linear-gradient(180deg, #fafbfd, #f3f6fb);
  display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; z-index: 2;
}
.nav-brand {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 0 4px 4px;
}
.nav-brand b {
  font-size: 12px; font-weight: 700; color: var(--primary-hover); letter-spacing: .04em; text-transform: uppercase;
}
.section-label {
  font-size: 10px; font-weight: 700; color: var(--text-tertiary);
  letter-spacing: .06em; text-transform: uppercase; padding: 0 6px; margin-bottom: 6px;
}
.mode-list { display: flex; flex-direction: column; gap: 4px; }
.mode {
  height: 34px; border: none; border-radius: 9px; background: transparent;
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  display: flex; align-items: center; gap: 8px; padding: 0 10px; cursor: pointer; text-align: left;
  transition: background .15s, color .15s;
}
.mode svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; opacity: .7; }
.mode:hover { background: rgba(22,93,255,.06); color: var(--primary-hover); }
.mode.on { background: var(--bg-elevated); color: var(--primary-hover); box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.mode.on svg { opacity: 1; }
.src-list { display: flex; flex-direction: column; gap: 4px; }
.nav-src {
  height: 30px; border-radius: 8px; border: 1px solid transparent; background: transparent;
  font-size: 11px; font-weight: 600; color: var(--text-tertiary);
  display: flex; align-items: center; gap: 8px; padding: 0 8px; cursor: pointer; text-align: left;
}
.nav-src .box {
  width: 14px; height: 14px; border-radius: 4px; border: 1.5px solid var(--border-strong);
  display: grid; place-items: center; background: var(--bg-elevated); flex-shrink: 0;
}
.nav-src .box svg { width: 9px; height: 9px; stroke: #fff; fill: none; stroke-width: 3; }
.nav-src.on { color: var(--text-primary); background: rgba(255,255,255,.7); }
.nav-src.on .box { background: var(--primary); border-color: var(--primary); }
.nav-src[data-src="smithery"].on .box { background: #722ed1; border-color: #722ed1; }
.nav-src[data-src="modelscope"].on .box { background: #00b42a; border-color: #00b42a; }
.nav-src[data-src="pulsemcp"].on .box { background: #ff7d00; border-color: #ff7d00; }
.nav-src[data-src="glama"].on .box { background: #4e5969; border-color: var(--text-secondary); }
.nav-src.locked:not(.on) { border-style: dashed; border-color: var(--border-base); }
.nav-src .key-badge {
  margin-left: auto; font-size: 9px; font-weight: 800; padding: 1px 5px; border-radius: 999px;
  background: #fff7e8; color: #ff7d00; border: 1px solid #ffe0b3;
}

.cat-h {
  padding: 14px 16px 10px; border-bottom: 1px solid var(--border-base);
  display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;
}
.cat-h h3 { margin: 0 0 4px; font-size: 15px; font-weight: 700; color: var(--text-primary); }
.cat-h .sub { margin: 0; font-size: 12px; color: var(--text-tertiary); line-height: 1.4; }
.cat-search { margin: 12px 16px 0; display: flex; gap: 8px; }
.cat-search input {
  flex: 1; height: 38px; border: 1.5px solid var(--border-strong); border-radius: 10px;
  padding: 0 12px; font-size: 13px; background: var(--bg-elevated);
}
.cat-search input:focus {
  outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(22,93,255,.15);
}
.cat-search .btn { height: 38px; border-radius: 10px; padding: 0 14px; }
.meta-bar {
  display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap;
  padding: 10px 16px; font-size: 11px; color: var(--text-tertiary);
}
.meta-bar strong { color: var(--text-primary); }
.src-meta { display: flex; flex-wrap: wrap; gap: 4px; }
.src-meta span {
  padding: 2px 7px; border-radius: 6px; background: var(--bg-base); border: 1px solid var(--border-base); font-weight: 600;
}
.src-meta span.err { color: var(--red); border-color: var(--red-border); background: var(--red-bg); }

.results {
  flex: 1 1 0%; min-height: 0; min-width: 0;
  overflow-x: hidden; overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px 20px 20px;
  display: flex; flex-direction: column; gap: 10px;
  align-items: stretch;
  box-sizing: border-box;
}
.results.form-pad { padding: 12px 20px 20px; overflow-y: auto; }
.m-card {
  border: 1px solid var(--border-base);
  border-left: 3px solid var(--border-strong);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--bg-elevated);
  width: 100%; max-width: 100%;
  box-sizing: border-box;
  flex: 0 0 auto;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s, background .15s;
}
.m-card.from-registry { border-left-color: var(--primary); }
.m-card.from-smithery { border-left-color: #722ed1; }
.m-card.from-modelscope { border-left-color: #00b42a; }
.m-card.from-pulsemcp { border-left-color: #ff7d00; }
.m-card.from-glama { border-left-color: var(--text-secondary); }
.m-card:hover {
  border-top-color: #d9e6ff;
  border-right-color: #d9e6ff;
  border-bottom-color: #d9e6ff;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
}
.m-card.sel {
  border-color: var(--primary);
  background: var(--primary-container);
  outline: 2px solid rgba(22,93,255,.28);
  outline-offset: 1px;
}
.m-card.sel.from-registry { border-left-color: var(--primary); }
.m-card.sel.from-smithery { border-left-color: #722ed1; }
.m-card.sel.from-modelscope { border-left-color: #00b42a; }
.m-card.sel.from-pulsemcp { border-left-color: #ff7d00; }
.m-card.sel.from-glama { border-left-color: var(--text-secondary); }
.m-card-top {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;
  margin-bottom: 6px; min-width: 0;
}
.m-card h4 {
  margin: 0; font-size: 13px; font-weight: 650; line-height: 1.3;
  flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; word-break: break-word; color: var(--text-primary);
}
.m-tags { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; flex: 0 1 auto; max-width: 46%; }
.src-tag {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 999px;
  border: 1px solid transparent; white-space: nowrap;
}
.src-tag .dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.src-tag.registry { background: var(--primary-container); color: var(--primary-hover); border-color: var(--primary-container-strong); }
.src-tag.registry .dot { background: var(--primary); }
.src-tag.smithery { background: #f5e8ff; color: #722ed1; border-color: #e6d0ff; }
.src-tag.smithery .dot { background: #722ed1; }
.src-tag.modelscope { background: #e8ffea; color: #00b42a; border-color: #b7ebc4; }
.src-tag.modelscope .dot { background: #00b42a; }
.src-tag.pulsemcp { background: #fff7e8; color: #ff7d00; border-color: #ffe0b3; }
.src-tag.pulsemcp .dot { background: #ff7d00; }
.src-tag.glama { background: var(--bg-base); color: var(--text-primary); border-color: var(--border-strong); }
.src-tag.glama .dot { background: #4e5969; }
.host-tag {
  font-size: 10px; font-weight: 700; padding: 3px 7px; border-radius: 999px;
  background: #e8ffea; color: #00b42a; border: 1px solid #b7ebc4; white-space: nowrap;
}
.m-card .meta {
  font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
}
.m-card p {
  margin: 0; font-size: 12px; color: var(--text-secondary); line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.prev-h { padding: 16px 16px 12px; border-bottom: 1px solid var(--border-base); }
.prev-h .eyebrow {
  font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: var(--primary); margin-bottom: 6px;
}
.prev-h h4 { margin: 0 0 6px; font-size: 15px; font-weight: 700; line-height: 1.25; word-break: break-word; }
.prev-h .id { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; color: var(--text-tertiary); }
.prev-b { flex: 1; overflow: auto; padding: 14px 16px; }
.desc { font-size: 13px; line-height: 1.55; color: var(--text-secondary); margin: 0 0 14px; }
.auto-hint {
  margin: 0 0 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--primary-container);
  color: var(--primary-hover);
  font-size: 12px;
  line-height: 1.45;
}
.kv { display: grid; gap: 10px; margin-bottom: 14px; }
.kv div {
  background: var(--bg-elevated); border: 1px solid var(--border-base); border-radius: 10px; padding: 10px 12px;
}
.kv label {
  display: block; font-size: 10px; font-weight: 700; color: var(--text-tertiary);
  letter-spacing: .04em; text-transform: uppercase; margin-bottom: 4px;
}
.kv b { font-size: 12px; font-weight: 600; color: var(--text-primary); word-break: break-word; }
.code {
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; line-height: 1.5;
  background: var(--text-primary); color: #d7e3ff; border-radius: 10px; padding: 12px; overflow: auto; margin: 0;
  white-space: pre-wrap; word-break: break-word;
}
.prev-f {
  padding: 12px 16px; border-top: 1px solid var(--border-base);
  background: rgba(255,255,255,.7);
}
.prev-f .row { display: flex; gap: 8px; }
.prev-f .btn { flex: 1; }
.empty-prev {
  flex: 1; display: grid; place-items: center; text-align: center;
  padding: 24px; color: var(--text-tertiary); font-size: 13px; line-height: 1.5;
}

.pulse-tip {
  display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 8px 12px;
  margin: 10px 16px 0; padding: 10px 12px; border-radius: 10px;
  background: #fff7e8; border: 1px solid #ffe0b3; color: #ad4e00;
  font-size: 12px; line-height: 1.5;
}
.pulse-tip.ok { background: #e8ffea; border-color: #b7f0c0; color: #008026; }
.pulse-tip-text { flex: 1; min-width: 160px; }
.pulse-tip-text code {
  font-size: 11px; padding: 0 4px; border-radius: 4px; background: rgba(0,0,0,.06);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.pulse-tip-links { display: flex; flex-wrap: wrap; gap: 8px; }
.pulse-tip-links a { color: inherit; font-weight: 650; text-decoration: underline; text-underline-offset: 2px; }

.m-empty, .m-loading, .m-hint {
  text-align: center; padding: 36px 16px; color: var(--text-tertiary); font-size: 13px; line-height: 1.5;
}
.m-empty.compact, .m-loading.compact { padding: 20px 8px; }
.m-empty.compact {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
}
.m-empty.compact p { margin: 0; }
.m-empty .repo-link {
  color: var(--primary); font-size: 12px; font-weight: 600; text-decoration: none;
}
.m-empty .repo-link:hover { text-decoration: underline; }
.m-loading { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.spinner {
  width: 22px; height: 22px; border: 2.5px solid var(--primary-container-strong); border-top-color: var(--primary);
  border-radius: 50%; animation: mcp-spin .7s linear infinite;
}
@keyframes mcp-spin { to { transform: rotate(360deg); } }
.suggest-row { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-top: 12px; }
.suggest {
  height: 28px; padding: 0 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  background: var(--bg-elevated); border: 1px solid var(--border-base); color: var(--text-secondary); cursor: pointer;
}
.suggest:hover { border-color: var(--primary-container-strong); color: var(--primary-hover); background: var(--primary-container); }

.manual-form { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.manual-form .field { margin-bottom: 0; }
.field.full, .manual-form .field.full { grid-column: 1 / -1; }
.field label { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.field input, .field select, .field textarea {
  width: 100%; border: 1px solid var(--border-strong); border-radius: 8px; padding: 9px 11px; font-size: 13px;
  background: var(--bg-elevated); color: var(--text-primary);
}
.field input:focus, .field select:focus, .field textarea:focus {
  outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(22,93,255,.15);
}
.field textarea { font-family: 'JetBrains Mono', Consolas, monospace; resize: vertical; min-height: 72px; }
.danger-zone { margin-top: 8px; padding-top: 14px; border-top: 1px solid var(--border-base); }
.keys-hint { margin: 0 0 14px; font-size: 12px; color: var(--text-tertiary); line-height: 1.5; }
.keys-list { display: grid; gap: 8px; }
.key-row { display: grid; grid-template-columns: 140px 1fr auto; gap: 8px; align-items: center; }
.key-row code {
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; color: var(--text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.key-row input {
  height: 34px; border: 1px solid var(--border-strong); border-radius: 8px; padding: 0 10px;
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px;
}

.mcp-studio-enter-active, .mcp-studio-leave-active { transition: opacity .2s ease; }
.mcp-studio-enter-active .studio, .mcp-studio-leave-active .studio {
  transition: transform .22s ease-out, opacity .22s ease-out;
}
.mcp-studio-enter-from, .mcp-studio-leave-to { opacity: 0; }
.mcp-studio-enter-from .studio, .mcp-studio-leave-to .studio {
  transform: translateY(8px) scale(.98); opacity: 0;
}

@media (max-width: 900px) {
  .kpis { grid-template-columns: 1fr 1fr; }
  .cmd { max-width: 160px; }
  .manual-form { grid-template-columns: 1fr; }
  .key-row { grid-template-columns: 1fr; }
  .drawer-root { padding: 12px; align-items: stretch; }
  .studio {
    width: 100%; height: min(92vh, 760px);
    flex-direction: column;
  }
  .studio-nav {
    width: 100%; flex: 0 0 auto;
    flex-direction: row; flex-wrap: wrap; align-items: flex-start;
    border-right: none; border-bottom: 1px solid var(--border-base); gap: 10px;
    max-height: 160px;
  }
  .mode-list, .src-list { flex-direction: row; flex-wrap: wrap; }
  .studio-catalog { flex: 1 1 0%; min-height: 0; }
  .studio-preview {
    width: 100%; flex: 0 0 auto; max-height: 38%;
    border-left: none; border-top: 1px solid var(--border-base);
  }
}
@media (prefers-reduced-motion: reduce) {
  .btn, .switch, .switch::after, .spinner,
  .mcp-studio-enter-active, .mcp-studio-leave-active,
  .mcp-studio-enter-active .studio, .mcp-studio-leave-active .studio {
    transition: none !important; animation: none !important;
  }
}
</style>
