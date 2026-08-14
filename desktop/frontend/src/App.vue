<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import Header from './components/Header.vue'
import Toast from './components/Toast.vue'
import Modal from './components/Modal.vue'
import AppDialog from './components/AppDialog.vue'
import AuthDialog from './components/AuthDialog.vue'
import LogPanel from './components/LogPanel.vue'
import IdeView from './views/IdeView.vue'
import LlmView from './views/LlmView.vue'
import McpView from './views/McpView.vue'
import KeysView from './views/KeysView.vue'
import SkillView from './views/SkillView.vue'
import CommandView from './views/CommandView.vue'
import SubagentView from './views/SubagentView.vue'
import PluginView from './views/PluginView.vue'
import PluginBuildView from './views/PluginBuildView.vue'
import RulesView from './views/RulesView.vue'
import HooksView from './views/HooksView.vue'
import MemoryView from './views/MemoryView.vue'
import MarketplaceView from './views/MarketplaceView.vue'
import TokenView from './views/TokenView.vue'
import { useIdeStore } from './stores/ide'
import { useEnvStore } from './stores/env'
import { useMcpStore } from './stores/mcp'
import { useKeysStore } from './stores/keys'
import { useAuthStore } from './stores/auth'

const tab = ref('marketplace')
// 菜单分组定义（两级菜单）
interface TabItem { key: string; label: string }
interface TabGroup {
  group: string
  label: string
  items: TabItem[]
}
const tabs: TabGroup[] = [
  { group: 'ide', label: 'AIDE 管理', items: [{ key: 'ide', label: 'AIDE 管理' }] },
  { group: 'keys', label: '密钥管理', items: [{ key: 'keys', label: '密钥管理' }] },
  {
    group: 'agent',
    label: 'Agent 配置',
    items: [
      { key: 'env', label: 'LLM 配置' },
      { key: 'mcp', label: 'MCP 配置' },
      { key: 'skill', label: 'Skills 管理' },
      { key: 'command', label: '自定义命令' },
      { key: 'subagent', label: 'Subagent' },
      { key: 'rules', label: 'Rules' },
      { key: 'hooks', label: 'Hooks' },
      { key: 'memory', label: '记忆' },
    ],
  },
  { group: 'plugin', label: '插件管理', items: [{ key: 'plugin', label: '插件管理' }] },
  { group: 'marketplace', label: '插件市场', items: [{ key: 'marketplace', label: '插件市场' }] },
  { group: 'plugin-build', label: '插件构建', items: [{ key: 'plugin-build', label: '插件构建' }] },
  { group: 'token', label: 'Token 市场', items: [{ key: 'token', label: 'Token 市场' }] },
  // ttyd 终端已隐藏（功能意义不大，后续如需恢复取消注释即可）
  // { group: 'tools', label: '工具', items: [{ key: 'terminal', label: '终端测试' }] },
]
// 扁平化（用于查找）
const flatTabs: TabItem[] = tabs.flatMap(g => g.items)
const defaultFavoriteKeys = ['marketplace']

const ide = useIdeStore()
const env = useEnvStore()
const mcp = useMcpStore()
const keys = useKeysStore()
const auth = useAuthStore()

onMounted(() => {
  ide.loadIdeDetect()
  env.loadEnv()
  mcp.loadMcpCatalog()
  mcp.loadMcpConfig()
  keys.loadKeys()
  auth.restore()
})
onBeforeUnmount(() => {})
</script>

<template>
  <div class="app-root min-h-screen">
    <Header :tab="tab" :tabs="tabs" :default-favorite-keys="defaultFavoriteKeys" @update:tab="tab = $event" />

    <main class="max-w-[1600px] w-full mx-auto px-6 py-5">
      <IdeView v-if="tab === 'ide'" />
      <LlmView v-else-if="tab === 'env'" />
      <McpView v-else-if="tab === 'mcp'" @go-tab="tab = $event" />
      <KeysView v-else-if="tab === 'keys'" />
      <SkillView v-else-if="tab === 'skill'" />
      <CommandView v-else-if="tab === 'command'" />
      <SubagentView v-else-if="tab === 'subagent'" />
      <PluginView v-else-if="tab === 'plugin'" @go-tab="tab = $event" />
      <PluginBuildView v-else-if="tab === 'plugin-build'" />
      <RulesView v-else-if="tab === 'rules'" />
      <HooksView v-else-if="tab === 'hooks'" />
      <MemoryView v-else-if="tab === 'memory'" />
      <MarketplaceView v-else-if="tab === 'marketplace'" />
      <TokenView v-else-if="tab === 'token'" />
    </main>

    <Toast />
    <Modal />
    <AppDialog />
    <AuthDialog />
    <LogPanel />
  </div>
</template>
