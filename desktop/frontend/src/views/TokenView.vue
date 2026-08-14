<script setup lang="ts">
import { ref } from 'vue'
import { openExternal } from '../stores/ide'

interface TokenChannel {
  name: string
  description: string
  url: string
  badge?: string
  features: string[]
}

const channels: TokenChannel[] = [
  {
    name: 'TeamOrouter',
    description: '免费白嫖 DeepSeek V4 + Codex 的宝藏入口',
    url: 'https://teamorouter.com/?i=e1c028955e',
    badge: '推荐',
    features: [
      'DeepSeek V4 模型免费用',
      'Codex（GPT-5.5）免费用',
      '无需信用卡，注册即用',
      '支持 OpenAI 兼容 API',
    ],
  },
]

function go(url: string) {
  openExternal(url)
}
</script>

<template>
  <div class="max-w-4xl mx-auto py-6">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-ink-900">Token 购买渠道</h1>
      <p class="text-sm text-ink-600 mt-1">
        以下渠道可用于获取 LLM API Token，配置到「LLM 配置」页面即可使用。
      </p>
    </div>

    <div class="grid gap-4">
      <div
        v-for="ch in channels"
        :key="ch.name"
        class="rounded-xl border border-ink-200 bg-white p-5 hover:border-brand-400 hover:shadow-md transition-all cursor-pointer"
        @click="go(ch.url)"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <h3 class="text-lg font-semibold text-ink-900">{{ ch.name }}</h3>
              <span
                v-if="ch.badge"
                class="text-[10px] px-2 py-0.5 rounded-full bg-brand-500 text-white font-medium"
              >
                {{ ch.badge }}
              </span>
            </div>
            <p class="text-sm text-ink-600 mt-1">{{ ch.description }}</p>
          </div>
          <svg
            class="w-5 h-5 text-ink-400 flex-shrink-0 mt-1"
            fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </div>

        <div class="mt-3 flex flex-wrap gap-2">
          <span
            v-for="f in ch.features"
            :key="f"
            class="text-[11px] px-2 py-1 rounded-md bg-ink-50 text-ink-600"
          >
            {{ f }}
          </span>
        </div>
      </div>
    </div>

    <div class="mt-6 rounded-lg bg-ink-50 border border-ink-200 p-4">
      <p class="text-xs text-ink-500">
        💡 获取 Token 后，前往「LLM 配置」页面，点击「智能添加」粘贴 API Key 即可自动识别 Provider。
      </p>
    </div>
  </div>
</template>
