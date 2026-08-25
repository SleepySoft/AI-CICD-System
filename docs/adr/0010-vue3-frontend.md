# ADR-0010 Manager 前端选 Vue3（允许 Jinja2/htmx 过渡）

> 日期：2026-08-21 · 状态：已接受
> 关联：what/manager.md §前端页面
> （本篇为文档重构时对原 docs/02 §13.4 决策的追记）

## 背景

Manager 需要中文管理后台：仪表盘、报告渲染、待审 diff 视图、SSE 实时日志。希望不引入独立前端部署。

## 决策

目标方案 **Vue 3 + Element Plus**，构建为静态文件由 FastAPI/Caddy 托管；M1-M2 允许用 FastAPI + Jinja2/htmx 出管理页过渡，接口不变，M3 切换。（当前 M1 实际落地为 Vue3 CDN SPA，与目标方案一致。）

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| React + AntD | 生态等价；Element Plus 在中文管理后台更事实标准，无切换收益 |
| 长期停留在 Jinja2/htmx | 待审 diff、SSE 日志等交互重页面用模板渲染维护成本高，仅作过渡 |

## 后果

- 正面：无独立前端服务；中文后台组件现成。
- 负面：前端构建链需进 Manager 镜像（多阶段构建解决）。
- 同步：manager/（前端静态资源）。
