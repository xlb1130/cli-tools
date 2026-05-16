# Token 追踪

## 目标

量化自动化执行的模型成本，支撑优化、限额和问题排查。

## 采集字段

- `task_id`
- `skill`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `model`
- `timestamp`

## 使用原则

- 成本统计应与任务、阶段、模型绑定。
- 分析成本时同时看效果，不只看 token 总量。
- 发现异常高消耗时，应回溯上下文大小和重复调用。

## 典型场景

- 统计单任务成本。
- 识别高消耗场景。
- 对比不同策略的成本收益。
