FROM node:20-bookworm-slim AS node_runtime

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright \
    PATH=/app/node_modules/.bin:$PATH

ARG PLAYWRIGHT_CHROMIUM_VERSION=149.0.7827.3
ARG PLAYWRIGHT_CHROMIUM_REVISION=1224
ARG PLAYWRIGHT_CFT_MIRROR=https://cdn.npmmirror.com/binaries/chrome-for-testing
ENV PLAYWRIGHT_CFT_MIRROR=${PLAYWRIGHT_CFT_MIRROR}

COPY --from=node_runtime /usr/local/ /usr/local/

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev build-essential postgresql-client curl unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy repository into image. .dockerignore will exclude tests, docs and other dev files
COPY . .

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && npm config set registry https://registry.npmmirror.com \
    && python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir . \
    && npm ci \
    && npx playwright install-deps chromium \
    && mkdir -p "/ms-playwright/chromium-${PLAYWRIGHT_CHROMIUM_REVISION}" "/ms-playwright/chromium_headless_shell-${PLAYWRIGHT_CHROMIUM_REVISION}" \
    && curl -fsSL "${PLAYWRIGHT_CFT_MIRROR}/${PLAYWRIGHT_CHROMIUM_VERSION}/linux64/chrome-linux64.zip" -o /tmp/chrome-linux64.zip \
    && curl -fsSL "${PLAYWRIGHT_CFT_MIRROR}/${PLAYWRIGHT_CHROMIUM_VERSION}/linux64/chrome-headless-shell-linux64.zip" -o /tmp/chrome-headless-shell-linux64.zip \
    && unzip -q /tmp/chrome-linux64.zip -d "/ms-playwright/chromium-${PLAYWRIGHT_CHROMIUM_REVISION}" \
    && unzip -q /tmp/chrome-headless-shell-linux64.zip -d "/ms-playwright/chromium_headless_shell-${PLAYWRIGHT_CHROMIUM_REVISION}" \
    && touch "/ms-playwright/chromium-${PLAYWRIGHT_CHROMIUM_REVISION}/INSTALLATION_COMPLETE" "/ms-playwright/chromium-${PLAYWRIGHT_CHROMIUM_REVISION}/DEPENDENCIES_VALIDATED" \
    && touch "/ms-playwright/chromium_headless_shell-${PLAYWRIGHT_CHROMIUM_REVISION}/INSTALLATION_COMPLETE" "/ms-playwright/chromium_headless_shell-${PLAYWRIGHT_CHROMIUM_REVISION}/DEPENDENCIES_VALIDATED" \
    && npx playwright install ffmpeg \
    && rm -f /tmp/chrome-linux64.zip /tmp/chrome-headless-shell-linux64.zip

RUN mkdir -p /opt/google \
    && ln -sfn "/ms-playwright/chromium-${PLAYWRIGHT_CHROMIUM_REVISION}/chrome-linux64" /opt/google/chrome

EXPOSE 8000

RUN chmod +x ./docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
