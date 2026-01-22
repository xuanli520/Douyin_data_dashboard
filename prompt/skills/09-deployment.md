# Skill：部署配置

## Docker Compose服务

```yaml
services：
  # 主应用
  app：
    build：。
    ports：
      - "8000:8000"
    environment：
      - ENVIRONMENT=production
    depends_on：
      - postgres
      - redis
    volumes：
      - ./logs:/app/logs
      - ./data:/app/data

  # Celery Worker
  worker：
    build：。
    command：celery -A tasks worker -l info
    depends_on：
      - postgres
      - redis
    volumes：
      - ./logs:/app/logs
      - ./data:/app/data

  # Celery Beat（调度器）
  beat：
    build：。
    command：celery -A tasks beat -l info
    depends_on：
      - redis
    volumes：
      - ./logs:/app/logs

  # PostgreSQL
  postgres：
    image：postgres:15
    environment：
      - POSTGRES_DB=douyin_data
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes：
      - postgres_data:/var/lib/postgresql/data
    ports：
      - "5432:5432"

  # Redis
  redis：
    image：redis:7
    ports：
      - "6379:6379"
    volumes：
      - redis_data:/data

  # Nginx（反向代理）
  nginx：
    image：nginx:alpine
    ports：
      - "80:80"
      - "443:443"
    volumes：
      - ./docker/nginx:/etc/nginx/conf.d
      - ./static:/var/www/static
    depends_on：
      - app

volumes：
  postgres_data：
  redis_data：
```

## 配置文件

```
docker/
├── docker-compose.yml            # 生产环境配置
├── docker-compose.dev.yml        # 开发环境配置
├── docker-compose.prod.yml       # 预发布环境
├── Dockerfile                    # 应用Dockerfile
├── Dockerfile.worker             # Celery Worker Dockerfile
└── nginx/
    ├── default.conf              # Nginx配置
    └── ssl/                      # SSL证书

.env                              # 环境变量（本地）
.env.prod                         # 生产环境变量
.env.test                         # 测试环境变量
```

## 环境变量

```bash
# 数据库
DB__DRIVER=postgresql
DB__HOST=postgres
DB__PORT=5432
DB__NAME=douyin_data
DB__USER=postgres
DB__PASSWORD=postgres

# Redis
REDIS__URL=redis://redis:6379/0

# 应用
APP__HOST=0.0.0.0
APP__PORT=8000
APP__DEBUG=false
APP__SECRET_KEY=your-secret-key

# JWT
JWT__SECRET_KEY=your-jwt-secret
JWT__ALGORITHM=HS256
JWT__ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

## 启动命令

```bash
# 开发环境
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up --build

# 生产环境
docker compose -f docker/docker-compose.yml up --build

# 迁移数据库
docker compose exec app alembic upgrade head
```

## 健康检查

```bash
# 应用健康
GET /api/v1/system/health

# 任务状态
GET /api/v1/system/tasks-status
```

## 日志位置

```
logs/
├── app/                          # 应用日志
│   ├── app.log
│   └── app.log.1
├── tasks/                        # 任务日志
│   ├── task.log
│   └── task.log.1
└── access/                       # 访问日志
    ├── access.log
    └── access.log.1
```
