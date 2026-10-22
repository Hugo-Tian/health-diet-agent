# 食物库来源与复现

当前参考库包含 79 个明确品种、生熟状态的食物条目，覆盖主食、肉鱼蛋豆、蔬菜、水果、乳品、坚果和油脂。不是完整中国食物成分表，也不是餐馆复合菜的配方数据库。

## 权威原始来源

- USDA FoodData Central 官方下载页：https://fdc.nal.usda.gov/download-datasets/
- SR Legacy，2018 年 4 月最终版本：https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_json_2018-04.zip
- 官方数据使用说明（公共领域 / CC0）：https://fdc.nal.usda.gov/api-guide/
- 下载归档 SHA-256：`0fe8ae486a2c8eb42cb96413f058deb51863a46c8fb8eeb4b1fb45006dd338ef`

选择 SR Legacy 是为了使用稳定、覆盖常见食物且可复现的版本；它不是 2026 年新测定数据。每条保留 FDC ID、NDB 编号、英文原名、原始详情链接、数据版本、检索日期、原始营养证据与单位。中文名称、分类及保守过敏标签由本项目整理，不能冒充 USDA 的过敏认证。

## 数值及单位

所有数值从官方 JSON 抽取，不由 DeepSeek 填写。每 100g 可食部记录能量（kcal）、蛋白质、碳水化合物、脂肪、膳食纤维（g）以及钠、钙、铁、钾（mg）。导入脚本按 USDA 营养素 ID 和单位验证；缺失值保留 null。份量换算使用 `每100g数值 × 可食部克数 / 100`，生重与熟重不能混用。

USDA 的 Carbohydrate, by difference 是差减法碳水，包含膳食纤维，不等同于中国营养标签的可利用碳水。美国品种、强化工艺和家用量规格与本地可能不同。食品标签或已知配方更具体时，应按明确来源另建条目，不能直接覆盖原条目。

库内除 100g 称重单位外，家用量只取原始 USDA portion 的 gramWeight，保留英文单位和来源，不把一杯/一碗臆定为统一重量。复合面包成分可能不完整，标记未知过敏原，禁止自动推荐。

## 复现及更新

在项目根目录下载上述官方 ZIP 后执行：

```powershell
.\.venv\Scripts\python.exe backend/scripts/build_food_catalog.py work/nutrition/sr-legacy.zip
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.seed
```

脚本验证归档哈希，生成 `backend/data/usda_catalog.json`；运行时无需 USDA API Key。导入幂等；有变化时提高用户数据修订号，让旧草案失效。旧 demo 食物停用，历史计划和实际记录快照保持原值并显示“历史演示值”。不会用新库悄悄重算旧记录。更新前应备份数据库。

## 照片记录

DeepSeek 仅识别食物、估计份量并匹配库 ID。后端从库计算营养，低置信度、复合菜及不明用油不强行匹配。未匹配条目营养未知。照片结果先保存为 pending，用户核对食物、克数、时间、是否吃完后才计入摄入。照片本身不会保存在应用数据库或聊天历史中。
