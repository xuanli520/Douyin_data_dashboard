#!/usr/bin/env bash
set -euo pipefail

mirrors=(
  "https://pypi.tuna.tsinghua.edu.cn/simple"
  "https://mirrors.aliyun.com/pypi/simple"
  "https://mirrors.cloud.tencent.com/pypi/simple"
)

for mirror in "${mirrors[@]}"; do
  echo "uv sync --dev via ${mirror}"
  rm -rf .venv
  if uv sync --dev --refresh --index "${mirror}"; then
    exit 0
  fi
done

exit 1
