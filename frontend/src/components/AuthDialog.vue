<script setup lang="ts">
import { ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const username = ref('')
const password = ref('')
const email = ref('')
const errorMsg = ref('')

// 弹窗打开时重置
watch(() => auth.dialogOpen, (open) => {
  if (open) {
    username.value = ''
    password.value = ''
    email.value = ''
    errorMsg.value = ''
  }
})

async function submit() {
  errorMsg.value = ''
  if (!username.value.trim() || !password.value) {
    errorMsg.value = '用户名和密码不能为空'
    return
  }

  if (auth.dialogMode === 'register') {
    if (password.value.length < 6) {
      errorMsg.value = '密码至少 6 位'
      return
    }
    const r = await auth.register(username.value.trim(), password.value, email.value.trim() || undefined)
    if (!r.ok) {
      errorMsg.value = r.error || '注册失败'
      return
    }
    auth.closeDialog()
  } else {
    const ok = await auth.login(username.value.trim(), password.value)
    if (!ok) {
      errorMsg.value = '用户名或密码错误'
      return
    }
    auth.closeDialog()
  }
}

function switchMode() {
  errorMsg.value = ''
  auth.dialogMode.value = auth.dialogMode.value === 'login' ? 'register' : 'login'
}
</script>

<template>
  <Teleport to="body">
    <Transition name="auth-dialog">
      <div v-if="auth.dialogOpen" class="auth-mask" @click.self="auth.closeDialog()">
        <div class="auth-panel" role="dialog" aria-modal="true">
          <!-- 标题 -->
          <div class="auth-title">{{ auth.dialogMode === 'login' ? '登录' : '注册' }}</div>
          <div class="auth-sub">
            {{ auth.dialogMode === 'login' ? '登录后可发布插件、管理团队空间' : '注册后即可发布插件、创建团队空间' }}
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMsg" class="auth-error">{{ errorMsg }}</div>

          <!-- 表单 -->
          <div class="auth-field">
            <label class="auth-label">用户名</label>
            <input
              v-model="username"
              class="auth-input"
              type="text"
              placeholder="输入用户名"
              @keydown.enter="submit"
            />
          </div>
          <div class="auth-field">
            <label class="auth-label">密码</label>
            <input
              v-model="password"
              class="auth-input"
              type="password"
              :placeholder="auth.dialogMode === 'register' ? '至少 6 位' : '输入密码'"
              @keydown.enter="submit"
            />
          </div>
          <div v-if="auth.dialogMode === 'register'" class="auth-field">
            <label class="auth-label">邮箱（可选）</label>
            <input
              v-model="email"
              class="auth-input"
              type="email"
              placeholder="用于找回密码"
              @keydown.enter="submit"
            />
          </div>

          <!-- 提交按钮 -->
          <button
            class="auth-btn"
            :disabled="auth.loading"
            @click="submit"
          >
            {{ auth.loading ? '...' : (auth.dialogMode === 'login' ? '登录' : '注册') }}
          </button>

          <!-- 切换登录/注册 -->
          <div class="auth-switch">
            {{ auth.dialogMode === 'login' ? '还没有账号？' : '已有账号？' }}
            <a @click="switchMode">{{ auth.dialogMode === 'login' ? '立即注册' : '返回登录' }}</a>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.auth-mask {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.35);
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(2px);
}

.auth-panel {
  background: var(--bg-base, #fff);
  border: 1px solid var(--border-base, #e5e7eb);
  border-radius: 16px;
  padding: 28px;
  width: 360px;
  max-width: 90vw;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.1);
}

.auth-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary, #111827);
  margin-bottom: 4px;
}

.auth-sub {
  font-size: 13px;
  color: var(--text-tertiary, #9ca3af);
  margin-bottom: 20px;
}

.auth-error {
  font-size: 12px;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}

.auth-field {
  margin-bottom: 14px;
}

.auth-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #4b5563);
  margin-bottom: 4px;
}

.auth-input {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--border-strong, #d1d5db);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-base, #fff);
  color: var(--text-primary, #111827);
  transition: border-color 0.15s;
}
.auth-input:focus {
  outline: none;
  border-color: var(--brand-500, #6366f1);
}

.auth-btn {
  width: 100%;
  padding: 10px;
  border-radius: 8px;
  border: none;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 6px;
  background: var(--brand-500, #6366f1);
  color: white;
  transition: background 0.15s;
}
.auth-btn:hover:not(:disabled) {
  background: var(--brand-600, #4f46e5);
}
.auth-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auth-switch {
  text-align: center;
  font-size: 12px;
  color: var(--text-tertiary, #9ca3af);
  margin-top: 14px;
}
.auth-switch a {
  color: var(--brand-500, #6366f1);
  cursor: pointer;
}
.auth-switch a:hover {
  text-decoration: underline;
}

/* Transition */
.auth-dialog-enter-active,
.auth-dialog-leave-active {
  transition: opacity 0.2s;
}
.auth-dialog-enter-active .auth-panel,
.auth-dialog-leave-active .auth-panel {
  transition: transform 0.2s, opacity 0.2s;
}
.auth-dialog-enter-from,
.auth-dialog-leave-to {
  opacity: 0;
}
.auth-dialog-enter-from .auth-panel,
.auth-dialog-leave-to .auth-panel {
  transform: scale(0.95) translateY(-10px);
}
</style>
