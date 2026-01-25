# 实现健康检查端点

## Use Case

生产环境部署后缺乏必要的运维基础设施，无法实现负载均衡器和 K8s 健康检查探测。需要实现 `/health` 端点用于：
- 负载均衡器健康检查
- K8s liveness/readiness probe

## Proposed Solution

实现 `/health` 端点，返回整体健康状态：
- 检查 PostgreSQL 数据库连接
- 检查 Redis 连接
- 返回健康状态 (healthy/degraded/unhealthy)
- HTTP 状态码反映健康状况

## Alternatives Considered

N/A

## Implementation Notes

- 参考项目现有的响应格式
- 保持代码风格一致
- 依赖注入方式获取 DB 和 Redis 连接
