<script setup lang="ts">
import { ref, computed } from 'vue'
import { useIdeStore } from '../stores/ide'

const ide = useIdeStore()

interface CodingPlan {
  name: string
  vendor: string
  description: string
  url: string
  badge?: string
  price: string
  firstMonth?: string
  unit: string
  quota: string
  models: number
  modelNames: string[]
  billingType: string
  gradient: string
  promoCode?: string
  promoDiscount?: string
  highlight?: boolean
}

interface TokenMarket {
  name: string
  description: string
  url: string
  badge?: string
  features: string[]
  models: { name: string; price: string; unit: string }[]
  pricing: { free?: string; paid?: string; currency: string }
  gradient: string
  promoCode?: string
  promoDiscount?: string
  cheapestPrice?: string
  highlight?: boolean
}

// ===== Coding Plan 方案（各家厂商订阅套餐） =====
const codingPlans: CodingPlan[] = [
  {
    name: '火山方舟 Coding Plan',
    vendor: '字节跳动',
    description: 'Doubao Seed 1.5 / DeepSeek V3 / Qwen 等模型，18,000 次/月',
    url: 'https://www.volcengine.com/product/ark',
    badge: '性价比',
    price: '¥40',
    firstMonth: '¥9.4',
    unit: '/月',
    quota: '18,000 次',
    models: 10,
    modelNames: ['DeepSeek', 'Doubao', 'Qwen'],
    billingType: 'API 请求次数',
    gradient: 'from-red-500 to-orange-600',
    highlight: true,
  },
  {
    name: '火山方舟 Agent Plan',
    vendor: '字节跳动',
    description: '18 个模型 + 10+ 工具，20,000 AFP 积分/月',
    url: 'https://www.volcengine.com/product/ark',
    price: '¥40',
    firstMonth: '¥9.9',
    unit: '/月',
    quota: '20,000 AFP',
    models: 18,
    modelNames: ['DeepSeek', 'Doubao', 'Qwen', 'GLM'],
    billingType: '积分制',
    gradient: 'from-red-500 to-rose-700',
  },
  {
    name: '百炼 Coding Plan',
    vendor: '阿里云',
    description: 'Qwen 系列模型，90,000 次/月，AI 编码专属套餐',
    url: 'https://bailian.console.aliyun.com/',
    badge: '大额度',
    price: '¥200',
    unit: '/月',
    quota: '90,000 次',
    models: 9,
    modelNames: ['Qwen'],
    billingType: 'API 请求次数',
    gradient: 'from-orange-500 to-amber-600',
  },
  {
    name: '百炼 Token Plan',
    vendor: '阿里云',
    description: '22 个模型灵活切换，2,500 积分/月',
    url: 'https://bailian.console.aliyun.com/',
    price: '¥60',
    firstMonth: '¥39',
    unit: '/月',
    quota: '2,500 积分',
    models: 22,
    modelNames: ['Qwen', 'DeepSeek', 'GLM'],
    billingType: '积分制',
    gradient: 'from-amber-500 to-yellow-600',
  },
  {
    name: 'GLM Coding Plan',
    vendor: '智谱华章',
    description: 'GLM-4.6 / GLM-4-AirX 等，40,000 积分/月',
    url: 'https://open.bigmodel.cn/',
    price: '¥118',
    unit: '/月',
    quota: '40,000 积分',
    models: 3,
    modelNames: ['GLM'],
    billingType: '积分制',
    gradient: 'from-blue-500 to-cyan-600',
  },
  {
    name: 'Kimi Code Plan',
    vendor: '月之暗面',
    description: 'Kimi K3 模型，约 33M Token/月',
    url: 'https://platform.moonshot.cn/',
    price: '¥49',
    unit: '/月',
    quota: '~33M Token',
    models: 5,
    modelNames: ['Kimi'],
    billingType: 'Token 计费',
    gradient: 'from-purple-500 to-indigo-600',
  },
  {
    name: 'MiniMax Token Plan',
    vendor: 'MiniMax',
    description: '5 个模型，约 600M Token/月，额度大',
    url: 'https://platform.minimaxi.com/',
    price: '¥49',
    unit: '/月',
    quota: '~600M Token',
    models: 5,
    modelNames: ['MiniMax'],
    billingType: 'Token 计费',
    gradient: 'from-teal-500 to-green-600',
  },
  {
    name: '百度千帆 Token Plan',
    vendor: '百度',
    description: 'ERNIE 4.5 等 6 个模型，10M Token/月',
    url: 'https://qianfan.cloud.baidu.com/',
    price: '¥9.9',
    firstMonth: '¥4.9',
    unit: '/月',
    quota: '10M Token',
    models: 6,
    modelNames: ['ERNIE'],
    billingType: 'Token 计费',
    gradient: 'from-blue-600 to-indigo-700',
  },
  {
    name: '腾讯云 Hy Token Plan',
    vendor: '腾讯云',
    description: '7 个模型，35M Token/月',
    url: 'https://cloud.tencent.com/product/hy',
    price: '¥28',
    unit: '/月',
    quota: '35M Token',
    models: 7,
    modelNames: ['Hunyuan'],
    billingType: 'Token 计费',
    gradient: 'from-sky-500 to-blue-600',
  },
  {
    name: '科大讯飞 Astron Coding Plan',
    vendor: '科大讯飞',
    description: '16 个模型，18,000 次/月',
    url: 'https://xinghuo.xfyun.cn/',
    price: '¥19',
    firstMonth: '¥3.9',
    unit: '/月',
    quota: '18,000 次',
    models: 16,
    modelNames: ['Spark'],
    billingType: 'API 请求次数',
    gradient: 'from-indigo-500 to-purple-600',
  },
]

// ===== Token 中转市场（按量付费） =====
const tokenMarkets: TokenMarket[] = [
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

const copiedCode = ref('')
function copyPromoCode(code: string, e: Event) {
  e.stopPropagation()
  navigator.clipboard?.writeText(code).then(() => {
    copiedCode.value = code
    setTimeout(() => { copiedCode.value = '' }, 2000)
  })
}

const activeTab = ref<'plans' | 'markets'>('markets')

const planFilter = ref<'all' | 'cheap' | 'large'>('all')
const modelFilter = ref<string>('all')

// 所有可用模型列表（从数据中提取去重）
const allModelNames = computed(() => {
  const set = new Set<string>()
  codingPlans.forEach(p => p.modelNames.forEach(m => set.add(m)))
  markets.forEach(m => m.models.forEach(mo => {
    // 从模型名中提取厂商关键词
    const name = mo.name.toLowerCase()
    if (name.includes('deepseek')) set.add('DeepSeek')
    else if (name.includes('claude')) set.add('Claude')
    else if (name.includes('gpt') || name.includes('codex')) set.add('GPT')
    else if (name.includes('gemini')) set.add('Gemini')
    else if (name.includes('qwen')) set.add('Qwen')
    else if (name.includes('glm')) set.add('GLM')
    else if (name.includes('kimi')) set.add('Kimi')
  }))
  return Array.from(set).sort()
})

const filteredPlans = computed(() => {
  let result = codingPlans
  if (planFilter.value === 'cheap') result = result.filter(p => parseFloat(p.price.replace(/[¥$]/, '')) <= 40)
  if (planFilter.value === 'large') result = result.filter(p => p.models >= 10)
  if (modelFilter.value !== 'all') result = result.filter(p => p.modelNames.includes(modelFilter.value))
  return result
})

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
        精选 LLM API 方案：按量付费市场（按需付费，比订阅更便宜）+ Coding Plan 订阅套餐（固定额度）。
      </p>
    </div>

    <!-- Tab 切换 -->
    <div class="mb-5 flex items-center gap-2 rounded-lg border border-ink-200 bg-ink-100 p-1 w-fit">
      <button
        class="text-sm px-4 py-1.5 rounded-md font-medium transition-all"
        :class="activeTab === 'markets' ? 'bg-white text-brand-500 shadow-sm' : 'text-ink-500 hover:text-ink-700'"
        @click="activeTab = 'markets'"
      >
        按量付费市场 ⭐
      </button>
      <button
        class="text-sm px-4 py-1.5 rounded-md font-medium transition-all"
        :class="activeTab === 'plans' ? 'bg-white text-brand-500 shadow-sm' : 'text-ink-500 hover:text-ink-700'"
        @click="activeTab = 'plans'"
      >
        Coding Plan 套餐
      </button>
    </div>

    <!-- ===== Coding Plan 套餐 ===== -->
    <template v-if="activeTab === 'plans'">
      <!-- 筛选器 -->
      <div class="mb-5 flex flex-wrap items-center gap-2">
        <button
          v-for="f in [
            { v: 'all', l: '全部' },
            { v: 'cheap', l: '≤¥40/月' },
            { v: 'large', l: '10+ 模型' },
          ]"
          :key="f.v"
          class="text-xs px-3 py-1.5 rounded-full font-medium transition-all"
          :class="planFilter === f.v ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-600 hover:bg-ink-200'"
          @click="planFilter = f.v"
        >
          {{ f.l }}
        </button>
        <span class="text-ink-300 mx-1">|</span>
        <button
          class="text-xs px-3 py-1.5 rounded-full font-medium transition-all"
          :class="modelFilter === 'all' ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-600 hover:bg-ink-200'"
          @click="modelFilter = 'all'"
        >
          全部模型
        </button>
        <button
          v-for="m in allModelNames"
          :key="m"
          class="text-xs px-3 py-1.5 rounded-full font-medium transition-all"
          :class="modelFilter === m ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-600 hover:bg-ink-200'"
          @click="modelFilter = m"
        >
          {{ m }}
        </button>
      </div>

      <!-- 套餐卡片网格 -->
      <div class="grid gap-4 md:grid-cols-2">
        <div
          v-for="p in filteredPlans"
          :key="p.name"
          class="rounded-2xl overflow-hidden border bg-white hover:shadow-xl transition-all cursor-pointer"
          :class="p.highlight ? 'border-brand-300 ring-1 ring-brand-200' : 'border-ink-200'"
          @click="go(p.url)"
        >
          <!-- 顶部渐变 Banner -->
          <div class="h-20 bg-gradient-to-r relative flex items-center px-5" :class="p.gradient">
            <div class="absolute right-0 top-0 w-24 h-24 rounded-full bg-white/10 -translate-y-6 translate-x-6"></div>
            <div class="text-white relative z-10 flex-1">
              <div class="flex items-center gap-2">
                <h3 class="text-base font-bold">{{ p.name }}</h3>
                <span v-if="p.badge" class="text-[10px] px-2 py-0.5 rounded-full bg-white/20 text-white font-medium backdrop-blur-sm">
                  {{ p.badge }}
                </span>
                <span v-if="p.highlight" class="text-[10px] px-2 py-0.5 rounded-full bg-yellow-400 text-yellow-900 font-bold">
                  ⭐ 推荐
                </span>
              </div>
              <p class="text-xs text-white/80 mt-0.5">{{ p.vendor }} · {{ p.description }}</p>
            </div>
            <div class="relative z-10 text-white text-right">
              <p class="text-lg font-bold">{{ p.price }}<span class="text-xs font-normal">{{ p.unit }}</span></p>
              <p v-if="p.firstMonth" class="text-[10px] text-white/70">首月 {{ p.firstMonth }}</p>
            </div>
          </div>

          <!-- 内容区 -->
          <div class="p-4">
            <div class="grid grid-cols-3 gap-3 mb-3">
              <div class="text-center">
                <p class="text-[10px] text-ink-500 uppercase">月度额度</p>
                <p class="text-sm font-semibold text-ink-900 mt-0.5">{{ p.quota }}</p>
              </div>
              <div class="text-center border-x border-ink-100">
                <p class="text-[10px] text-ink-500 uppercase">模型数</p>
                <p class="text-sm font-semibold text-ink-900 mt-0.5">{{ p.models }} 个</p>
              </div>
              <div class="text-center">
                <p class="text-[10px] text-ink-500 uppercase">计费方式</p>
                <p class="text-sm font-semibold text-ink-900 mt-0.5">{{ p.billingType }}</p>
              </div>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-xs text-ink-500">{{ p.vendor }}</span>
              <span class="text-xs font-medium text-brand-600 flex items-center gap-1">
                前往订阅
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ===== 按量付费市场 ===== -->
    <template v-else>
      <!-- Hero 大图卡片 -->
      <div class="grid gap-5">
        <div
          v-for="m in tokenMarkets"
          :key="m.name"
          class="rounded-2xl overflow-hidden border bg-white hover:shadow-xl transition-all cursor-pointer"
          :class="m.highlight ? 'border-brand-300 ring-1 ring-brand-200' : 'border-ink-200'"
          @click="go(m.url)"
        >
          <!-- 顶部渐变 Banner -->
          <div class="h-28 bg-gradient-to-r relative flex items-center px-6" :class="m.gradient">
            <div class="absolute right-0 top-0 w-32 h-32 rounded-full bg-white/10 -translate-y-8 translate-x-8"></div>
            <div class="absolute right-12 top-4 w-20 h-20 rounded-full bg-white/5"></div>
            <div class="text-white relative z-10 flex-1">
              <div class="flex items-center gap-2">
                <h3 class="text-xl font-bold">{{ m.name }}</h3>
                <span v-if="m.badge" class="text-[10px] px-2 py-0.5 rounded-full bg-white/20 text-white font-medium backdrop-blur-sm">
                  {{ m.badge }}
                </span>
                <span v-if="m.highlight" class="text-[10px] px-2 py-0.5 rounded-full bg-yellow-400 text-yellow-900 font-bold">
                  ⭐ 推荐
                </span>
              </div>
              <p class="text-sm text-white/80 mt-0.5">{{ m.description }}</p>
            </div>
            <div class="relative z-10 text-white text-right">
              <p class="text-[11px] text-white/70 uppercase tracking-wide">最低价</p>
              <p class="text-lg font-bold">{{ m.cheapestPrice }}</p>
            </div>
          </div>

          <!-- 推广码横幅（可点击复制） -->
          <div v-if="m.promoCode" class="px-5 py-2 bg-amber-50 border-b border-amber-100 flex items-center gap-2">
            <svg class="w-4 h-4 text-amber-500 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M7 7a2 2 0 11-4 0 2 2 0 014 0zM17 17a2 2 0 11-4 0 2 2 0 014 0zM7 7h10M7 17h10" />
            </svg>
            <span class="text-xs text-amber-700 font-medium">{{ m.promoDiscount }}</span>
            <button
              class="text-xs text-amber-600 font-mono bg-amber-100 hover:bg-amber-200 px-2 py-0.5 rounded ml-auto flex items-center gap-1 transition-colors"
              @click="copyPromoCode(m.promoCode!, $event)"
            >
              <span v-if="copiedCode === m.promoCode">✓ 已复制</span>
              <template v-else>
                推广码: {{ m.promoCode }}
                <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </template>
            </button>
          </div>

          <!-- 内容区 -->
          <div class="p-5">
            <div class="mb-4">
              <p class="text-[11px] text-ink-500 uppercase tracking-wide font-medium mb-2">模型价格（从低到高）</p>
              <div class="grid grid-cols-3 gap-2">
                <div
                  v-for="model in m.models"
                  :key="model.name"
                  class="rounded-lg border px-3 py-2 text-center"
                  :class="model.price === '0' ? 'border-green-200 bg-green-50' : 'border-ink-200'"
                >
                  <p class="text-xs text-ink-600 truncate">{{ model.name }}</p>
                  <p class="text-sm font-bold mt-0.5" :class="model.price === '0' ? 'text-green-600' : 'text-ink-900'">
                    {{ model.price === '0' ? '免费' : `${m.pricing.currency}${model.price}` }}
                  </p>
                  <p class="text-[10px] text-ink-400">{{ model.unit !== '免费' ? model.unit : '' }}</p>
                </div>
              </div>
            </div>
            <div class="flex items-end justify-between">
              <div class="flex flex-wrap gap-x-3 gap-y-1">
                <span v-for="f in m.features" :key="f" class="text-[11px] flex items-center gap-1 text-ink-600">
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
    </template>

    <!-- 底部提示 -->
    <div class="mt-6 rounded-lg bg-ink-50 border border-ink-200 p-4">
      <p class="text-xs text-ink-500">
        💡 获取 Token 后，前往「LLM 配置」页面，点击「智能添加」粘贴 API Key 即可自动识别 Provider。
      </p>
    </div>
  </div>
</template>
