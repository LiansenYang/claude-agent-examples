---
name: weather
description: 天气查询技能，能查询任意城市的实时天气状况
tags: 天气, 气象, weather, forecast
---

# 天气查询指南

## 推荐的天气 API

使用 **wttr.in** 纯文本天气服务，无需 API Key。

## 查询格式

```
https://wttr.in/{城市英文名}?format=j1
```

参数说明：
- `{城市英文名}`：城市英文名称，如 London, Beijing, Tokyo
- `format=j1`：返回 JSON 格式数据

## 返回数据解析

JSON 结构如下：
- `current_condition[0].temp_C`：摄氏温度
- `current_condition[0].weatherDesc[0].value`：天气描述（晴/多云/雨等）
- `current_condition[0].humidity`：湿度百分比
- `current_condition[0].windspeedKmph`：风速（km/h）
- `current_condition[0].feelsLikeC`：体感温度

## 使用步骤

1. 将城市名翻译为英文
2. 调用 `web_fetch` 工具，URL 使用上述格式，设置 `extract_mode` 为 `"raw"`
3. 解析返回的 JSON 数据
4. 将结果用中文回复给用户
