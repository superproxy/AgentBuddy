<script setup lang="ts">
import { ref, computed } from 'vue'
import { useIdeStore } from '../stores/ide'

const ide = useIdeStore()

interface TokenMarket {
  name: string
  description: string
  url: string
  badge?: string
  features: string[]
  models: { name: string; price: string; unit: string }[]
  pricing: {
    free?: string
    paid?: string
    currency: string
  }
  highlight?: boolean
  gradient: string
  promoCode?: string
  promoDiscount?: string
  cheapestPrice?: string
}

const markets: TokenMarket[] = [
  {
    name: 'TeamOrouter',
    description: '免费白嫖 DeepSeek V4 + Codex 的宝藏入口',
    url: 'https://teamorouter.com/?i=e1c028955e',
    badge: '免费',
    highlight: true,
    gradient: 'from-green-500 to-emerald-700',
    promoCode: 'e1c028955e',
    promoDiscount: '专属推广码已内置',
    cheapestPrice: '¥0',
    features: [
      'DeepSeek V4 模型免费用',
      'Codex（GPT-5.5）免费用',
      '无需信用卡，注册即用',
      '支持 OpenAI 兼容 API',
    ],
    models: [
      { name: 'DeepSeek V4', price: '0', unit: '免费' },
      { name: 'Codex GPT-5.5', price: '0', unit: '免费' },
    ],
    pricing: { free: '全部免费', currency: '¥' },
  },
  {
    name: '硅基流动',
    description: '国内最便宜的 DeepSeek API，新用户送 ¥14 额度',
    url: 'https://cloud.siliconflow.cn/i/e1c028955e',
    badge: '最便宜',
    highlight: true,
    gradient: 'from-orange-500 to-red-600',
    promoCode: 'e1c028955e',
    promoDiscount: '新用户送 ¥14 + 推广返佣',
    cheapestPrice: '¥1/1M',
    features: [
      'DeepSeek V3 仅 ¥1/1M tokens（全网最低）',
      'DeepSeek R1 仅 ¥4/1M tokens',
      'Qwen / GLM / Yi 等国产模型',
      '国内直连，延迟低，人民币支付',
    ],
    models: [
      { name: 'DeepSeek V3', price: '1', unit: '/1M tokens' },
      { name: 'DeepSeek R1', price: '4', unit: '/1M tokens' },
      { name: 'Qwen2.5-72B', price: '4.13', unit: '/1M tokens' },
    ],
    pricing: { paid: '按量付费', currency: '¥' },
  },
  {
    name: 'OpenRouter',
    description: '全球最大 LLM API 聚合平台，一个 Key 访问 300+ 模型',
    url: 'https://openrouter.ai/',
    badge: '聚合',
    gradient: 'from-blue-500 to-indigo-700',
    cheapestPrice: '$0.27/1M',
    features: [
      '300+ 模型统一 API',
      '按量付费，无月费',
      '支持 Claude / GPT / Gemini / Llama',
      '自带负载均衡和故障转移',
    ],
    models: [
      { name: 'DeepSeek V3', price: '0.27', unit: '/1M tokens' },
      { name: 'GPT-4o', price: '2.5', unit: '/1M tokens' },
      { name: 'Claude Sonnet 4.5', price: '3', unit: '/1M tokens' },
    ],
    pricing: { paid: '按量付费', currency: '$' },
  },
  {
    name: 'AiHubMix',
    description: 'Claude / GPT / Gemini 官方模型中转，OpenAI 兼容 API',
    url: 'https://aihubmix.com/',
    badge: '中转',
    gradient: 'from-purple-500 to-pink-600',
    cheapestPrice: '¥12.5/1M',
    features: [
      'Claude / GPT / Gemini 官方模型',
      'OpenAI 兼容 API 格式',
      '支持流式输出',
      '稳定可靠，SLA 99.9%',
    ],
    models: [
      { name: 'Gemini 2.5 Pro', price: '12.5', unit: '/1M tokens' },
      { name: 'GPT-4o', price: '18', unit: '/1M tokens' },
      { name: 'Claude Sonnet 4.5', price: '21', unit: '/1M tokens' },
    ],
    pricing: { paid: '按量付费', currency: '¥' },
  },
]

function go(url: string) {
  ide.openExternal(url)
}

const filterMode = ref<'all' | 'free' | 'paid'>('all')
const filteredMarkets = computed(() => {
  if (filterMode.value === 'free') return markets.filter(m => m.pricing.free)
  if (filterMode.value === 'paid') return markets.filter(m => m.pricing.paid)
  return markets
})
</script>

<template>
  <div class="max-w-5xl mx-auto py-6">
    <!-- 标题区 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-ink-900">Token 市场</h1>
      <p class="text-sm text-ink-600 mt-1">
        精选 LLM API Token 渠道，按价格从低到高排列，推广码已内置到链接中。
      </p>
    </div>

    <!-- 筛选器 -->
    <div class="mb-5 flex items-center gap-2">
      <button
        v-for="f in [
          { v: 'all', l: '全部' },
          { v: 'free', l: '免费' },
          { v: 'paid', l: '付费' },
        ]"
        :key="f.v"
        class="text-xs px-3 py-1.5 rounded-full font-medium transition-all"
        :class="filterMode === f.v
          ? 'bg-brand-500 text-white'
          : 'bg-ink-100 text-ink-600 hover:bg-ink-200'"
        @click="filterMode = f.v"
      >
        {{ f.l }}
      </button>
    </div>

    <!-- Hero 大图卡片 -->
    <div class="grid gap-5">
      <div
        v-for="m in filteredMarkets"
        :key="m.name"
        class="rounded-2xl overflow-hidden border bg-white hover:shadow-xl transition-all cursor-pointer"
        :class="m.highlight ? 'border-brand-300 ring-1 ring-brand-200' : 'border-ink-200'"
        @click="go(m.url)"
      >
        <!-- 顶部渐变 Banner -->
        <div
          class="h-28 bg-gradient-to-r relative flex items-center px-6"
          :class="m.gradient"
        >
          <div class="absolute right-0 top-0 w-32 h-32 rounded-full bg-white/10 -translate-y-8 translate-x-8"></div>
          <div class="absolute right-12 top-4 w-20 h-20 rounded-full bg-white/5"></div>

          <div class="text-white relative z-10 flex-1">
            <div class="flex items-center gap-2">
              <h3 class="text-xl font-bold">{{ m.name }}</h3>
              <span
                v-if="m.badge"
                class="text-[10px] px-2 py-0.5 rounded-full bg-white/20 text-white font-medium backdrop-blur-sm"
              >
                {{ m.badge }}
              </span>
              <span
                v-if="m.highlight"
                class="text-[10px] px-2 py-0.5 rounded-full bg-yellow-400 text-yellow-900 font-bold"
              >
                ⭐ 推荐
              </span>
            </div>
            <p class="text-sm text-white/80 mt-0.5">{{ m.description }}</p>
          </div>

          <!-- 右侧最低价 -->
          <div class="relative z-10 text-white text-right">
            <p class="text-[11px] text-white/70 uppercase tracking-wide">最低价</p>
            <p class="text-lg font-bold">{{ m.cheapestPrice }}</p>
          </div>
        </div>

        <!-- 推广码横幅 -->
        <div
          v-if="m.promoCode"
          class="px-5 py-2 bg-amber-50 border-b border-amber-100 flex items-center gap-2"
        >
          <svg class="w-4 h-4 text-amber-500 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7 7a2 2 0 11-4 0 2 2 0 014 0zM17 17a2 2 0 11-4 0 2 2 0 014 0zM7 7h10M7 17h10" />
          </svg>
          <span class="text-xs text-amber-700 font-medium">{{ m.promoDiscount }}</span>
          <span class="text-xs text-amber-600 font-mono bg-amber-100 px-2 py-0.5 rounded ml-auto">
            推广码: {{ m.promoCode }}
          </span>
        </div>

        <!-- 内容区 -->
        <div class="p-5">
          <!-- 模型价格表 -->
          <div class="mb-4">
            <p class="text-[11px] text-ink-500 uppercase tracking-wide font-medium mb-2">模型价格（从低到高）</p>
            <div class="grid grid-cols-3 gap-2">
              <div
                v-for="model in m.models"
                :key="model.name"
                class="rounded-lg border px-3 py-2 text-center"
                :class="model.price === '0'
                  ? 'border-green-200 bg-green-50'
                  : 'border-ink-200'"
              >
                <p class="text-xs text-ink-600 truncate">{{ model.name }}</p>
                <p class="text-sm font-bold mt-0.5" :class="model.price === '0' ? 'text-green-600' : 'text-ink-900'">
                  {{ model.price === '0' ? '免费' : `${m.pricing.currency}${model.price}` }}
                </p>
                <p class="text-[10px] text-ink-400">{{ model.unit !== '免费' ? model.unit : '' }}</p>
              </div>
            </div>
          </div>

          <!-- 特性 + 前往按钮 -->
          <div class="flex items-end justify-between">
            <div class="flex flex-wrap gap-x-3 gap-y-1">
              <span
                v-for="f in m.features"
                :key="f"
                class="text-[11px] flex items-center gap-1 text-ink-600"
              >
                <svg class="w-3 h-3 text-brand-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clip-rule="evenodd" />
                </svg>
                {{ f }}
              </span>
            </div>
            <span class="text-sm font-medium text-brand-600 flex items-center gap-1 flex-shrink-0 ml-4">
              前往购买
              <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部提示 -->
    <div class="mt-6 rounded-lg bg-ink-50 border border-ink-200 p-4">
      <p class="text-xs text-ink-500">
        💡 获取 Token 后，前往「LLM 配置」页面，点击「智能添加」粘贴 API Key 即可自动识别 Provider。
      </p>
    </div>
  </div>
</template>
