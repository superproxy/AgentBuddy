<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useCmdStore } from '../stores/cmd'
const cmd = useCmdStore()
const { cmdData } = storeToRefs(cmd)
const { loadCmd, saveCmd, addCmd, deleteCmd, exportCmd, importCmd } = cmd
const inputRef = ref<HTMLInputElement | null>(null)
async function onImport(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  const content = await f.text()
  ;(e.target as HTMLInputElement).value = ''
  await importCmd(content)
}
onMounted(() => { loadCmd() })
</script>
<template>
  <div class="space-y-4">
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex items-center justify-between mb-3 pb-3 border-b border-gray-100">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded"></span>自定义命令
          <span class="text-[10px] text-ink-500 font-normal">cmd.yaml · {{ cmdData.commands.length }} 条</span>
        </h2>
        <div class="flex gap-2">
          <button @click="addCmd" class="px-3 py-1.5 text-xs bg-brand-50 text-brand-600 rounded-md hover:bg-brand-100 font-medium">+ 添加</button>
          <button @click="saveCmd()" class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded-md hover:bg-brand-600 font-medium">保存</button>
          <button @click="exportCmd" class="px-3 py-1.5 text-xs text-ink-600 hover:text-brand-600">导出</button>
          <button @click="inputRef?.click()" class="px-3 py-1.5 text-xs text-brand-600 hover:underline">导入</button>
          <input ref="inputRef" type="file" accept=".yaml,.yml" @change="onImport" class="hidden">
        </div>
      </div>
      <div class="space-y-2">
        <div v-for="(c, i) in cmdData.commands" :key="i" class="border border-ink-300 rounded-md p-3">
          <div class="grid grid-cols-2 gap-2 mb-2">
            <input v-model="c.name" placeholder="命令名（如 commit）" class="px-2 py-1 text-xs border border-ink-300 rounded font-mono">
            <input v-model="c.description" placeholder="描述（如 提交代码变更）" class="px-2 py-1 text-xs border border-ink-300 rounded">
          </div>
          <textarea v-model="c.prompt" rows="3" placeholder="命令 prompt（AI 执行的提示词）" class="w-full px-2 py-1 text-xs border border-ink-300 rounded font-mono"></textarea>
          <div class="text-right mt-1">
            <button @click="deleteCmd(i)" class="px-2 py-1 text-xs text-red-500 bg-red-50 rounded hover:bg-red-100">删除</button>
          </div>
        </div>
        <div v-if="!cmdData.commands.length" class="text-center text-ink-500 text-xs py-6">暂无命令，点击 "+ 添加" 创建</div>
      </div>
    </div>
  </div>
</template>
