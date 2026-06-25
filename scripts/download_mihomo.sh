#!/bin/bash
# =============================================================================
# 下载 mihomo 可执行文件
# =============================================================================
# 自动检测当前平台，从 GitHub Releases 下载对应版本的 mihomo，解压并重命名为
# ``./mihomo`` 以便后续使用。
#
# 用法::
#
#     # 自动获取最新版本
#     bash scripts/download_mihomo.sh
#
#     # 指定版本
#     bash scripts/download_mihomo.sh v1.19.27
#
#     # 通过环境变量指定版本
#     MIHOMO_VERSION=v1.19.27 bash scripts/download_mihomo.sh
#
# 支持的平台:
#   - linux/amd64, linux/arm64
#   - darwin/amd64, darwin/arm64
#   - windows/amd64
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."  # 回到项目根目录

# ---- 平台检测 ---------------------------------------------------------------
detect_os() {
    local os
    os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    case "$os" in
        linux)         echo "linux"   ;;
        darwin)        echo "darwin"  ;;
        mingw*|msys*|cygwin*) echo "windows" ;;
        *)
            echo "ERROR: 不支持的操作系统: $os" >&2
            exit 1
            ;;
    esac
}

detect_arch() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64)   echo "amd64"  ;;
        aarch64|arm64)  echo "arm64"  ;;
        armv7l|armv7)   echo "armv7"  ;;
        *)
            echo "ERROR: 不支持的架构: $arch" >&2
            exit 1
            ;;
    esac
}

OS="$(detect_os)"
ARCH="$(detect_arch)"

# ---- 确定版本 ---------------------------------------------------------------
if [[ -n "${1:-}" ]]; then
    VERSION="$1"
elif [[ -n "${MIHOMO_VERSION:-}" ]]; then
    VERSION="$MIHOMO_VERSION"
else
    echo ">>> 获取最新 mihomo 版本..."
    VERSION="$(curl -sSf \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest" \
        | sed -nE 's/.*"tag_name": *"([^"]+)".*/\1/p')"

    if [[ -z "$VERSION" ]]; then
        echo "ERROR: 无法获取最新版本（可能触发 API 限流），请手动指定版本" >&2
        exit 1
    fi
    echo "    最新版本: $VERSION"
fi

# ---- 下载 -------------------------------------------------------------------
if [[ "$OS" == "windows" ]]; then
    EXT="zip"
else
    EXT="gz"
fi

ARCHIVE="mihomo-${OS}-${ARCH}-${VERSION}.${EXT}"
URL="https://github.com/MetaCubeX/mihomo/releases/download/${VERSION}/${ARCHIVE}"

echo ">>> 下载: $URL"
curl -sSfL "$URL" -o "$ARCHIVE"

# ---- 解压 -------------------------------------------------------------------
if [[ "$EXT" == "zip" ]]; then
    echo ">>> 解压 zip..."
    # 尝试多种可能的内部文件名
    TMPDIR=".mihomo_extract_$$"
    mkdir -p "$TMPDIR"
    unzip -o "$ARCHIVE" -d "$TMPDIR" >/dev/null

    # 查找 exe 文件
    BIN="$(find "$TMPDIR" -type f -name '*.exe' | head -1)"
    if [[ -z "$BIN" ]]; then
        echo "ERROR: zip 中未找到 .exe 文件" >&2
        rm -rf "$TMPDIR" "$ARCHIVE"
        exit 1
    fi
    mv "$BIN" ./mihomo
    rm -rf "$TMPDIR" "$ARCHIVE"
else
    echo ">>> 解压 gz..."
    gunzip -f "$ARCHIVE"
    # 解压后文件名 = 去掉 .gz 后缀
    BINARY="${ARCHIVE%.gz}"
    mv "$BINARY" mihomo
    chmod +x mihomo
fi

# ---- 验证 -------------------------------------------------------------------
echo ">>> 验证二进制..."
./mihomo -v 2>&1 || true
echo ">>> mihomo 就绪 ($VERSION, $OS/$ARCH)"
