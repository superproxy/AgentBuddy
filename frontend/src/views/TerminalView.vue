<script setup lang="ts">
import { onMounted, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import { useTerminalStore } from '../stores/terminal'

const terminal = useTerminalStore()
const { running, terminalUrl, loading } = storeToRefs(terminal)

onMounted(() => { terminal.checkStatus() })
onBeforeUnmount(() => { /* 保留终端运行，不自动关闭 */ })
</script>

<template>
  <div class="space-y-3">
    <div class="bg-white rounded-xl shadow-card p-4">
      <div class="flex items-center justify-between mb-3 pb-2 border-b border-gray-100">
        <h3 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded"></span>终端测试
          <span v-if="running" class="text-[10px] text-green-600 font-normal">● 运行中</span>
        </h3>
        <div class="flex items-center gap-2">
          <button v-if="!running" @click="terminal.start()" :disabled="loading"
                  class="text-[11px] px-3 py-1 bg-brand-500 text-white rounded hover:bg-brand-600 disabled:opacity-50">
            {{ loading ? '启动中…' : '启动终端' }}
          </button>
          <button v-else @click="terminal.stop()"
                  class="text-[11px] px-3 py-1 bg-red-500 text-white rounded hover:bg-red-600">
            关闭终端
          </button>
        </div>
      </div>

      <!-- 终端 iframe -->
      <div v-if="running && terminalUrl" class="h-[68vh] rounded-lg overflow-hidden border border-ink-300">
        <iframe :src="terminalUrl" class="w-full h-full border-0" title="Terminal" />
      </div>

      <!-- 未启动状态 -->
      <div v-else class="h-[68vh] flex flex-col items-center justify-center text-center">
        <div class="text-4xl mb-3">🖥️</div>
        <p class="text-sm text-ink-600 mb-2">内嵌 ttyd 终端服务</p>
        <p class="text-[11px] text-ink-500 mb-4 max-w-md">
          启动后可在页面内运行 opencode、claude 等命令，直接测试插件管理效果。<br>
          终端基于 ttyd，需先安装：<code class="bg-ink-100 px-1 rounded">brew install ttyd</code>（macOS）或 <code class="bg-ink-100 px-1 rounded">winget install ttyd</code>（Windows）
        </p>
        <button @click="terminal.start()" :disabled="loading"
                class="px-4 py-2 text-sm font-medium text-white rounded-lg bg-gradient-to-r from-brand-500 to-brand-600 hover:from-brand-600 hover:to-brand-700 disabled:opacity-50 shadow-sm">
          {{ loading ? '启动中…' : '▶ 启动终端' }}
        </button>
      </div>

      <!-- 快捷提示 -->
      <div v-if="running" class="mt-2 flex flex-wrap gap-2 text-[10px] text-ink-500">
        <span class="px-2 py-1 bg-ink-100 rounded">💡 可运行：</span>
        <code class="px-2 py-1 bg-brand-50 text-brand-600 rounded">opencode</code>
        <code class="px-2 py-1 bg-brand-50 text-brand-600 rounded">claude</code>
        <code class="px-2 py-1 bg-brand-50 text-brand-600 rounded">zcode</code>
        <code class="px-2 py-1 bg-brand-50 text-brand-600 rounded">agentctl generate</code>
      </div>
    </div>
  </div>
</template>
