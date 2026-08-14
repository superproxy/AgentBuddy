<script setup lang="ts">
import { useUiStore } from '../stores/ui'
const ui = useUiStore()
</script>

<template>
  <!-- 挂到 body，避免被「添加 MCP」等 fixed 面板（z-60）盖住 -->
  <Teleport to="body">
    <div
      v-if="ui.modalVisible"
      class="ui-modal-root"
      role="dialog"
      aria-modal="true"
      @click.self="ui.modalVisible = false"
    >
      <div class="ui-modal-panel">
        <h3 class="ui-modal-title">{{ ui.modalTitle }}</h3>
        <pre class="ui-modal-pre">{{ ui.modalContent }}</pre>
        <div class="ui-modal-actions">
          <button type="button" class="ui-modal-close" @click="ui.modalVisible = false">
            关闭
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ui-modal-root {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
}
.ui-modal-panel {
  background: var(--bg-elevated);
  border-radius: 8px;
  padding: 20px;
  width: 80%;
  max-width: 700px;
  max-height: 80vh;
  overflow: auto;
  box-shadow: 0 24px 64px rgba(15, 20, 30, 0.22);
}
.ui-modal-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.ui-modal-pre {
  margin: 0;
  background: #1d2129;
  color: #e5e6eb;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.ui-modal-actions {
  margin-top: 12px;
  text-align: right;
}
.ui-modal-close {
  padding: 6px 12px;
  font-size: 12px;
  border-radius: 6px;
  border: none;
  background: var(--bg-sunken);
  color: var(--text-primary);
  cursor: pointer;
}
.ui-modal-close:hover {
  background: #e5e6eb;
}
</style>
