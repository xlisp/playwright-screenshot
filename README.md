# Playwright Screenshot Tool (Offline Version)

基于 Ubuntu 24.04 的 Playwright 网页截图工具，支持离线安装 Chrome 浏览器。

## 项目结构

```
playwright-screenshot/
├── Dockerfile          # Docker 镜像构建文件
├── requirements.txt    # Python 依赖
├── screenshot.py       # 主截图脚本
├── entrypoint.sh       # 容器入口脚本
├── chrome-linux64.zip  # 本地 Chrome 浏览器 (需手动复制: https://storage.googleapis.com/chrome-for-testing-public/143.0.7499.4/linux64/chrome-linux64.zip) 
└── README.md           # 说明文档
```

## 快速开始

### 1. 准备 Chrome 浏览器文件

由于网络限制，需要手动复制本地 Chrome 浏览器文件到项目目录：

```bash
cp /Users/xlisp/Downloads/chrome-linux64.zip /Users/xlisp/PyPro/playwright-screenshot/
```

### 2. 构建镜像

```bash
cd /Users/xlisp/PyPro/playwright-screenshot
docker build -t playwright-screenshot .
```

### 3. 运行截图

**默认截图 (Docker Hub Ubuntu 页面):**

```bash
docker run --rm -v $(pwd)/output:/app/screenshots playwright-screenshot
```

**自定义 URL:**

```bash
docker run --rm -v $(pwd)/output:/app/screenshots playwright-screenshot \
    "https://github.com" \
    "/app/screenshots/github.png"
```

**带参数截图:**

```bash
docker run --rm -v $(pwd)/output:/app/screenshots playwright-screenshot \
    "https://example.com" \
    "/app/screenshots/example.png" \
    --width 1280 \
    --height 720 \
    --viewport-only
```
**本地多次测试:**
```
# 跑一个bash
base ❯ docker exec -it playwright_container2 bash
root@9999bade782c:/app#

#=>
❯ docker exec playwright_container2 python3 /app/screenshot.py https://hub.docker.com/_/ubuntu /app/screenshots/test.png
🔧 Using Chrome at: /opt/chrome/chrome-linux64/chrome
📸 Navigating to: https://hub.docker.com/_/ubuntu
⏳ Waiting 3000ms for content to load...
✅ Screenshot saved to: /app/screenshots/test.png
📁 File size: 511.41 KB
~ 32s
❯ docker cp playwright_container2:/app/screenshots/test.png ./test.png
Successfully copied 525kB to /Users/xlisp/test.png
~
❯ docker ps
CONTAINER ID   IMAGE                          COMMAND                  CREATED         STATUS         PORTS     NAMES
9999bade782c   playwright-screenshot:latest   "bash -c 'tail -f /d…"   2 minutes ago   Up 2 minutes             playwright_container2
~
❯

# 进入当前跑的bash:
❯ docker exec -i -t 9999bade782c /bin/bash
root@9999bade782c:/app# ls -lh /app/screenshots/test.png
-rw-r--r-- 1 root root 512K Jan 22 08:28 /app/screenshots/test.png
root@9999bade782c:/app#

# 运行的手动安装的chrome:
root@9999bade782c:/app# playwright -V
Version 1.57.0
root@9999bade782c:/app# ls /opt/chrome/chrome-linux64/chrome
/opt/chrome/chrome-linux64/chrome
root@9999bade782c:/app# ls /opt/chrome/chrome-linux64
ABOUT                                chrome                  chrome_crashpad_handler  icudtl.dat            libvulkan.so.1       resources.pak            xdg-mime
MEIPreload                           chrome-wrapper          chrome_sandbox           libEGL.so             locales              rpm.deps                 xdg-settings
PrivacySandboxAttestationsPreloaded  chrome_100_percent.pak  deb.deps                 libGLESv2.so          product_logo_48.png  v8_context_snapshot.bin
WidevineCdm                          chrome_200_percent.pak  hyphen-data              libvk_swiftshader.so  resources            vk_swiftshader_icd.json
root@9999bade782c:/app#
```
## 命令行参数

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | - | https://hub.docker.com/_/ubuntu | 目标网页 URL |
| `output` | - | /app/screenshots/screenshot.png | 输出文件路径 |
| `--width` | `-W` | 1920 | 视口宽度 (像素) |
| `--height` | `-H` | 1080 | 视口高度 (像素) |
| `--full-page` | `-f` | True | 全页面截图 |
| `--viewport-only` | `-v` | False | 仅截取视口 |
| `--wait` | `-w` | 3000 | 页面加载后等待时间 (毫秒) |
| `--timeout` | `-t` | 60000 | 导航超时时间 (毫秒) |

## 示例

### 截取 GitHub 首页

```bash
docker run --rm -v $(pwd)/output:/app/screenshots playwright-screenshot \
    "https://github.com" \
    "/app/screenshots/github.png"
```

### 截取指定尺寸的视口

```bash
docker run --rm -v $(pwd)/output:/app/screenshots playwright-screenshot \
    "https://example.com" \
    "/app/screenshots/mobile.png" \
    --width 375 \
    --height 812 \
    --viewport-only
```

### 交互式进入容器

```bash
docker run -it --rm --entrypoint bash -v $(pwd)/output:/app/screenshots playwright-screenshot
# 然后在容器内运行:
python3 screenshot.py https://example.com /app/screenshots/test.png
```

## 离线安装说明

本项目使用本地 Chrome 浏览器文件，避免了从外网下载的限制。

Chrome 浏览器文件来源：
- 官方下载: https://googlechromelabs.github.io/chrome-for-testing/
- 选择 Linux x64 版本的 `chrome-linux64.zip`

浏览器安装位置：`/opt/chrome/chrome-linux64/chrome`

## 注意事项

- 构建前必须将 `chrome-linux64.zip` 复制到项目目录
- 镜像大小约 1.5GB (包含 Chrome 浏览器)
- 截图输出目录需要挂载到宿主机才能获取文件
