# Playwright Screenshot Tool

基于 Ubuntu 24.04 的 Playwright 网页截图工具。

## 项目结构

```
playwright-screenshot/
├── Dockerfile          # Docker 镜像构建文件
├── requirements.txt    # Python 依赖
├── screenshot.py       # 主截图脚本
├── entrypoint.sh       # 容器入口脚本
└── README.md           # 说明文档
```

## 快速开始

### 1. 构建镜像

```bash
cd /Users/xlisp/PyPro/playwright-screenshot
docker build -t playwright-screenshot .
```

### 2. 运行截图

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
docker run -it --rm -v $(pwd)/output:/app/screenshots playwright-screenshot bash
# 然后在容器内运行:
python3 screenshot.py https://example.com /app/screenshots/test.png
```

## 本地开发

如果想在本地运行而不使用 Docker:

```bash
# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
playwright install-deps chromium

# 运行脚本
python screenshot.py https://example.com output.png
```

## 注意事项

- 镜像大小约 1.5GB (包含 Chromium 浏览器)
- 首次构建需要下载较多依赖，请耐心等待
- 截图输出目录需要挂载到宿主机才能获取文件
