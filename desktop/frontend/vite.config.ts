import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// Vite 配置：
// - base: './' 相对路径，Flask 静态托管 + pywebview 加载 dist/index.html 兼容
// - outDir: 产物输出到 desktop/dist-ui，被 PyInstaller collect_dir('desktop') 自动打包
// - dev proxy: /api + /static 转发到 Flask(5050)，开发时前端跑 19527
export default defineConfig({
  base: './',
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: '../dist-ui',
    emptyOutDir: true,
    // 产物用相对路径加载资源（配合 base: './'）
    assetsDir: 'assets',
  },
  server: {
    port: 19527,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5050',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:5050',
        changeOrigin: true,
      },
    },
  },
})
