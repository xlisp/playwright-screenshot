# Playwright Screenshot - Kubernetes Deployment

本目录包含将 Playwright Screenshot REST API 服务部署到 Kubernetes 的所有配置文件。

## 架构

```
                    ┌─────────────────┐
                    │   LoadBalancer  │
                    │    (Port 80)    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │      Nginx      │
                    │  (Reverse Proxy)│
                    │   Rate Limit    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼────┐  ┌──────▼─────┐  ┌─────▼─────┐
     │  API Pod 1  │  │  API Pod 2 │  │  API Pod N│
     │  (Port 8080)│  │ (Port 8080)│  │(Port 8080)│
     └──────┬──────┘  └─────┬──────┘  └─────┬─────┘
            │               │               │
            └───────────────┼───────────────┘
                            │
                   ┌────────▼────────┐
                   │       PVC       │
                   │  (Screenshots)  │
                   └─────────────────┘
```

## 目录结构

```
k8s/
├── README.md              # 本文档
├── deploy.sh              # 一键部署脚本
├── cleanup.sh             # 清理脚本
├── namespace.yaml         # 命名空间
├── configmap.yaml         # API 配置
├── pvc.yaml               # 持久化存储
├── service.yaml           # API Service
├── deployment.yaml        # API Deployment
├── nginx-configmap.yaml   # Nginx 配置
├── nginx-deployment.yaml  # Nginx Deployment
├── nginx-service.yaml     # Nginx Service (LoadBalancer)
├── ingress.yaml           # Ingress (可选)
├── job.yaml               # 一次性任务模板
└── cronjob.yaml           # 定时任务配置
```

## 快速开始

### 前置条件

- Docker 已安装
- kubectl 已配置并连接到 K8s 集群
- 项目根目录包含 `chrome-linux64.zip` 文件

### 一键部署

```bash
# 本地镜像部署
./deploy.sh

# 推送到 Docker Hub
./deploy.sh docker.io/your-username latest

# 推送到私有仓库
./deploy.sh registry.example.com/your-repo v1.0.0
```

### 手动部署

```bash
# 1. 构建 Docker 镜像
cd /path/to/playwright-screenshot
docker build -t playwright-screenshot:latest .

# 2. 按顺序应用 K8s 资源
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/nginx-configmap.yaml
kubectl apply -f k8s/nginx-deployment.yaml
kubectl apply -f k8s/nginx-service.yaml
```

## REST API 使用

### 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /screenshot | 创建截图 |
| GET | /screenshots | 列出所有截图 |
| GET | /screenshots/{filename} | 下载截图 |
| DELETE | /screenshots/{filename} | 删除截图 |
| GET | /health | 健康检查 |

### 示例请求

#### 1. 创建截图

```bash
curl -X POST http://<IP>/screenshot \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "width": 1920,
    "height": 1080,
    "full_page": true,
    "wait_time": 3000,
    "format": "png"
  }'
```

响应：
```json
{
  "success": true,
  "filename": "screenshot_20240101_120000_abc123_def456.png",
  "url": "https://example.com",
  "download_url": "/screenshots/screenshot_20240101_120000_abc123_def456.png",
  "file_size": 123456,
  "file_size_human": "120.56 KB"
}
```

#### 2. 列出截图

```bash
curl http://<IP>/screenshots
```

#### 3. 下载截图

```bash
curl -O http://<IP>/screenshots/screenshot_20240101_120000_abc123_def456.png
```

#### 4. 本地测试 (Port Forward)

```bash
kubectl -n playwright-screenshot port-forward svc/nginx 8080:80

# 然后访问
curl -X POST http://localhost:8080/screenshot \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com"}'
```

## 配置说明

### API 参数

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| url | string | 必填 | 目标 URL |
| width | int | 1920 | 视口宽度 (320-3840) |
| height | int | 1080 | 视口高度 (240-2160) |
| full_page | bool | true | 是否全页截图 |
| wait_time | int | 3000 | 等待时间 (ms, 0-30000) |
| timeout | int | 60000 | 超时时间 (ms, 5000-120000) |
| format | string | png | 格式 (png/jpeg) |

### Nginx 配置

- 速率限制: 10 请求/秒，突发 20
- 连接限制: 每 IP 10 个连接
- 代理超时: 截图 120 秒，其他 30 秒

### 使用 Nginx Plus

如果你有 Nginx Plus 许可证：

1. 构建或拉取 Nginx Plus 镜像
2. 创建 registry secret:
```bash
kubectl -n playwright-screenshot create secret docker-registry nginx-plus-registry-secret \
  --docker-server=your-registry \
  --docker-username=your-user \
  --docker-password=your-password
```

3. 修改 `nginx-deployment.yaml`:
```yaml
image: your-registry/nginx-plus:r30
imagePullSecrets:
  - name: nginx-plus-registry-secret
```

## 常用命令

```bash
# 查看状态
kubectl -n playwright-screenshot get all

# 查看日志
kubectl -n playwright-screenshot logs -l component=api -f
kubectl -n playwright-screenshot logs -l component=nginx -f

# 扩缩容
kubectl -n playwright-screenshot scale deployment/playwright-screenshot-api --replicas=3

# 重启部署
kubectl -n playwright-screenshot rollout restart deployment/playwright-screenshot-api

# 进入 Pod
kubectl -n playwright-screenshot exec -it deploy/playwright-screenshot-api -- /bin/bash
```

## 清理

```bash
./cleanup.sh

# 或手动
kubectl delete namespace playwright-screenshot
```

## 故障排查

### API 返回 500

1. 检查 Chrome 是否正常: `kubectl -n playwright-screenshot exec -it deploy/playwright-screenshot-api -- /opt/chrome/chrome-linux64/chrome --version`
2. 检查内存是否足够
3. 查看日志: `kubectl -n playwright-screenshot logs -l component=api`

### Nginx 502 Bad Gateway

1. 确认 API Pod 运行正常
2. 检查 Service 是否正确指向 Pod
3. 验证端口配置
