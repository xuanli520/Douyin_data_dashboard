# 后端API端点开发状态提示系统规划

## 核心设计原则

**完全复用现有基础设施，最小化侵入**

基于系统已有架构：`ErrorCode` 枚举 + `BusinessException` 异常 + `handlers.py` 全局异常处理。

**关键设计决策**：
1. 统一走异常通道，保持中间件链完整
2. 在 `handlers.py` 中对非错误状态码静默处理
3. 提供细粒度开关，避免吞掉真实错误
4. `planned`/`deprecated(strict)` 内置鉴权，避免信息泄露

---

## 1. 业务错误码定义

```python
# src/shared/errors.py

class ErrorCode(IntEnum):
    # ... 现有错误码 ...
    
    # 端点开发状态码 (70001-70003)
    # 新增状态码需评估是否加入 NON_ERROR_CODES
    ENDPOINT_IN_DEVELOPMENT = 70001
    ENDPOINT_PLANNED = 70002
    ENDPOINT_DEPRECATED = 70003


ERROR_CODE_TO_HTTP = {
    # ... 现有映射 ...
    ErrorCode.ENDPOINT_IN_DEVELOPMENT: 200,
    ErrorCode.ENDPOINT_PLANNED: 501,
    ErrorCode.ENDPOINT_DEPRECATED: 410,
}

# 非错误状态码：DEBUG 级日志，不计入 APM error rate
NON_ERROR_CODES: set[ErrorCode] = {
    ErrorCode.ENDPOINT_IN_DEVELOPMENT,
}
```

---

## 2. 异常类定义

```python
# src/exceptions.py

class EndpointInDevelopmentException(BusinessException):
    """端点开发中异常 - 非错误状态"""
    
    def __init__(
        self,
        data: dict | None,
        *,
        is_mock: bool = True,
        expected_release: str | None = None,
    ):
        super().__init__(
            code=ErrorCode.ENDPOINT_IN_DEVELOPMENT,
            msg="该功能正在开发中，当前返回演示数据",
            data={
                "mock": is_mock,
                "expected_release": expected_release,
                "data": data,
            },
        )


class EndpointPlannedException(BusinessException):
    """端点计划中异常"""
    
    def __init__(self, expected_release: str | None = None):
        data = {"expected_release": expected_release} if expected_release else None
        super().__init__(
            code=ErrorCode.ENDPOINT_PLANNED,
            msg="该功能正在规划中，暂未实现",
            data=data,
        )


class EndpointDeprecatedException(BusinessException):
    """端点已弃用异常（strict mode）"""
    
    def __init__(self, alternative: str | None = None, removal_date: str | None = None):
        data = {}
        if alternative:
            data["alternative"] = alternative
        if removal_date:
            data["removal_date"] = removal_date
        super().__init__(
            code=ErrorCode.ENDPOINT_DEPRECATED,
            msg="该接口已弃用，请迁移到新接口",
            data=data if data else None,
        )
```

---

## 3. handlers.py 修改

```python
# src/handlers.py (修改 handle_business_exception)

from src.shared.errors import NON_ERROR_CODES

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessException)
    async def handle_business_exception(
        request: Request, exc: BusinessException
    ) -> JSONResponse:
        http_status = error_code_to_http_status(exc.code)
        response = Response.error(code=int(exc.code), msg=exc.msg, data=exc.data)
        
        if exc.code in NON_ERROR_CODES:
            logger.debug("Non-error status: %s", exc)
        else:
            logger.error("BusinessException: %s", exc)
        
        return JSONResponse(content=response.model_dump(), status_code=http_status)
```

---

## 4. 开发状态路由装饰器

```python
# src/core/endpoint_status.py

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, Literal

from fastapi import Depends
from fastapi.responses import JSONResponse

from src.auth import User, current_user
from src.exceptions import (
    EndpointDeprecatedException,
    EndpointInDevelopmentException,
    EndpointPlannedException,
)
from src.responses.base import Response

logger = logging.getLogger(__name__)


def _get_mock(mock_data: dict | Callable[[], dict]) -> dict:
    """获取 mock 数据"""
    try:
        return mock_data() if callable(mock_data) else mock_data
    except Exception as e:
        logger.warning("mock_data callable failed: %s", e)
        return {}


def _raise_in_development(
    data: dict | None,
    *,
    is_mock: bool,
    expected_release: str | None,
) -> None:
    raise EndpointInDevelopmentException(
        data=data,
        is_mock=is_mock,
        expected_release=expected_release,
    )


def in_development(
    mock_data: dict | Callable[[], dict],
    *,
    expected_release: str | None = None,
    prefer_real: bool = False,
    fallback_on_exception: bool = False,
):
    """标记端点为开发中状态
    
    Args:
        mock_data: Mock 数据或返回 Mock 数据的 callable
        expected_release: 预计发布日期
        prefer_real:
            - False (默认): 不执行函数，返回 mock
            - True: 执行函数，成功返回真实数据
        fallback_on_exception:
            - False (默认): 异常向外传播，不吞错误
            - True: 异常时回退 mock（仅灰度场景使用）
    
    **注意**: 
    - prefer_real=False 不执行函数体，副作用不会发生
    - fallback_on_exception=True 会记录原始异常上下文
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            if not prefer_real:
                _raise_in_development(
                    _get_mock(mock_data),
                    is_mock=True,
                    expected_release=expected_release,
                )
            
            try:
                result = await func(*args, **kwargs)
                _raise_in_development(
                    result,
                    is_mock=False,
                    expected_release=expected_release,
                )
            except EndpointInDevelopmentException:
                raise
            except Exception as e:
                if fallback_on_exception:
                    logger.warning(
                        "in_development fallback: %s, error: %s",
                        func.__name__,
                        e,
                        exc_info=True,
                    )
                    _raise_in_development(
                        _get_mock(mock_data),
                        is_mock=True,
                        expected_release=expected_release,
                    )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            if not prefer_real:
                _raise_in_development(
                    _get_mock(mock_data),
                    is_mock=True,
                    expected_release=expected_release,
                )
            
            try:
                result = func(*args, **kwargs)
                _raise_in_development(
                    result,
                    is_mock=False,
                    expected_release=expected_release,
                )
            except EndpointInDevelopmentException:
                raise
            except Exception as e:
                if fallback_on_exception:
                    logger.warning(
                        "in_development fallback: %s, error: %s",
                        func.__name__,
                        e,
                        exc_info=True,
                    )
                    _raise_in_development(
                        _get_mock(mock_data),
                        is_mock=True,
                        expected_release=expected_release,
                    )
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def planned(
    expected_release: str | None = None,
):
    """标记端点为计划中状态，返回 501
    
    **内置鉴权**: 通过依赖注入要求已登录用户，避免信息泄露。
    
    **注意**: 501 可能触发网关重试，需确认网关配置。
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(
            *args,
            _planned_user: User = Depends(current_user),
            **kwargs,
        ) -> Any:
            raise EndpointPlannedException(expected_release=expected_release)

        @wraps(func)
        def sync_wrapper(
            *args,
            _planned_user: User = Depends(current_user),
            **kwargs,
        ) -> Any:
            raise EndpointPlannedException(expected_release=expected_release)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def deprecated(
    alternative: str | None = None,
    *,
    removal_date: str | None = None,
    mode: Literal["soft", "strict"] = "soft",
):
    """标记端点为已弃用状态
    
    Args:
        alternative: 替代端点路径
        removal_date: 计划移除日期
        mode:
            - "soft": 执行函数，返回结果 + 响应头警告
            - "strict": 返回 410 错误（内置鉴权）
    
    **soft mode**: 
    - 只添加响应头，不修改响应体
    - 返回 JSONResponse（已包装格式），绕过 ResponseWrapperMiddleware
    - 无内置鉴权，保持原有鉴权行为
    
    **strict mode**: 内置鉴权，避免向未授权用户暴露弃用信息。
    """
    def decorator(func: Callable) -> Callable:
        if mode == "strict":
            @wraps(func)
            async def async_wrapper_strict(
                *args,
                _deprecated_user: User = Depends(current_user),
                **kwargs,
            ) -> Any:
                raise EndpointDeprecatedException(
                    alternative=alternative, removal_date=removal_date
                )

            @wraps(func)
            def sync_wrapper_strict(
                *args,
                _deprecated_user: User = Depends(current_user),
                **kwargs,
            ) -> Any:
                raise EndpointDeprecatedException(
                    alternative=alternative, removal_date=removal_date
                )

            return (
                async_wrapper_strict
                if asyncio.iscoroutinefunction(func)
                else sync_wrapper_strict
            )

        @wraps(func)
        async def async_wrapper_soft(*args, **kwargs) -> Any:
            result = await func(*args, **kwargs)
            
            headers = {
                "X-Deprecated": "true",
                **({"X-Deprecated-Alternative": alternative} if alternative else {}),
                **({"X-Deprecated-Removal-Date": removal_date} if removal_date else {}),
            }
            
            if hasattr(result, "headers"):
                for k, v in headers.items():
                    result.headers[k] = v
                return result
            
            return JSONResponse(
                content=Response.success(data=result).model_dump(),
                status_code=200,
                headers=headers,
            )

        @wraps(func)
        def sync_wrapper_soft(*args, **kwargs) -> Any:
            result = func(*args, **kwargs)
            
            headers = {
                "X-Deprecated": "true",
                **({"X-Deprecated-Alternative": alternative} if alternative else {}),
                **({"X-Deprecated-Removal-Date": removal_date} if removal_date else {}),
            }
            
            if hasattr(result, "headers"):
                for k, v in headers.items():
                    result.headers[k] = v
                return result
            
            return JSONResponse(
                content=Response.success(data=result).model_dump(),
                status_code=200,
                headers=headers,
            )

        return async_wrapper_soft if asyncio.iscoroutinefunction(func) else sync_wrapper_soft
    return decorator
```

---

## 5. 使用示例

```python
from fastapi import APIRouter, Depends
from src.auth import current_user, User
from src.core.endpoint_status import in_development, planned, deprecated

router = APIRouter(prefix="/analytics")


# 早期开发：纯 mock
@router.get("/realtime")
@in_development(mock_data={"visitors": 1234})
async def get_realtime():
    pass


# 灰度联调：优先真实，失败抛异常
@router.get("/dashboard")
@in_development(mock_data={"placeholder": True}, prefer_real=True)
async def get_dashboard():
    return await fetch_dashboard()


# 灰度联调：优先真实，失败回退 mock
@router.get("/metrics")
@in_development(
    mock_data={"value": 0},
    prefer_real=True,
    fallback_on_exception=True,
)
async def get_metrics():
    return await fetch_metrics()


# 计划中：内置鉴权
@router.get("/forecast")
@planned(expected_release="2026-03-01")
async def get_forecast():
    pass  # 未授权返回 401，已授权返回 501


# 软弃用：保持原有鉴权行为
@router.get("/legacy")
@deprecated(alternative="/api/v2/legacy")
async def get_legacy(user: User = Depends(current_user)):
    return {"data": "..."}


# 严格弃用：内置鉴权
@router.get("/old-export")
@deprecated(mode="strict")
async def get_old_export():
    pass  # 未授权返回 401，已授权返回 410
```

---

## 6. 响应格式

### 6.1 开发中 (code: 70001, HTTP: 200)

```json
{
  "code": 70001,
  "msg": "该功能正在开发中，当前返回演示数据",
  "data": {
    "mock": true,
    "expected_release": "2026-02-20",
    "data": {"visitors": 1234}
  }
}
```

`mock: false` 表示 `prefer_real=True` 且函数成功返回真实数据。

### 6.2 计划中 (code: 70002, HTTP: 501)

未授权 → HTTP 401  
已授权 → HTTP 501

```json
{
  "code": 70002,
  "msg": "该功能正在规划中，暂未实现",
  "data": {"expected_release": "2026-03-01"}
}
```

### 6.3 已弃用 - soft (HTTP: 200)

```json
{
  "code": 200,
  "msg": "success",
  "data": {...}
}
```

Headers: `X-Deprecated: true`

### 6.4 已弃用 - strict (HTTP: 410)

未授权 → HTTP 401  
已授权 → HTTP 410

```json
{
  "code": 70003,
  "msg": "该接口已弃用，请迁移到新接口",
  "data": {"alternative": "/api/v2/..."}
}
```

---

## 7. APM 监控策略

| 状态 | HTTP | 日志级别 | Error Rate |
|------|------|---------|------------|
| `in_development` | 200 | DEBUG | ❌ 排除 |
| `planned` | 501 | ERROR | ✅ 计入 |
| `deprecated(soft)` | 200 | N/A | N/A |
| `deprecated(strict)` | 410 | ERROR | ✅ 计入 |

**APM 配置**:
```yaml
error_rate_exclude:
  business_code: [70001]
```

---

## 8. 副作用说明

`in_development(prefer_real=False)` 不执行函数体，以下副作用不会发生：
- 数据库写入
- 缓存更新
- 访问统计
- 审计日志

如需保留副作用，使用 `prefer_real=True`。

---

## 9. 安全设计

| 装饰器 | 鉴权方式 | 未授权行为 |
|--------|---------|-----------|
| `in_development` | 无内置 | 正常返回 mock |
| `planned` | 内置 `Depends(current_user)` | 返回 401 |
| `deprecated(soft)` | 无内置 | 保持原有鉴权行为 |
| `deprecated(strict)` | 内置 `Depends(current_user)` | 返回 401 |

**设计原则**: `planned` 和 `deprecated(strict)` 内置鉴权，避免向未授权用户暴露端点信息。

---

## 10. ResponseWrapperMiddleware 兼容性

`deprecated(soft)` 返回的 `JSONResponse` 包含 `code/msg/data` 结构。

由于直接返回 `JSONResponse`（非通过 `call_next`），不经过 middleware 的 body 处理逻辑，无二次包装问题。

---

## 11. 实施步骤

1. `errors.py`: 添加错误码 + `NON_ERROR_CODES`
2. `exceptions.py`: 添加异常类
3. `handlers.py`: 修改异常处理器
4. `endpoint_status.py`: 创建装饰器
5. 配置 APM: 过滤 `business_code: [70001]`
