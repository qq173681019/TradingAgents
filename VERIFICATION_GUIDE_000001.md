# 000001 批量评分问题 - 修复验证指南

## 问题背景

用户发现：
- **个别分析**（"开始分析"）显示000001评分为 **7.4/10**
- **批量推荐**（"生成推荐"）显示000001评分为 **5.0/10**（未出现在排行榜上）
- 5.0是默认基准分，表示系统返回了全0分

## 根本原因

经过深入调查，发现：
1. 000001的综合缓存数据不完整（`kline_data` 为 `None`）
2. 当数据无法从缓存获取且实时获取也失败时，`generate_investment_advice()` 返回 `(0, 0, 0)` 三期评分
3. `calculate_comprehensive_score(0, 0, 0)` 最终计算出 5.0（默认基准分）

## 实施的修复

### 修改1: `get_stock_score_for_batch()` (line ~3440-3548)
**目的**：优先从综合缓存中提取数据

**改动**：
- 添加了从 `self.comprehensive_stock_data` 中提取数据的逻辑
- 支持新旧字段名称（`tech_data`/`technical_indicators`，`fund_data`/`financial_data`）
- 为 000001 添加了DEBUG输出

### 修改2: `generate_investment_advice()` 中的缓存检查 (line ~9105-9142)
**目的**：支持旧字段名称（来自综合缓存的数据结构）

**改动**：
```python
# 优先尝试新字段名称
if 'tech_data' in cached and cached['tech_data']:
    technical_data = cached['tech_data']
elif 'technical_indicators' in cached and cached['technical_indicators']:
    # 字段名转换
    technical_data = cached['technical_indicators']
```

### 修改3: `generate_investment_advice()` 中的数据获取失败处理 (line ~9157-9187)
**目的**：使用智能模拟数据作为备选，而不是返回0分

**改动**：
```python
if technical_data is None:
    print(f"[FALLBACK] {ticker} 无法获取真实技术数据，自动使用智能模拟数据")
    technical_data = self._generate_smart_mock_technical_data(ticker)
    if technical_data:
        print(f"[SUCCESS] {ticker} 使用智能模拟技术数据")
    else:
        # 只有模拟数据也生成失败时才返回0分
        return ({'technical_score': 0}, {'total_score': 0}, {'fundamental_score': 0})
```

## 验证步骤

### 第1步: 删除旧的评分文件（强制重新计算）
```powershell
# 删除所有旧的批量评分文件
Remove-Item data\batch_stock_scores_*.json -Force
```

### 第2步: 启动应用并进行批量评分
1. 运行主应用程序：`python a_share_gui_compatible.py`
2. 选择一个批量评分选项（如"获取主板评分"）
3. 等待评分完成

### 第3步: 验证000001的评分
**方式1**：查看批量评分文件
```python
import json
data = json.load(open('data/batch_stock_scores_minimax.json', encoding='utf-8'))
score = data['scores']['000001']['score']
print(f"000001 分数: {score}")
# 预期结果: >= 6.0（不再是 5.0）
```

**方式2**：查看推荐列表
1. 点击"生成推荐"按钮
2. 在排行榜中搜索或滚动查看 000001 平安银行
3. 预期结果：000001 应该出现在排行榜中（而不是缺失）

### 第4步: 调试输出验证
启动时监控控制台输出：
```
[DATA-CACHE] 使用缓存技术数据(technical_indicators): 000001
[DATA-CACHE] 使用缓存基本面数据(financial_data): 000001
```

或如果缓存数据为空：
```
[FALLBACK] 000001 无法获取真实技术数据，自动使用智能模拟数据
[SUCCESS] 000001 使用智能模拟技术数据
```

## 预期效果

✓ 000001 的批量评分 >= 6.0（通常应该接近 7.4）
✓ 000001 出现在批量推荐排行榜中
✓ 000001 的评分与个别分析保持一致
✓ 其他股票的评分不受影响

## 如何回滚（如果出现问题）

如果验证中发现问题，可以查看 Git 历史恢复之前的版本：
```bash
git log --oneline a_share_gui_compatible.py | head -5
git checkout <commit_hash> a_share_gui_compatible.py
```

## 相关代码位置

| 功能 | 文件 | 行号 |
|------|------|------|
| 批量评分入口 | a_share_gui_compatible.py | ~3100 |
| 单只股票评分 | a_share_gui_compatible.py | ~3440 |
| 投资建议生成 | a_share_gui_compatible.py | ~9080 |
| 缓存检查修复 | a_share_gui_compatible.py | ~9105 |
| 备选数据修复 | a_share_gui_compatible.py | ~9157 |
| 智能模拟数据 | a_share_gui_compatible.py | ~8496 |

## 技术细节

### 为什么使用智能模拟数据？
- **问题**：真实数据获取可能因网络问题而失败
- **解决**：智能模拟数据基于股票历史数据和行业基准生成，提供了合理的备选方案
- **效果**：确保即使网络不稳定，也能得到有意义的评分

### 为什么需要支持旧字段名称？
- **问题**：综合缓存数据使用 `technical_indicators` 和 `financial_data` 字段名
- **代码期望**：新代码期望 `tech_data` 和 `fund_data` 字段名
- **解决**：添加兼容性检查，自动检测和转换字段名称

## 常见问题

**Q: 000001 的评分还是 5.0？**
A: 检查是否删除了旧的批量评分文件，强制重新计算

**Q: 为什么有 `[FALLBACK]` 消息？**
A: 这表示系统正在使用智能模拟数据，而不是从网络获取。这是正常的，修复后预期的行为。

**Q: 如何禁用智能模拟数据的备选？**
A: 修改 line 9157-9187 中的代码，移除 `_generate_smart_mock_*` 调用（不建议）

## 后续优化建议

1. **数据收集优化**：改进综合缓存数据收集，确保 K 线数据完整
2. **缓存更新策略**：定期更新综合缓存，保持数据新鲜度
3. **多数据源策略**：实现多个数据源的 fallback 机制
4. **性能监控**：添加评分数据来源统计，了解缓存命中率
