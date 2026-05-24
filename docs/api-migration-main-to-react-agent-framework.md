# main 到 feat/react-agent-framework API 迁移

## 范围

本文只记录当前分支相对 `main` 的后端 API 变化。所有 HTTP 路径默认带 `/api/v1` 前缀，认证沿用现有 Cookie/JWT。

## 新增接口

| 模块 | 方法 | 路径 | 说明 |
|---|---|---|---|
| Agent 登录 | POST | `/agent-login/start` | 发起抖店登录会话 |
| Agent 登录 | POST | `/agent-login/{session_id}/code` | 提交短信验证码 |
| Agent 登录 | POST | `/agent-login/{session_id}/cancel` | 取消登录会话 |
| Agent 登录 | WS | `/agent-login/{session_id}/events` | 订阅登录事件 |
| Agent Discovery | POST | `/agent-discovery` | 发起浏览器探索并生成 recipe |
| Agent Discovery | WS | `/agent-discovery/{run_id}/events` | 订阅探索事件 |
| Agent Recipe | POST | `/agent-discovery/recipes/{recipe_id}/mark-stable` | 标记 recipe 为 stable |
| Agent Recipe | GET | `/agent-discovery/recipes/{recipe_id}/export` | 导出 `.agent-recipe.json` |
| Agent Recipe | POST | `/agent-discovery/recipes/import` | 导入 `.agent-recipe.json` |
| Agent Result | GET | `/agent-results` | 查询 agent 采集结果 |
| Agent Result | GET | `/agent-results/{result_id}` | 查询单条 agent 采集结果 |
| Agent Result | GET | `/agent-results/download` | 下载 agent 采集结果 CSV |

## Agent 登录

`POST /agent-login/start`

请求体：

```json
{
  "phone": "13800000000",
  "account_id": "18251956205"
}
```

响应 `data`：

```json
{
  "session_id": "uuid-hex",
  "status": "queued",
  "ws_endpoint": "/api/v1/agent-login/{session_id}/events"
}
```

`POST /agent-login/{session_id}/code`

请求体：

```json
{"code": "123456"}
```

`POST /agent-login/{session_id}/cancel`

响应 `data`：

```json
{"ok": true}
```

WebSocket 事件包含 `sequence`、`event_type`、`status`、`message`、`current_url`、`page_title`、`screenshot_artifact_id`。

## Agent Discovery 与 Recipe

`POST /agent-discovery`

请求体：

```json
{
  "shop_id": "153514567",
  "account_id": "18251956205",
  "goal": "发现抖店体验分单页采集路径",
  "entrypoint_url": "https://fxg.jinritemai.com/tps/score/home",
  "namespace_hint": "douyin_shop_dashboard",
  "key_hint": "experience_score_single_page",
  "max_steps": 30
}
```

响应 `data`：

```json
{
  "run_id": "uuid-hex",
  "status": "queued",
  "event_sequence": 1
}
```

`WS /agent-discovery/{run_id}/events` 推送 queued、running、recipe_generated、run_finished、run_failed 等事件。终态事件出现后服务端关闭连接。

`POST /agent-discovery/recipes/{recipe_id}/mark-stable`

请求体：

```json
{"expected_version": 1}
```

`GET /agent-discovery/recipes/{recipe_id}/export`

返回 `format_version + recipe` JSON 文件，文件名为 `{namespace}_{key}_v{version}.agent-recipe.json`。

`POST /agent-discovery/recipes/import`

请求类型为 `multipart/form-data`，字段名为 `file`，文件名必须以 `.agent-recipe.json` 结尾。重复的 `(namespace, key, version)` 返回 `409`。

## Agent Results

`GET /agent-results`

查询参数：

| 参数 | 必填 | 说明 |
|---|---|---|
| `namespace` | 否 | recipe/result 命名空间 |
| `resource_key` | 否 | 资源标识，抖店场景为 `shop_id` |
| `date_from` | 否 | 开始日期 |
| `date_to` | 否 | 结束日期 |
| `page` | 否 | 默认 `1` |
| `size` | 否 | 默认 `50`，最大 `200` |

响应 `data`：

```json
{
  "items": [
    {
      "id": 1,
      "namespace": "douyin_shop_dashboard",
      "resource_key": "153514567",
      "resource_date": "2026-05-15",
      "recipe_id": 2,
      "output": {},
      "status": "succeeded",
      "error_message": null,
      "created_at": "2026-05-24T00:00:00Z",
      "updated_at": "2026-05-24T00:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 50
}
```

`GET /agent-results/{result_id}` 返回单条记录。`GET /agent-results/download` 需要 `namespace`、`resource_key`、`date_from`、`date_to`，返回 CSV。

## 任务运行 payload 变化

`POST /tasks/{task_id}/run` 路径不变，`payload` 支持抖店采集覆盖项：

| 字段 | 说明 |
|---|---|
| `shop_id` | 单店采集 |
| `shop_ids` | 多店采集 |
| `all` | 全店采集 |
| `time_range` | `{ "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" }` |
| `extra_config.agent_recipe` | `{ "namespace": "...", "key": "...", "version": 1 }` |
| `extra_config.agent_discovery` | discovery 模式标记，限制单店 |
| `extra_config.agent_recipe_validation` | recipe 验证模式，限制单店 |
| `extra_config.agent_recipe_recovery` | recipe 修复模式，限制单店 |

多店或全店 agent 批量采集要求 recipe 已标记为 `stable`。否则任务返回 `agent_recipe_missing_for_batch` 或 `agent_recipe_not_stable_for_batch`。

## 持久化变化

新增 `agent_recipes`：

| 字段 | 说明 |
|---|---|
| `namespace` / `key` / `version` | recipe 版本定位 |
| `status` | `active`、`degraded`、`disabled` |
| `stability` | `candidate`、`stable` |
| `entrypoint`、`steps`、`observations`、`assertions` | 可执行 recipe |
| `recovery_policy`、`security_policy` | 修复与安全策略 |

新增 `agent_collection_results`：

| 字段 | 说明 |
|---|---|
| `namespace` | 业务命名空间 |
| `resource_key` | 资源标识 |
| `resource_date` | 数据日期 |
| `recipe_id` | 对应 recipe |
| `output` | agent 原始输出 JSON |
| `status` / `error_message` | 采集结果 |

## 迁移注意点

1. 前端需要新增登录和 discovery 的 WebSocket 事件消费。
2. recipe 从候选到批量可用必须显式调用 `mark-stable`。
3. 原有 `shop_dashboard_scores` 仍保留聚合查询用途，agent 原始输出从 `agent_collection_results` 查询。
4. 新增迁移文件包括 `20260515_01_add_agent_recipe_table.py`、`20260521_01_add_agent_recipe_stability.py`、`20260521_03_add_agent_collection_results.py`。
