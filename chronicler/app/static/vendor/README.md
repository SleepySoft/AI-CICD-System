# 前端本地化资源（vendor）

本项目前端（Vue3 + Element Plus 全局构建）不再依赖 CDN，资源随仓库分发，避免公司网络/代理导致 CDN 加载失败（曾出现登录页渲染原始 `{{ loginError }}`、图标按钮不可见但可点的问题，2026-09-01 实测）。

## 资源清单（版本钉死，来源 unpkg）

| 文件 | 来源 | License |
|------|------|---------|
| vue.global.prod.js | https://unpkg.com/vue@3.5.42/dist/vue.global.prod.js | MIT |
| element-plus.css | https://unpkg.com/element-plus@2.14.5/dist/index.css | MIT |
| element-plus.full.min.js | https://unpkg.com/element-plus@2.14.5/dist/index.full.min.js | MIT |
| icons.iife.min.js | https://unpkg.com/@element-plus/icons-vue@2.3.2/dist/index.iife.min.js | MIT |
| marked.umd.js | marked@18.0.11 package/lib/marked.umd.js（npm registry） | MIT |
| purify.min.js | dompurify@3.4.14 package/dist/purify.min.js（npm registry） | Apache-2.0/MPL-2.0 |

报告渲染链路（2026-09-05）：marked 解析 Markdown → DOMPurify 消毒 → `v-html` 输出，防 XSS。

## 刷新方式

```powershell
curl.exe -sS -L -o chronicler\app\static\vendor\vue.global.prod.js https://unpkg.com/vue@3.5.42/dist/vue.global.prod.js
curl.exe -sS -L -o chronicler\app\static\vendor\element-plus.css https://unpkg.com/element-plus@2.14.5/dist/index.css
curl.exe -sS -L -o chronicler\app\static\vendor\element-plus.full.min.js https://unpkg.com/element-plus@2.14.5/dist/index.full.min.js
curl.exe -sS -L -o chronicler\app\static\vendor\icons.iife.min.js https://unpkg.com/@element-plus/icons-vue@2.3.2/dist/index.iife.min.js
```

升级版本时同步更新本表和 `index.html` 引用（路径不变，仅内容更新）。
