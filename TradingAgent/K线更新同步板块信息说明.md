# K线更新时同步采集板块信息 - 功能说明

## 更新日期：2026-01-13

## 背景
之前在更新K线数据时，只更新K线和技术指标，不更新板块信息（行业、概念等）。这导致在后续分析热门板块时，需要重新获取板块数据，增加了不必要的API调用和等待时间。

## 解决方案
在 `update_kline_data_only` 方法中，增加了智能板块信息采集功能：

### 1. 智能判断是否需要更新
系统会自动检查每个股票是否需要更新板块信息：
- 新股票：需要采集
- 缺失板块信息：需要采集
- 行业信息为空：需要采集
- 使用默认值的：尝试获取真实数据

### 2. 批量高效采集
- 使用 `collect_batch_industry_concept` 批量采集板块信息
- Baostock 提供标准行业分类（一次性获取全量映射）
- AKShare 补充热门概念（但在批量模式下会跳过，避免API限制）

### 3. 自动保存到数据文件
更新后的板块信息会自动保存到每个股票的 `industry_concept` 字段中：
```json
{
  "industry_concept": {
    "code": "000001",
    "source": "baostock",
    "industry": "银行",
    "industry_name": "银行业",
    "sector": "金融业",
    "concepts": ["金融科技", "数字货币", ...],
    "industry_update_date": "2026-01-13"
  }
}
```

## 主要修改文件
- `TradingShared/api/comprehensive_data_collector.py`
  - `update_kline_data_only()`: 添加板块信息采集逻辑
  - `collect_batch_industry_concept()`: 优化批量模式下的概念查询策略

## 优化细节

### 1. 避免重复采集
```python
# 只更新需要的股票
codes_need_industry = []
for code in batch_codes:
    if code not in existing_data or 'industry_concept' not in existing_data[code]:
        codes_need_industry.append(code)
    elif existing_data[code]['industry_concept'].get('source') in ['default', 'baostock_default']:
        codes_need_industry.append(code)  # 使用默认值，尝试获取真实数据
```

### 2. 批量模式优化
```python
# 超过10只股票时，跳过AKShare概念查询（避免API限制）
skip_concepts = len(concept_codes) > 10
if skip_concepts:
    print(f"批量更新模式：跳过AKShare概念查询，仅更新行业信息")
```

### 3. 数据合并策略
```python
# 更新现有股票数据
if code in batch_industry_data:
    existing_data[code]['industry_concept'] = batch_industry_data[code]
```

## 使用示例

### 运行K线更新（会自动采集板块信息）
```python
from TradingShared.api.comprehensive_data_collector import ComprehensiveDataCollector

collector = ComprehensiveDataCollector()
collector.update_kline_data_only(batch_size=100, stock_type='主板', exclude_st=True)
```

### 查看更新后的板块信息
```python
existing_data = collector.load_existing_data()
stock = existing_data['000001']
print(f"行业: {stock['industry_concept']['industry']}")
print(f"板块: {stock['industry_concept']['sector']}")
print(f"概念: {stock['industry_concept']['concepts']}")
```

## 性能优势

### 之前的流程
1. 更新K线数据（100批次）
2. 分析热门板块时，重新获取板块信息（需要额外API调用）

### 现在的流程
1. 更新K线数据 + 同步更新板块信息（一次完成）
2. 分析热门板块时，直接使用已有数据（无需API调用）

### 效果
- **减少API调用**：避免重复获取板块信息
- **提升性能**：热门板块分析无需等待数据获取
- **降低失败率**：减少API调用次数，降低触发限制的风险

## 测试验证
运行测试脚本验证功能：
```bash
python test_kline_industry_update.py
```

## 注意事项
1. **BaoStock依赖**：需要安装 BaoStock 才能获取详细的行业分类
   ```bash
   pip install baostock
   ```

2. **概念查询限制**：批量更新（>10只股票）时会跳过概念查询，避免触发AKShare API限制

3. **数据更新策略**：只更新缺失或使用默认值的股票，已有真实数据的股票不会重复采集

4. **向后兼容**：不影响现有数据结构，只是增加了 `industry_concept` 字段的更新

## 后续优化建议
1. 可以考虑定期（如每月）全量更新一次板块信息，确保数据准确性
2. 可以添加板块信息的时效性检查，超过一定时间自动更新
3. 可以考虑缓存板块映射关系，进一步提升性能
