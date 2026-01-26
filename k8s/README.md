# Playwright Screenshot - Kubernetes Deployment

本目录包含将 Playwright Screenshot 服务部署到 Kubernetes 的所有配置文件。

## 目录结构

```
k8s/
├── README.md           # 本文档
├── deploy.sh           # 一键部署脚本
├── cleanup.sh          # 清理脚本
├── namespace.yaml      # 命名空间定义
├── configmap.yaml      # 配置参数
├── pvc.yaml            # 持久化存储
├── deployment.yaml     # 部署配置
├── job.yaml            # 一次性任务模板
└── cronjob.yaml        # 定时任务配置
```

## 快速开始

### 前置条件

- Docker 已安装
- kubectl 已配置并连接到 K8s 集群
- 项目根目录包含 `chrome-linux64.zip` 文件

### 一键部署

```bash
# 本地镜像部署（需要集群可以访问本地镜像）
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

# 2. 如需要，推送到镜像仓库
docker tag playwright-screenshot:latest your-registry/playwright-screenshot:latest
docker push your-registry/playwright-screenshot:latest

# 3. 更新 deployment.yaml 中的镜像地址

# 4. 按顺序应用 K8s 资源
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
```

## 使用方法

### 在运行的 Pod 中执行截图

```bash
# 获取 Pod 名称
POD=$(kubectl -n playwright-screenshot get pod -l app=playwright-screenshot -o jsonpath='{.items[0].metadata.name}')

# 执行截图
kubectl -n playwright-screenshot exec -it $POD -- /app/entrypoint.sh 'https://github.com' '/app/screenshots/github.png'

# 复制截图到本地
kubectl -n playwright-screenshot cp $POD:/app/screenshots/github.png ./github.png
```

### 运行一次性 Job

```bash
# 编辑 job.yaml 中的 URL 和输出路径，然后：
kubectl apply -f k8s/job.yaml

# 或者从模板创建带时间戳的 Job
kubectl -n playwright-screenshot create job screenshot-$(date +%s) --from=job/screenshot-job
```

### 部署定时任务

```bash
# 编辑 cronjob.yaml 中的 schedule 和 URL，然后：
kubectl apply -f k8s/cronjob.yaml

# 查看定时任务状态
kubectl -n playwright-screenshot get cronjob
```

## 配置说明

### ConfigMap 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| VIEWPORT_WIDTH | 1920 | 视口宽度 |
| VIEWPORT_HEIGHT | 1080 | 视口高度 |
| WAIT_TIME | 3000 | 页面加载后等待时间 (ms) |
| TIMEOUT | 60000 | 导航超时时间 (ms) |
| CHROME_PATH | /opt/chrome/chrome-linux64/chrome | Chrome 路径 |

### 资源配置

默认资源限制：
- 内存请求: 512Mi，限制: 2Gi
- CPU 请求: 250m，限制: 1000m
- 共享内存 (/dev/shm): 2Gi

可根据需要在 deployment.yaml 中调整。

### 存储

默认创建 10Gi 的 PVC 用于存储截图。如需使用特定 StorageClass，取消 pvc.yaml 中的注释并修改。

## 常用命令

```bash
# 查看 Pod 状态
kubectl -n playwright-screenshot get pods

# 查看日志
kubectl -n playwright-screenshot logs -l app=playwright-screenshot

# 扩缩容
kubectl -n playwright-screenshot scale deployment/playwright-screenshot --replicas=3

# 进入 Pod Shell
kubectl -n playwright-screenshot exec -it $POD -- /bin/bash

# 列出截图
kubectl -n playwright-screenshot exec -it $POD -- ls -la /app/screenshots/
```

## 清理

```bash
# 使用清理脚本
./cleanup.sh

# 或手动删除
kubectl delete namespace playwright-screenshot
```

## 故障排查

### Chrome 无法启动

确保：
1. 镜像构建时包含了 `chrome-linux64.zip`
2. Pod 有足够的内存（建议至少 1Gi）
3. `/dev/shm` 挂载正确

### 截图空白或失败

1. 检查目标 URL 是否可访问
2. 增加 WAIT_TIME 等待时间
3. 检查是否有网络策略阻止出站流量

### 存储问题

1. 确认 PVC 已绑定：`kubectl -n playwright-screenshot get pvc`
2. 检查存储类是否支持所需的访问模式

### 使用 Docker Desktop 内置 K8s

```
# 1. 打开 Docker Desktop
# 2. Settings → Kubernetes → Enable Kubernetes
# 3. 等待启动完成，然后运行：
kubectl config use-context docker-desktop
```

```
❯ kubectl config use-context docker-desktop

Switched to context "docker-desktop".

~/PyPro/playwright-screenshot/k8s main
❯  ./deploy.sh

========================================
  Playwright Screenshot K8s Deployer
========================================

[INFO] Checking prerequisites...
[SUCCESS] Prerequisites check passed
[INFO] Building Docker image...
[+] Building 0.5s (16/16) FINISHED                                                                                                docker:desktop-linux
 => [internal] load build definition from Dockerfile                                                                                              0.0s
 => => transferring dockerfile: 2.08kB                                                                                                            0.0s
 => [internal] load metadata for docker.io/library/ubuntu:24.04                                                                                   0.0s
 => [internal] load .dockerignore                                                                                                                 0.0s
 => => transferring context: 2B                                                                                                                   0.0s
 => [ 1/11] FROM docker.io/library/ubuntu:24.04@sha256:cd1dba651b3080c3686ecf4e3c4220f026b521fb76978881737d24f200828b2b                           0.0s
 => => resolve docker.io/library/ubuntu:24.04@sha256:cd1dba651b3080c3686ecf4e3c4220f026b521fb76978881737d24f200828b2b                             0.0s
 => [internal] load build context                                                                                                                 0.0s
 => => transferring context: 143B                                                                                                                 0.0s
 => CACHED [ 2/11] RUN apt-get update && apt-get install -y     python3     python3-pip     python3-venv     unzip     libasound2t64     libatk-  0.0s
 => CACHED [ 3/11] WORKDIR /app                                                                                                                   0.0s
 => CACHED [ 4/11] COPY requirements.txt .                                                                                                        0.0s
 => CACHED [ 5/11] RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages                                                    0.0s
 => CACHED [ 6/11] COPY chrome-linux64.zip /tmp/chrome-linux64.zip                                                                                0.0s
 => CACHED [ 7/11] RUN mkdir -p /opt/chrome     && unzip /tmp/chrome-linux64.zip -d /opt/chrome     && rm /tmp/chrome-linux64.zip     && chmod +  0.0s
 => CACHED [ 8/11] COPY screenshot.py .                                                                                                           0.0s
 => CACHED [ 9/11] COPY entrypoint.sh .                                                                                                           0.0s
 => CACHED [10/11] RUN chmod +x entrypoint.sh                                                                                                     0.0s
 => CACHED [11/11] RUN mkdir -p /app/screenshots                                                                                                  0.0s
 => exporting to image                                                                                                                            0.2s
 => => exporting layers                                                                                                                           0.0s
 => => exporting manifest sha256:6e3a9d85898b7f03b9f69315a41dcefe38c0539d355ee6978d78da55d5ebcdbe                                                 0.0s
 => => exporting config sha256:257cc62cd3ecd6252f54c9aeff58c88e59bce3e5ecfad43d51d14ce51d7ff134                                                   0.0s
 => => exporting attestation manifest sha256:eae432a63135faf92a1ec64cfb1a5de3d6d4fbc1d429f14fe4649fe4b03021e4                                     0.0s
 => => exporting manifest list sha256:12b9e5187376e31a0b6aca66791c86f93d1a3879bf06234442122f31a9b58f50                                            0.0s
 => => naming to docker.io/library/playwright-screenshot:latest                                                                                   0.0s
 => => unpacking to docker.io/library/playwright-screenshot:latest                                                                                0.0s

View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/mdu919ovyjyts50rfvlk0hyqd
[SUCCESS] Image built: playwright-screenshot:latest
[INFO] Deploying to Kubernetes...
[INFO] Creating namespace...
namespace/playwright-screenshot created
[INFO] Creating ConfigMap...
configmap/playwright-screenshot-config created
[INFO] Creating PersistentVolumeClaim...
persistentvolumeclaim/playwright-screenshot-pvc created
[INFO] Creating Deployment...
deployment.apps/playwright-screenshot created
[SUCCESS] Base deployment completed

Deploy CronJob for scheduled screenshots? (y/N): y
cronjob.batch/scheduled-screenshot created
[SUCCESS] CronJob deployed
[INFO] Waiting for deployment to be ready...
Waiting for deployment "playwright-screenshot" rollout to finish: 0 of 2 updated replicas are available...
Waiting for deployment "playwright-screenshot" rollout to finish: 1 of 2 updated replicas are available...
deployment "playwright-screenshot" successfully rolled out
[SUCCESS] Deployment is ready

[INFO] Deployment Status:
====================

Pods:
NAME                                     READY   STATUS    RESTARTS   AGE
playwright-screenshot-84d75d7f99-5fl7z   1/1     Running   0          14s
playwright-screenshot-84d75d7f99-d2f5m   1/1     Running   0          14s

Deployment:
NAME                    READY   UP-TO-DATE   AVAILABLE   AGE
playwright-screenshot   2/2     2            2           15s

PVC:
NAME                        STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEATTRIBUTESCLASS   AGE
playwright-screenshot-pvc   Bound    pvc-57d8c6c8-aabd-419b-b9e9-ceb53c217e33   10Gi       RWO            hostpath       <unset>                 16s

CronJobs:
NAME                   SCHEDULE    TIMEZONE   SUSPEND   ACTIVE   LAST SCHEDULE   AGE
scheduled-screenshot   0 * * * *   <none>     False     0        <none>          8s

[INFO] Usage Instructions:
====================

1. Run a one-time screenshot job:
   kubectl -n playwright-screenshot create job screenshot-$(date +%s) --from=job/screenshot-job

2. Execute screenshot in running pod:
   POD=$(kubectl -n playwright-screenshot get pod -l app=playwright-screenshot -o jsonpath='{.items[0].metadata.name}')
   kubectl -n playwright-screenshot exec -it $POD -- /app/entrypoint.sh 'https://example.com' '/app/screenshots/test.png'

3. Copy screenshots from pod:
   kubectl -n playwright-screenshot cp $POD:/app/screenshots/test.png ./test.png

4. View logs:
   kubectl -n playwright-screenshot logs -l app=playwright-screenshot

5. Scale deployment:
   kubectl -n playwright-screenshot scale deployment/playwright-screenshot --replicas=3

[SUCCESS] Deployment completed successfully!

~/PyPro/playwright-screenshot/k8s main 20s
❯
```
