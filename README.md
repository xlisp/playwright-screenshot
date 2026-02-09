# Playwright Screenshot

网页截图 REST API 服务，集成 GitHub API、HashiCorp Vault 密钥管理、Kubernetes 部署，以及持久化 PVC 归档存储。

---

## 目录

- [项目概览](#项目概览)
- [架构](#架构)
- [快速开始](#快速开始)
  - [本地运行](#本地运行)
  - [Docker 运行](#docker-运行)
- [API 参考](#api-参考)
  - [截图接口](#截图接口)
  - [GitHub 接口](#github-接口)
  - [归档接口](#归档接口)
  - [Vault 接口](#vault-接口)
  - [健康检查](#健康检查)
- [Secret 管理（Vault 集成）](#secret-管理vault-集成)
  - [Token 获取优先级](#token-获取优先级)
  - [本地开发配置](#本地开发配置)
  - [Vault 服务端配置](#vault-服务端配置)
- [Kubernetes 部署](#kubernetes-部署)
  - [存储架构](#存储架构)
  - [三种部署方式](#三种部署方式)
  - [部署命令](#部署命令)
  - [验证部署](#验证部署)
- [归档存储（PVC）](#归档存储pvc)
  - [目录结构](#目录结构)
  - [工作原理](#工作原理)
  - [运维操作](#运维操作)
- [项目文件结构](#项目文件结构)
- [环境变量](#环境变量)
- [命令行工具](#命令行工具)

---

## 项目概览

本项目提供一个基于 Playwright + Chromium 的网页截图服务，并扩展了以下功能：

- **网页截图**：对任意 URL 进行全页面或视口截图，支持自定义分辨率、等待时间、输出格式
- **GitHub 用户展示页**：调用 GitHub API 获取用户信息、仓库、活动，生成深色主题 HTML 展示页并截图
- **Vault 密钥管理**：GitHub Token 通过 HashiCorp Vault（K8s Auth）安全注入 Pod，支持多种后备方案
- **持久化归档**：所有生成的 HTML、PNG、JSON 自动归档到 PVC 持久卷，发布、重启、滚动更新均不丢失数据

---

## 架构

```
                         ┌──────────────────────────────┐
                         │       Nginx (反向代理)        │
                         │       Port 80 → 8080         │
                         └──────────┬───────────────────┘
                                    │
                         ┌──────────▼───────────────────┐
                         │   Flask API (api.py)          │
                         │   Port 8080                   │
                         │                               │
                         │  ┌─────────┐  ┌────────────┐ │
                         │  │截图引擎  │  │GitHub API  │ │
                         │  │Playwright│  │客户端      │ │
                         │  └─────────┘  └──────┬─────┘ │
                         │                      │       │
                         │  ┌───────────────────▼─────┐ │
                         │  │  Vault Secret Manager   │ │
                         │  │  Token 优先级:           │ │
                         │  │  File → API → Env → Local│ │
                         │  └─────────────────────────┘ │
                         └──────┬──────────┬────────────┘
                                │          │
              ┌─────────────────▼┐    ┌────▼────────────────┐
              │  /app/screenshots │    │  /app/archive (PVC) │
              │  emptyDir (临时)  │    │  持久化存储          │
              │  Pod重启即清空    │    │  发布/重启不丢失      │
              └──────────────────┘    └─────────────────────┘
```

---

## 快速开始

### 本地运行

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 设置 GitHub Token（可选，不设则匿名访问，限 60 次/小时）
export GITHUB_TOKEN=ghp_your_token_here

# 启动服务
python api.py
```

服务启动在 `http://localhost:8080`。

### Docker 运行

```bash
docker build -t playwright-screenshot .
docker run -p 8080:8080 \
  -e GITHUB_TOKEN=ghp_your_token \
  -v $(pwd)/archive:/app/archive \
  playwright-screenshot
```

挂载 `-v $(pwd)/archive:/app/archive` 确保归档数据在容器重建后保留。

---

## API 参考

### 截图接口

#### `POST /screenshot` — 对任意 URL 截图

```bash
curl -X POST http://localhost:8080/screenshot \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://github.com/octocat",
    "width": 1920,
    "height": 1080,
    "full_page": true,
    "wait_time": 3000,
    "timeout": 60000,
    "format": "png"
  }'
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | string | 必填 | 目标网页 URL |
| `width` | int | 1920 | 视口宽度 (320–3840) |
| `height` | int | 1080 | 视口高度 (240–2160) |
| `full_page` | bool | true | 是否全页面截图 |
| `wait_time` | int | 3000 | 页面加载后等待时间 (ms) |
| `timeout` | int | 60000 | 导航超时 (ms) |
| `format` | string | png | 输出格式 (png / jpeg) |

#### `GET /screenshots` — 列出所有截图

```bash
curl http://localhost:8080/screenshots
```

#### `GET /screenshots/<filename>` — 下载截图

```bash
curl -O http://localhost:8080/screenshots/screenshot_20260209_150000_abc12345_def456.png
```

#### `DELETE /screenshots/<filename>` — 删除截图

```bash
curl -X DELETE http://localhost:8080/screenshots/screenshot_xxx.png
```

---

### GitHub 接口

#### `GET /github/<username>` — 获取用户资料

```bash
curl http://localhost:8080/github/octocat
```

返回：login、name、avatar_url、bio、公开仓库数、粉丝数等。

#### `GET /github/<username>/repos` — 获取仓库列表

```bash
curl "http://localhost:8080/github/octocat/repos?sort=stars&per_page=10"
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `sort` | updated | 排序方式 (created / updated / pushed / full_name) |
| `per_page` | 30 | 每页数量 (最大 100) |
| `page` | 1 | 页码 |

#### `GET /github/<username>/page` — 生成 HTML 展示页

```bash
# 浏览器直接访问，返回 HTML
curl http://localhost:8080/github/octocat/page
```

页面包含：用户头像、简介、统计数据、语言分布、Top 仓库卡片、最近活动。生成后自动归档到 PVC。

#### `POST /github/<username>/screenshot` — 生成展示页 + 截图

```bash
curl -X POST http://localhost:8080/github/octocat/screenshot \
  -H "Content-Type: application/json" \
  -d '{"width": 1280, "height": 900, "full_page": true}'
```

该接口会：
1. 调用 GitHub API 获取数据
2. 生成 HTML 展示页
3. 对该 HTML 截图
4. **自动将 HTML、PNG、JSON 归档到 PVC 持久卷**

返回值包含 `archive` 字段，标明持久化存储路径。

---

### 归档接口

归档数据存储在 PVC 持久卷 `/app/archive`，发布、重启不丢失。

#### `GET /archive` — 列出所有已归档的用户

```bash
curl http://localhost:8080/archive
```

返回示例：

```json
{
  "success": true,
  "count": 2,
  "users": [
    {
      "username": "octocat",
      "latest_generated_at": "2026-02-09T15:30:12",
      "snapshot_count": 5,
      "latest_url": "/archive/octocat/latest/profile.html",
      "latest_screenshot": "/archive/octocat/latest/profile.png"
    }
  ]
}
```

#### `GET /archive/<username>` — 列出某用户的所有快照

```bash
curl http://localhost:8080/archive/octocat
```

#### `GET /archive/<username>/latest/profile.html` — 最新的 HTML 展示页

```bash
# 浏览器直接打开即可
curl http://localhost:8080/archive/octocat/latest/profile.html
```

#### `GET /archive/<username>/latest/profile.png` — 最新的截图

```bash
curl -O http://localhost:8080/archive/octocat/latest/profile.png
```

#### `GET /archive/<username>/history/<timestamp>/profile.html` — 某次历史快照

```bash
curl http://localhost:8080/archive/octocat/history/20260209_153012/profile.html
```

---

### Vault 接口

#### `GET /vault/status` — 查看密钥后端状态

```bash
curl http://localhost:8080/vault/status
```

返回 Vault 连接状态、K8s 认证状态、各后端可用性。

#### `POST /vault/token` — 存储 GitHub Token

```bash
curl -X POST http://localhost:8080/vault/token \
  -H "Content-Type: application/json" \
  -d '{"token": "ghp_xxxxxxxxxxxx"}'
```

#### `DELETE /vault/token` — 删除已存储的 Token

```bash
curl -X DELETE http://localhost:8080/vault/token
```

---

### 健康检查

#### `GET /health`

```bash
curl http://localhost:8080/health
```

返回 Chrome 状态、归档目录可写性、Vault 连接状态、Token 可用性。

---

## Secret 管理（Vault 集成）

### Token 获取优先级

Pod 启动后，`vault_manager.py` 按以下顺序尝试获取 GitHub Token：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | `/vault/secrets/github-token` 文件 | Vault Agent Injector 或 CSI 自动注入 |
| 2 | Vault KV v2 API | 使用 K8s ServiceAccount JWT 认证 |
| 3 | `GITHUB_TOKEN` 环境变量 | 来自 K8s Secret 或手动设置 |
| 4 | `~/.playwright-screenshot/secrets.enc` 本地文件 | 仅限开发环境 |

### 本地开发配置

最简单的方式：

```bash
export GITHUB_TOKEN=ghp_your_token_here
python api.py
```

或使用 CLI 工具持久化保存：

```bash
python vault_manager.py store ghp_your_token_here
python vault_manager.py get       # 查看（脱敏）
python vault_manager.py status    # 查看所有后端状态
python vault_manager.py delete    # 删除
```

### Vault 服务端配置

使用一键配置脚本：

```bash
export VAULT_ADDR=https://vault.example.com:8200
export VAULT_TOKEN=hvs.xxxxx

# 自动完成：启用 KV v2、创建 Policy、配置 K8s Auth、写入 Token
bash k8s/vault-setup.sh ghp_your_token_here
```

脚本执行的操作：
1. 启用 `secret/` KV v2 引擎
2. 创建 `playwright-screenshot` Policy（只读权限）
3. 启用并配置 Kubernetes auth method
4. 创建 Vault Role（绑定 ServiceAccount + Namespace）
5. 写入 GitHub Token 到 `secret/playwright-screenshot/github`

---

## Kubernetes 部署

### 存储架构

```
Pod 内挂载:
┌────────────────────────────────────────────────────────────────┐
│  /app/screenshots   ← emptyDir       临时工作区，Pod 重启清空  │
│  /app/archive       ← PVC (20Gi RWX) 持久归档，发布不丢失     │
│  /vault/secrets     ← Vault Agent     自动注入 GitHub Token    │
│  /dev/shm           ← tmpfs (2Gi)     Headless Chrome 共享内存 │
└────────────────────────────────────────────────────────────────┘
```

**关键设计**：`/app/screenshots` 是临时的 emptyDir，Pod 重启即清空（这没关系，它只是工作区）。真正需要保留的数据全部由应用层复制到 `/app/archive` PVC，这个 PVC 独立于 Pod 生命周期。

### 三种部署方式

| 方式 | 适用场景 | 复杂度 |
|------|----------|--------|
| **Vault Agent Injector** | 生产环境，已部署 Vault | ⭐⭐⭐ |
| **Vault CSI Provider** | 生产环境，不想要 sidecar | ⭐⭐⭐ |
| **K8s Secret** | 开发/测试，无 Vault | ⭐ |

#### 方式一：Vault Agent Injector（推荐生产）

```bash
# 1. 配置 Vault 服务端
bash k8s/vault-setup.sh ghp_your_token_here

# 2. 部署
./k8s/deploy.sh --vault-method=agent
```

工作原理：Vault Agent 以 init container + sidecar 注入 Pod，用 ServiceAccount JWT 向 Vault 认证，将 Token 写入 `/vault/secrets/github-token` 文件，并在 TTL 到期时自动续期。

#### 方式二：Vault CSI Provider

```bash
./k8s/deploy.sh --vault-method=csi
```

工作原理：通过 Secrets Store CSI Driver 将 Vault secret 挂载为 Pod 卷，无需 sidecar。

#### 方式三：K8s Secret（最简单）

```bash
# 1. 创建 Secret
kubectl create secret generic github-token-secret \
  -n playwright-screenshot \
  --from-literal=GITHUB_TOKEN=ghp_your_token_here

# 2. 部署
./k8s/deploy.sh --vault-method=secret
```

### 部署命令

```bash
# 标准部署（默认 Vault Agent 方式）
./k8s/deploy.sh

# 指定镜像仓库和 Tag
./k8s/deploy.sh myregistry.com/myrepo v1.2.0

# 指定部署方式
./k8s/deploy.sh --vault-method=secret
./k8s/deploy.sh --vault-method=csi
./k8s/deploy.sh --vault-method=agent
```

deploy.sh 会自动：构建 Docker 镜像 → 创建 Namespace → 创建 ConfigMap → 创建 Archive PVC → 创建 ServiceAccount → 部署应用 → 部署 Nginx → 等待就绪。

### 验证部署

```bash
# 查看 Pod 状态
kubectl -n playwright-screenshot get pods -o wide

# 查看 PVC 状态
kubectl -n playwright-screenshot get pvc

# 端口转发到本地
kubectl -n playwright-screenshot port-forward svc/nginx 8080:80

# 测试
curl http://localhost:8080/health
curl http://localhost:8080/vault/status
curl http://localhost:8080/github/octocat/page
curl -X POST http://localhost:8080/github/octocat/screenshot

# 验证归档数据已持久化
kubectl -n playwright-screenshot exec -it deploy/playwright-screenshot-api \
  -- ls -la /app/archive/
```

---

## 归档存储（PVC）

### 目录结构

```
/app/archive/                              ← PVC 挂载点 (github-archive-pvc, 20Gi)
├── octocat/
│   ├── latest/                            ← 最新快照（每次生成时覆盖）
│   │   ├── profile.html                   ← GitHub 展示页
│   │   ├── profile.png                    ← 截图
│   │   ├── data.json                      ← 原始 API 数据
│   │   └── meta.json                      ← 元数据（生成时间等）
│   └── history/                           ← 全部历史版本
│       ├── 20260209_153012/
│       │   ├── profile.html
│       │   ├── profile.png
│       │   ├── data.json
│       │   └── meta.json
│       ├── 20260210_091500/
│       │   └── ...
│       └── 20260215_200000/
│           └── ...
├── torvalds/
│   ├── latest/
│   └── history/
└── ...
```

### 工作原理

1. 调用 `GET /github/<user>/page` 或 `POST /github/<user>/screenshot` 时触发
2. 应用将文件先写入 `/app/screenshots`（临时工作区）
3. 然后复制一份到 `/app/archive/<user>/history/<timestamp>/`（历史快照，永不覆盖）
4. 同时覆盖写入 `/app/archive/<user>/latest/`（最新快照，始终可直接访问）
5. 归档目录在 PVC 上，即使 Pod 销毁、Deployment 滚动更新、版本发布，数据都保留

### 运维操作

```bash
# 查看归档用量
kubectl -n playwright-screenshot exec deploy/playwright-screenshot-api \
  -- du -sh /app/archive/

# 查看某用户的快照列表
kubectl -n playwright-screenshot exec deploy/playwright-screenshot-api \
  -- ls -lt /app/archive/octocat/history/

# 手动清理历史（保留最近 10 个）
kubectl -n playwright-screenshot exec deploy/playwright-screenshot-api -- \
  bash -c 'cd /app/archive/octocat/history && ls -t | tail -n +11 | xargs rm -rf'

# 备份 PVC 数据
kubectl -n playwright-screenshot cp \
  deploy/playwright-screenshot-api:/app/archive ./backup-archive/
```

---

## 项目文件结构

```
playwright-screenshot/
├── api.py                          # Flask REST API 主入口
├── screenshot.py                   # Playwright 截图引擎
├── github_api.py                   # GitHub REST API v3 客户端
├── github_page_generator.py        # HTML 展示页生成器
├── vault_manager.py                # Vault + K8s Secret 管理器
├── requirements.txt                # Python 依赖
├── Dockerfile                      # Docker 镜像
├── entrypoint.sh                   # 容器入口脚本
│
└── k8s/                            # Kubernetes 部署配置
    ├── deploy.sh                   # 一键部署脚本
    ├── vault-setup.sh              # Vault 服务端一键配置
    ├── namespace.yaml              # Namespace
    ├── configmap.yaml              # ConfigMap（视口、超时等）
    ├── archive-pvc.yaml            # ⭐ 归档 PVC (20Gi RWX)
    ├── vault-serviceaccount.yaml   # ServiceAccount（Vault K8s Auth）
    ├── deployment.yaml             # Deployment — Vault Agent 方式
    ├── vault-csi.yaml              # Deployment — Vault CSI 方式
    ├── deployment-k8s-secret.yaml  # Deployment — K8s Secret 方式
    ├── github-secret.yaml          # K8s Secret 模板
    ├── service.yaml                # ClusterIP Service
    ├── ingress.yaml                # Ingress（可选）
    ├── nginx-configmap.yaml        # Nginx 配置
    ├── nginx-deployment.yaml       # Nginx Deployment
    ├── nginx-service.yaml          # Nginx Service
    ├── pvc.yaml                    # 旧版 PVC（已被 archive-pvc 取代）
    ├── job.yaml                    # 一次性截图 Job
    ├── cronjob.yaml                # 定时截图 CronJob
    └── cleanup.sh                  # 清理脚本
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | 8080 | API 服务端口 |
| `CHROME_PATH` | /opt/chrome/chrome-linux64/chrome | Chrome 可执行文件路径 |
| `SCREENSHOTS_DIR` | /app/screenshots | 临时截图工作目录 |
| `ARCHIVE_DIR` | /app/archive | 持久化归档目录（PVC 挂载点） |
| `GITHUB_TOKEN` | — | GitHub API Token（后备方案） |
| `VAULT_ADDR` | http://vault.vault.svc.cluster.local:8200 | Vault 地址 |
| `VAULT_TOKEN` | — | Vault Token（开发用） |
| `VAULT_SECRET_FILE` | /vault/secrets/github-token | Vault Agent 注入文件路径 |
| `VAULT_K8S_ROLE` | playwright-screenshot | Vault K8s Auth Role 名称 |
| `K8S_SA_TOKEN_PATH` | /var/run/secrets/.../token | K8s ServiceAccount JWT 路径 |

---

## 命令行工具

除了 REST API，项目还提供独立的命令行工具：

```bash
# 直接截图
python screenshot.py https://github.com/octocat output.png --full-page

# GitHub 用户信息
python github_api.py octocat
python github_api.py octocat --repos
python github_api.py octocat --repo playwright-screenshot
python github_api.py octocat --events

# 生成 HTML 展示页 + 截图
python github_page_generator.py octocat --screenshot --output-dir ./output

# 密钥管理
python vault_manager.py status
python vault_manager.py store ghp_xxxxx
python vault_manager.py get
python vault_manager.py delete
```
