# API Model 参数口径说明

本文记录 `xiaocao` CLI 对小草 API 中 `model` 参数的当前理解。这里的结论来自 live API 多日返回形态对比，不是官方枚举文档；如果后端口径变化，应以 e2e 测试和实际返回为准。

## 涉及接口

- `/stock/xiao_cao_industry_block_rank`
- `/stock/xiao_cao_block_category_rank_v3`

两个接口都接受 `model` 参数，但返回形态不完全一样。

## 当前推断

| model | 推断名称 | 行业方向表现 | 大类方向表现 | 推荐用途 |
|---:|---|---|---|---|
| `0` | 全量强度排行 | 返回完整行业方向排行，`num` 基本连续非零 | 返回完整大类方向排行，`num` 基本连续非零 | 报告展示、方向总览 |
| `1` | 短线重点 / 精选口径 | 非常稀疏，经常只有 0-3 个非零方向 | 返回部分大类，`num` 通常是 0.x 的归一化小数 | 策略方向加持、精选方向判断 |
| `2` | 全量强度排行别名 | 当前观察与 `model=0` 基本一致 | 当前观察与 `model=0` 基本一致 | 暂不做差异化依赖 |
| `3` | 全量强度排行别名 | 当前观察与 `model=0` 基本一致 | 当前观察与 `model=0` 基本一致 | 暂不做差异化依赖 |

## 证据摘要

最近多个交易日观察到：

- 行业方向 `model=0/2/3`：每天约 14-20 条，基本全部 `num != 0`。
- 行业方向 `model=1`：每天约 14-20 条，但非零方向通常只有 0-3 条。
- 大类方向 `model=0/2/3`：每天约 48-54 条，基本全部 `num != 0`。
- 大类方向 `model=1`：每天约 16-25 条，`num` 多为 `0.6`、`0.8`、`0.9` 这类小数。

因此：

- `model=0` 更像连续强度排名。
- `model=1` 更像短线重点、精选、或归一化热度口径。
- `model=2/3` 目前表现为 `model=0` 的兼容别名或预留参数。

## CLI 使用策略

当前 CLI 采用以下策略：

- 报告里的“强方向”使用 `industry_block_rank model=0`，避免把 `model=1` 中大量 `0` 强度方向误展示成 Top5。
- 策略内部默认使用配置项 `strategy.block_model=1`，因为精选口径适合做方向加持条件。
- 报告里的“强方向大类”使用 `category_rank model=0`。
- `model=2/3` 暂不承担独立业务语义。

## 推荐命名

代码或文档中建议使用语义名称，而不是裸数字：

```text
RANK_MODEL_FULL         -> model=0
RANK_MODEL_FOCUS        -> model=1
RANK_MODEL_FULL_ALIAS_2 -> model=2
RANK_MODEL_FULL_ALIAS_3 -> model=3
```

如果后续 CLI 要暴露更友好的参数，可以新增：

```bash
xiaocao block rank --rank-model full
xiaocao block rank --rank-model focus
```

并保留 `--model` 作为底层透传参数。
