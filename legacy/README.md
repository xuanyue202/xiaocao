# 旧脚本归档

这个目录保留重构前的脚本入口，方便追溯历史逻辑和 API 调用方式。它们不再作为日常入口维护，也不建议在新功能里继续引用。

## 当前入口

日常使用请走新的 `xiaocao` CLI：

- `stock_recommend.py` / `today_gogogo.py` -> `xiaocao strategy run`、`xiaocao report premarket`、`xiaocao report afterclose`
- `xiaocao_api.py` -> `src/xiaocao/api/client.py`
- `xiaocao_file.py` -> `src/xiaocao/datasource/local_source.py`
- `stock_dynamic_index.py` -> `xiaocao index dynamic`
- `stock_industry_block.py` -> `xiaocao block rank`
- `stock_block_category_v2.py` -> `xiaocao block category-rank`
- `stock_env.py` -> `xiaocao market environment`
- `stock_details.py` -> `xiaocao index stock`
- `get_stock.py` -> `xiaocao data pool`

## 维护原则

- 归档脚本只用于查证，不再补新能力。
- 新代码不要从 `legacy/scripts` import。
- 如果发现旧脚本里还有有价值逻辑，先迁移到 `src/xiaocao` 的对应模块，再补测试。
