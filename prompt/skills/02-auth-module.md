# Skill: 账号权限模块

## 功能列表

| 功能 | 描述 | 角色 |
|------|------|------|
| 登录/退出 | 验证码/密码登录、Token刷新、退出登录 | 所有角色 |
| 用户管理 | 创建/停用账号、重置密码、分配角色 | Super/Admin |
| 角色权限 | 配置角色、数据权限、菜单权限 | Super |
| 操作审计 | 关键操作留痕、登录日志、导出审计 | Super |

## API端点

```
# 认证
POST   /api/v1/auth/login              # 用户登录
POST   /api/v1/auth/logout             # 用户登出
POST   /api/v1/auth/refresh            # 刷新Token
POST   /api/v1/auth/verify             # 验证Token

# 用户管理
GET    /api/v1/users                   # 用户列表
POST   /api/v1/users                   # 创建用户
GET    /api/v1/users/{id}              # 用户详情
PUT    /api/v1/users/{id}              # 更新用户
DELETE /api/v1/users/{id}              # 删除用户
PUT    /api/v1/users/{id}/password     # 重置密码

# 角色管理
GET    /api/v1/roles                   # 角色列表
POST   /api/v1/roles                   # 创建角色
GET    /api/v1/roles/{id}              # 角色详情
PUT    /api/v1/roles/{id}              # 更新角色
DELETE /api/v1/roles/{id}              # 删除角色
GET    /api/v1/roles/{id}/permissions  # 角色权限
PUT    /api/v1/roles/{id}/permissions  # 更新权限

# 审计日志
GET    /api/v1/logs/audit              # 审计日志
GET    /api/v1/logs/login              # 登录日志
```

## 现有文件

```
src/auth/
├── backend.py           # JWT认证后端
├── manager.py           # 用户管理器
├── models.py            # ORM模型 (User, Role, Permission)
├── rbac.py              # RBAC权限检查
└── schemas.py           # Pydantic Schema

src/api/v1/auth/
├── router.py
└── views.py             # 登录/登出实现

src/api/v1/users/
├── router.py
├── views.py
└── schemas.py

src/api/v1/roles/
├── router.py
├── views.py
└── schemas.py

src/audit/
├── dependencies.py
├── schemas.py
├── service.py
└── __init__.py
```

## 实现要求

### JWT认证

- Token有效期: 24小时
- 刷新Token有效期: 7天
- 使用 `python-jose` 生成/验证Token

### RBAC权限

- 权限格式: `module:action` (如 `user:read`, `order:delete`)
- 角色权限可配置
- 支持数据权限隔离

### 审计日志

- 记录关键操作
- 记录登录登出
- 记录数据导出
