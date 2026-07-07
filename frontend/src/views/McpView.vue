<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useMcpStore } from '../stores/mcp'
const mcp = useMcpStore()
const { mcpTemplate, mcpConfigData, mcpTab, mcpMarketQ, mcpMarketResults, mcpSearched, mcpForm, editingMcp, editMcpForm, mcpEnabledCount } = storeToRefs(mcp)
const { searchMcpMarket, getMcpDetail, addMarketMcpToTemplate, parsePastedMcp, addManualMcp, toggleAllMcp, saveMcpAll, syncMcpFull, startEditMcp, cancelEditMcp, saveEditMcp, generateMcpRuntime, toggleMcpDisabled, deleteMcpEntry, saveMcpConfig, addMcpConfigKey, deleteMcpConfigKey } = mcp
</script>
<template>
  <div class="space-y-4">
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex items-center justify-between mb-3 pb-3 border-b border-gray-100">
        <div class="flex items-center gap-1">
          <button @click="mcpTab = 'market'" :class="['px-3 py-1 text-xs font-medium rounded-t border-b-2 -mb-px', mcpTab === 'market' ? 'border-brand-500 text-brand-600' : 'border-transparent text-ink-500 hover:text-ink-700']">市场搜索</button>
          <button @click="mcpTab = 'manual'" :class="['px-3 py-1 text-xs font-medium rounded-t border-b-2 -mb-px', mcpTab === 'manual' ? 'border-brand-500 text-brand-600' : 'border-transparent text-ink-500 hover:text-ink-700']">手动添加</button>
        </div>
        <span class="text-[10px] text-ink-500">{{ mcpTab === 'market' ? 'ModelScope 市场' : '填写表单或粘贴 Smithery 配置' }}</span>
      </div>
      <div v-show="mcpTab === 'market'">
        <div class="flex gap-2 mb-3">
          <input v-model="mcpMarketQ" @keydown.enter="searchMcpMarket" placeholder="关键词，如：地图、搜索、文件..." class="flex-1 px-3 py-1.5 text-xs border border-ink-300 rounded-md">
          <button @click="searchMcpMarket" class="px-4 py-1.5 text-xs bg-brand-500 text-white rounded-md hover:bg-brand-600">搜索</button>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div v-for="s in mcpMarketResults" :key="s.id" class="border border-ink-300 rounded-md p-3 hover:border-brand-500 hover:shadow-sm transition">
            <div class="flex justify-between items-start mb-1">
              <div class="font-medium text-sm">{{ s.name }}</div>
              <span v-if="s.is_hosted" class="px-1.5 py-0.5 text-[10px] bg-green-50 text-green-600 rounded">Hosted</span>
            </div>
            <div class="text-[11px] text-ink-500 mb-1">{{ s.id }} · {{ s.author }}</div>
            <div class="text-xs text-ink-700 line-clamp-2 mb-2">{{ s.description }}</div>
            <div class="flex gap-1">
              <button @click="getMcpDetail(s.owner, s.name)" class="px-2 py-1 text-[11px] bg-ink-100 rounded hover:bg-ink-300">查看配置</button>
              <button @click="addMarketMcpToTemplate(s.owner, s.name, s.name)" class="px-2 py-1 text-[11px] bg-brand-50 text-brand-600 rounded hover:bg-brand-100">添加到已配置</button>
            </div>
          </div>
          <div v-if="!mcpMarketResults.length && mcpSearched" class="col-span-2 text-center text-ink-500 py-6 text-xs">无结果</div>
        </div>
      </div>
      <div v-show="mcpTab === 'manual'">
        <div class="grid grid-cols-2 gap-3">
          <div class="flex items-center gap-2"><label class="text-xs text-ink-500 w-20">name *</label><input v-model="mcpForm.name" placeholder="my-mcp" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded"></div>
          <div class="flex items-center gap-2"><label class="text-xs text-ink-500 w-20">type</label>
            <select v-model="mcpForm.type" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded"><option value="">stdio（默认）</option><option value="http">http</option><option value="streamableHttp">streamableHttp</option></select>
          </div>
          <div class="flex items-center gap-2"><label class="text-xs text-ink-500 w-20">command</label><input v-model="mcpForm.command" placeholder="npx" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded"></div>
          <div class="flex items-center gap-2"><label class="text-xs text-ink-500 w-20">args</label><input v-model="mcpForm.args" placeholder="-y, @modelcontextprotocol/server-filesystem, ./" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded"></div>
          <div class="flex items-center gap-2 col-span-2"><label class="text-xs text-ink-500 w-20">url</label><input v-model="mcpForm.url" placeholder="http 类型填写" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded"></div>
          <div class="flex items-start gap-2 col-span-2"><label class="text-xs text-ink-500 w-20 mt-1.5">headers</label><textarea v-model="mcpForm.headers" rows="2" placeholder='{"Authorization":"Bearer xxx"}' class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded font-mono"></textarea></div>
          <div class="flex items-start gap-2 col-span-2"><label class="text-xs text-ink-500 w-20 mt-1.5">env</label><textarea v-model="mcpForm.env" rows="2" placeholder='{"API_KEY":"xxx"}' class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded font-mono"></textarea></div>
          <div class="flex items-start gap-2 col-span-2"><label class="text-xs text-ink-500 w-20 mt-1.5">Smithery 粘贴</label><textarea v-model="mcpForm.paste" rows="3" placeholder='粘贴完整 MCP 配置 JSON，自动解析' class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded font-mono"></textarea></div>
        </div>
        <div class="flex gap-2 mt-3">
          <button @click="parsePastedMcp" class="px-3 py-1.5 text-xs bg-ink-100 rounded hover:bg-ink-300">解析粘贴</button>
          <button @click="addManualMcp" class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded hover:bg-brand-600">添加到已配置</button>
        </div>
      </div>
    </div>
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex items-center justify-between mb-3 pb-3 border-b border-gray-100">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded"></span>已配置
          <span class="text-[10px] text-ink-500 font-normal">{{ Object.keys(mcpTemplate.mcpServers || {}).length }} 个 · 启用 {{ mcpEnabledCount }} · 密钥 {{ Object.keys(mcpConfigData.mcp || {}).length }} 个</span>
        </h2>
        <div class="flex gap-2 items-center">
          <button @click="toggleAllMcp(true)" class="px-2 py-1.5 text-[11px] bg-ink-100 rounded hover:bg-ink-300">全选</button>
          <button @click="toggleAllMcp(false)" class="px-2 py-1.5 text-[11px] bg-ink-100 rounded hover:bg-ink-300">全不选</button>
          <button @click="saveMcpAll()" class="px-2 py-1.5 text-[11px] bg-brand-500 text-white rounded hover:bg-brand-600">保存</button>
          <button @click="generateMcpRuntime" class="px-2 py-1.5 text-[11px] bg-ink-100 rounded hover:bg-ink-300">生成 mcp.json</button>
          <button @click="syncMcpFull" class="px-2 py-1.5 text-[11px] bg-brand-50 text-brand-600 rounded hover:bg-brand-100">同步到 IDE</button>
        </div>
      </div>
      <div class="space-y-2 mb-4">
        <div v-for="(cfg, name) in (mcpTemplate.mcpServers || {})" :key="name"
             :class="['border rounded-md p-2.5 transition', (cfg.disabled === true || cfg.disabled === 'true') ? 'border-ink-300 bg-ink-100/40 opacity-60' : 'border-brand-300 bg-brand-50/30']">
          <div class="flex justify-between items-center">
            <div class="flex items-center gap-2">
              <input type="checkbox" :checked="!(cfg.disabled === true || cfg.disabled === 'true')" @change="toggleMcpDisabled(name, $event.target.checked)" class="w-4 h-4 accent-brand-500 cursor-pointer">
              <div class="font-medium text-sm">{{ name }}</div>
              <span v-if="cfg.disabled === true || cfg.disabled === 'true'" class="px-1 py-0.5 text-[10px] bg-ink-200 text-ink-500 rounded">已禁用</span>
              <span v-else class="px-1 py-0.5 text-[10px] bg-green-50 text-green-600 rounded">启用</span>
            </div>
            <div class="flex items-center gap-1">
              <button @click="startEditMcp(name)" class="text-[11px] text-brand-600 hover:bg-brand-50 px-1.5 py-0.5 rounded">编辑</button>
              <button @click="deleteMcpEntry(name)" class="text-[11px] text-red-500 hover:bg-red-50 px-1.5 py-0.5 rounded">删</button>
            </div>
          </div>
          <div class="text-[11px] text-ink-500 mt-0.5">{{ cfg.command ? cfg.command + ' ' + (cfg.args||[]).join(' ') : (cfg.url || '') }}</div>
          <div v-if="editingMcp === name" class="mt-2 pt-2 border-t border-dashed border-ink-300 space-y-2">
            <div class="grid grid-cols-2 gap-2">
              <div class="flex items-center gap-1.5"><label class="text-[10px] text-ink-500 w-14">type</label><select v-model="editMcpForm.type" class="flex-1 px-1.5 py-1 text-[11px] border border-ink-300 rounded"><option value="">stdio</option><option value="http">http</option><option value="streamableHttp">streamableHttp</option></select></div>
              <div class="flex items-center gap-1.5"><label class="text-[10px] text-ink-500 w-14">command</label><input v-model="editMcpForm.command" class="flex-1 px-1.5 py-1 text-[11px] border border-ink-300 rounded"></div>
              <div class="flex items-center gap-1.5 col-span-2"><label class="text-[10px] text-ink-500 w-14">args</label><input v-model="editMcpForm.args" placeholder="逗号分隔" class="flex-1 px-1.5 py-1 text-[11px] border border-ink-300 rounded"></div>
              <div class="flex items-center gap-1.5 col-span-2"><label class="text-[10px] text-ink-500 w-14">url</label><input v-model="editMcpForm.url" class="flex-1 px-1.5 py-1 text-[11px] border border-ink-300 rounded"></div>
              <div class="flex items-start gap-1.5 col-span-2"><label class="text-[10px] text-ink-500 w-14 mt-1">headers</label><textarea v-model="editMcpForm.headers" rows="2" class="flex-1 px-1.5 py-1 text-[11px] border border-ink-300 rounded font-mono"></textarea></div>
              <div class="flex items-start gap-1.5 col-span-2"><label class="text-[10px] text-ink-500 w-14 mt-1">env</label><textarea v-model="editMcpForm.env" rows="2" class="flex-1 px-1.5 py-1 text-[11px] border border-ink-300 rounded font-mono"></textarea></div>
            </div>
            <div class="flex gap-2">
              <button @click="saveEditMcp" class="px-2.5 py-1 text-[11px] bg-brand-500 text-white rounded hover:bg-brand-600">保存</button>
              <button @click="cancelEditMcp" class="px-2.5 py-1 text-[11px] bg-ink-100 rounded hover:bg-ink-300">取消</button>
            </div>
          </div>
        </div>
        <div v-if="!Object.keys(mcpTemplate.mcpServers || {}).length" class="text-center text-ink-500 text-xs py-4">暂无已配置 MCP，可上方通过市场搜索或手动添加</div>
      </div>
      <div class="border-t border-gray-100 pt-3">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-xs font-semibold text-ink-700">密钥配置 <span class="text-[10px] text-ink-500 font-normal">mcp.yaml · mcp</span></h3>
          <div class="flex gap-2">
            <button @click="saveMcpConfig" class="px-2 py-1 text-[11px] bg-brand-500 text-white rounded hover:bg-brand-600">保存</button>
            <button @click="addMcpConfigKey" class="px-2 py-1 text-[11px] bg-brand-50 text-brand-600 rounded hover:bg-brand-100">+ 添加 Key</button>
          </div>
        </div>
        <p class="text-[11px] text-ink-500 mb-3 leading-relaxed">MCP 服务的密钥/Token，供生成 mcp.json 时替换 ${KEY} 占位符。</p>
        <div class="grid grid-cols-2 gap-3">
          <div v-for="(_, k) in (mcpConfigData.mcp || {})" :key="k" class="flex items-center gap-2 group">
            <label class="text-xs text-ink-500 w-44 truncate font-mono" :title="k">{{ k }}</label>
            <input type="password" v-model="mcpConfigData.mcp[k]" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded font-mono">
            <button @click="deleteMcpConfigKey(k)" class="opacity-0 group-hover:opacity-100 transition px-2 py-1 text-[11px] text-red-500 hover:bg-red-50 rounded">删</button>
          </div>
          <div v-if="!Object.keys(mcpConfigData.mcp || {}).length" class="col-span-2 text-center text-ink-500 text-xs py-4">暂无密钥，点击 "+ 添加 Key" 开始</div>
        </div>
      </div>
    </div>
  </div>
</template>
