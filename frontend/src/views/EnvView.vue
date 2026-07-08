<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useEnvStore } from '../stores/env'
const env = useEnvStore()
const { envData, envDataText, openedProviders, providerNames, proxyEnabled } = storeToRefs(env)
const { toggleProvider, updateEnvDataSection, addProvider, deleteProvider, setActiveProvider, addProtocol, deleteProtocol, addModel, deleteModel, renameModel, saveEnv, generateProxyConfig, startProxyServer, verifyLlm } = env
</script>
<template>
  <div class="space-y-4">
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex items-center justify-between mb-4 pb-3 border-b border-gray-100">
        <h2 class="text-sm font-semibold flex items-center gap-2"><span class="w-1 h-4 bg-brand-500 rounded"></span>LLM Providers <span class="text-[10px] text-ink-500 font-normal">llm.yaml</span></h2>
        <div class="flex gap-2 items-center">
          <button @click="addProvider" class="px-3 py-1.5 text-xs bg-brand-50 text-brand-600 rounded-md hover:bg-brand-100 font-medium">+ 添加 Provider</button>
          <button @click="saveEnv()" class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded-md hover:bg-brand-600 font-medium">保存</button>
        </div>
      </div>
      <div class="grid grid-cols-2 gap-3 mb-4">
        <div class="flex items-center gap-2">
          <label class="text-xs text-ink-500 w-32">Active Provider</label>
          <select v-model="envData.llm._active_provider" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded-md">
            <option v-for="p in providerNames" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>
        <div class="flex items-center gap-2">
          <label class="text-xs text-ink-500 w-32">Active Protocol</label>
          <input v-model="envData.llm._active_protocol" placeholder="openai|anthropic" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded-md">
        </div>
      </div>
      <div class="space-y-2">
        <div v-for="pn in providerNames" :key="pn" class="border border-ink-300 rounded-lg overflow-hidden hover:border-brand-500 transition">
          <div @click="toggleProvider(pn)" class="px-3 py-2 bg-ink-100 flex items-center justify-between cursor-pointer hover:bg-gray-200/60">
            <div class="flex items-center gap-2">
              <span class="text-xs text-ink-500">{{ openedProviders.has(pn) ? '▼' : '▶' }}</span>
              <span class="font-medium text-sm">{{ pn }}</span>
              <span v-if="envData.llm._active_provider === pn" class="px-1.5 py-0.5 text-[10px] bg-brand-50 text-brand-600 rounded">active</span>
            </div>
            <div class="flex gap-1">
              <button @click.stop="setActiveProvider(pn)" class="px-2 py-1 text-[11px] text-brand-600 hover:bg-brand-50 rounded">设为 Active</button>
              <button @click.stop="deleteProvider(pn)" class="px-2 py-1 text-[11px] text-red-500 hover:bg-red-50 rounded">删除</button>
            </div>
          </div>
          <div v-show="openedProviders.has(pn)" class="p-3 space-y-3">
            <template v-for="(pc, proto) in envData.llm[pn]" :key="proto">
              <div v-if="typeof pc === 'object' && pc !== null" class="bg-gray-50 border border-gray-200 rounded-md p-3">
                <div class="flex justify-between items-center mb-2">
                  <h4 class="text-[11px] font-semibold text-ink-700 uppercase">{{ proto }}</h4>
                  <button @click="deleteProtocol(pn, proto)" class="px-2 py-1 text-[11px] text-red-500 hover:bg-red-50 rounded">删除协议</button>
                </div>
                <div class="grid grid-cols-2 gap-2 mb-2">
                  <div class="flex items-center gap-2"><label class="text-[11px] text-ink-500 w-16">base_url</label><input v-model="pc.base_url" class="flex-1 px-2 py-1 text-xs border border-ink-300 rounded"></div>
                  <div class="flex items-center gap-2"><label class="text-[11px] text-ink-500 w-16">api_key</label><input type="password" v-model="pc.api_key" class="flex-1 px-2 py-1 text-xs border border-ink-300 rounded"></div>
                </div>
                <table class="w-full text-xs border-collapse">
                  <thead><tr class="bg-ink-100"><th class="border border-ink-300 px-2 py-1 text-left">key</th><th class="border border-ink-300 px-2 py-1 text-left">name</th><th class="border border-ink-300 px-2 py-1 w-12"></th></tr></thead>
                  <tbody>
                    <tr v-for="(mv, mk) in (pc.models || {})" :key="mk">
                      <td class="border border-ink-300"><input :value="mk" @change="renameModel(pn, proto, mk, $event.target.value)" class="w-full px-2 py-1 border-0"></td>
                      <td class="border border-ink-300"><input v-model="mv.name" class="w-full px-2 py-1 border-0"></td>
                      <td class="border border-ink-300 text-center"><button @click="deleteModel(pn, proto, mk)" class="text-red-500 text-[11px]">删</button></td>
                    </tr>
                  </tbody>
                </table>
                <button @click="addModel(pn, proto)" class="mt-1.5 text-[11px] text-brand-600 hover:underline">+ 添加 model</button>
                <button @click="verifyLlm(pn, proto)" class="mt-1.5 ml-2 text-[11px] text-green-600 hover:underline">验证 key + 获取模型</button>
              </div>
            </template>
            <button @click="addProtocol(pn)" class="text-[11px] text-brand-600 hover:underline">+ 添加协议</button>
          </div>
        </div>
      </div>
    </div>
    <!-- Proxy -->
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex items-center justify-between mb-3 pb-3 border-b border-gray-100">
        <h2 class="text-sm font-semibold flex items-center gap-2"><span class="w-1 h-4 bg-brand-500 rounded"></span>Proxy</h2>
        <div class="flex gap-2">
          <button @click="generateProxyConfig" class="px-3 py-1.5 text-xs bg-ink-100 text-ink-700 rounded-md hover:bg-ink-300">生成 proxy/config.yaml</button>
          <button @click="startProxyServer" :disabled="!proxyEnabled" :class="['px-3 py-1.5 text-xs rounded-md font-medium', proxyEnabled ? 'bg-brand-500 text-white hover:bg-brand-600' : 'bg-ink-300 text-ink-500 cursor-not-allowed']">启动代理服务</button>
        </div>
      </div>
      <p class="text-[11px] text-ink-500 mb-3 leading-relaxed">代理模式：IDE → proxy(127.0.0.1:4000) → 真实 provider。开启后 init-env.py 会用 proxy 地址覆盖 LLM_ACTIVE_BASE_URL/API_KEY，并自动生成 proxy/config.yaml。</p>
      <div class="grid grid-cols-2 gap-3">
        <div class="flex items-center gap-2">
          <label class="text-xs text-ink-500 w-24">enable</label>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="envData.proxy.enable" class="sr-only peer">
            <div class="w-9 h-5 bg-ink-300 rounded-full peer-checked:bg-green-500 transition relative">
              <div class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition" :class="{'translate-x-4': envData.proxy && envData.proxy.enable}"></div>
            </div>
          </label>
          <span :class="['text-xs', envData.proxy && envData.proxy.enable ? 'text-green-600' : 'text-ink-500']">{{ envData.proxy && envData.proxy.enable ? '已开启' : '已关闭' }}</span>
        </div>
        <div></div>
        <div class="flex items-center gap-2">
          <label class="text-xs text-ink-500 w-24">base_url</label>
          <input v-model="envData.proxy.base_url" :disabled="!envData.proxy || !envData.proxy.enable" placeholder="http://127.0.0.1:4000/v1" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded">
        </div>
        <div class="flex items-center gap-2">
          <label class="text-xs text-ink-500 w-24">api_key</label>
          <input type="password" v-model="envData.proxy.api_key" :disabled="!envData.proxy || !envData.proxy.enable" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded">
        </div>
        <div class="flex items-center gap-2 col-span-2">
          <label class="text-xs text-ink-500 w-24">启动命令</label>
          <input v-model="envData.proxy.start_cmd" placeholder="litellm --config proxy/config.yaml --port 4000" class="flex-1 px-2 py-1.5 text-xs border border-ink-300 rounded font-mono">
        </div>
      </div>
    </div>
    <!-- 其他配置 -->
    <div class="bg-white rounded-xl shadow-card p-5">
      <h2 class="text-sm font-semibold flex items-center gap-2 mb-3 pb-3 border-b border-gray-100"><span class="w-1 h-4 bg-brand-500 rounded"></span>Embedding / TTS / ASR / Vision / Misc</h2>
      <div class="space-y-3">
        <div v-for="sec in ['embedding','tts','asr','vision','misc']" :key="sec" class="border border-gray-200 rounded-md p-3">
          <h4 class="text-[11px] font-semibold text-ink-700 uppercase mb-2">{{ sec }}</h4>
          <textarea v-model="envDataText[sec]" @input="updateEnvDataSection(sec)" rows="6" class="w-full px-2 py-1 text-[11px] border border-ink-300 rounded font-mono bg-gray-50"></textarea>
        </div>
      </div>
    </div>
  </div>
</template>
