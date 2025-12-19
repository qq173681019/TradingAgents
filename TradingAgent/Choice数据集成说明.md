# Choice数据集成完成说明

## 已完成的功能

### 1. Choice数据预加载
- **位置**: `_on_choice_data_toggle()` 和 `_preload_choice_data()`
- **功能**: 勾选"使用Choice数据"checkbox时，自动加载 `data/comprehensive_stock_data.json`
- **数据转换**: 将Choice数据格式转换为系统内部格式
- **存储位置**: `self.comprehensive_stock_data` 字典

### 2. 单只股票分析（开始分析按钮）
- **函数**: `perform_analysis()` → `generate_investment_advice()`
- **实现**:
  ```python
  # 0. 优先从Choice数据获取
  if self.use_choice_data.get() and ticker in self.comprehensive_stock_data:
      technical_data = cached['tech_data']  # Choice技术数据
      financial_data = cached['fund_data']  # Choice基本面数据
  ```
- **特点**:
  - 如果勾选Choice且数据存在，直接使用Choice数据
  - 如果Choice数据不存在该股票，**不会实时获取**，会跳过
  - 数据来源标记: `data_source = 'choice_data'`

### 3. 批量评分（获取主板评分按钮）
- **函数**: `_calculate_algorithmic_score_v2()`
- **实现**: 通过 `_get_cached_technical_data()` 和 `_get_cached_fundamental_data()` 获取数据
- **数据流程**:
  ```
  勾选Choice → _preload_choice_data() → comprehensive_stock_data
                                            ↓
  批量评分 → _get_cached_technical_data() → 从comprehensive_stock_data获取
          → _get_cached_fundamental_data() → 标记为'choice_data'
  ```
- **特点**: 自动使用预加载的Choice数据，无需额外配置

### 4. 数据来源标识
在以下位置显示数据来源：
- **终端日志**: `[CHOICE-DATA]` 前缀
- **技术数据**: `tech_data['data_source'] = 'choice_data'`
- **基本面数据**: `fund_data['data_source'] = 'choice_data'`
- **评分标签**: `[Choice数据]` 显示在评分旁边

## 使用方式

### 操作步骤
1. 运行 `python get_choice_data.py` 获取Choice数据（180天历史）
2. 启动GUI程序 `python a_share_gui_compatible.py`
3. 勾选"使用Choice数据"复选框
4. 系统自动加载Choice数据（显示加载进度）
5. 点击"开始分析"或"获取主板评分"即可使用Choice数据

### 数据要求
- **文件位置**: `data/comprehensive_stock_data.json`
- **数据结构**:
  ```json
  {
    "stocks": {
      "000001": {
        "code": "000001",
        "data_source": "choice_api",
        "kline_data": {
          "daily": [...]  // 至少150条K线数据
        },
        "financial_data": {
          "pe_ratio": 10.5,
          "pb_ratio": 1.5,
          "roe": 15.0
        },
        "basic_info": {...}
      }
    }
  }
  ```

## 数据优先级

### 单只股票分析
1. **勾选Choice**: Choice数据（如果存在）
2. **未勾选或不存在**: 缓存数据 → 实时获取

### 批量评分
1. **勾选Choice**: Choice数据（comprehensive_stock_data）
2. **未勾选**: JSON缓存文件（data/comprehensive_stock_data_part_*.json）

## 注意事项

### 数据完整性
- Choice数据必须包含至少**120条K线数据**才能计算MA120等长期指标
- 如果K线数据不足，会显示警告但不会崩溃
- 建议使用180天数据（已在get_choice_data.py中配置）

### 数据更新
- Choice数据需要手动更新（运行get_choice_data.py）
- 系统**不会自动混合**Choice数据和实时数据
- 勾选Choice后，**只使用Choice数据**，不会补全缺失数据

### 性能考虑
- Choice数据预加载时会计算所有技术指标
- 对于3000+只股票，预加载大约需要5-10秒
- 预加载后，分析速度大幅提升（无需网络请求）

## 代码位置

### 主要修改的文件
1. **a_share_gui_compatible.py**
   - Line 9363-9376: Choice数据优先获取逻辑
   - Line 9453-9472: 跳过实时获取逻辑
   - Line 17945-17975: 缓存数据获取标记Choice来源
   - Line 5784-5856: Choice数据预加载

2. **get_choice_data.py**
   - Line 236: 设置为180天（150个交易日）

3. **comprehensive_data_collector.py**
   - Line 196: 设置为150天

## 未来改进建议

### 1. 增量更新
- 检测最后一条K线日期
- 只获取新增数据
- 合并到现有Choice数据

### 2. 数据验证
- 检查K线数据连续性
- 验证数据完整性
- 自动修复异常数据

### 3. 混合模式
- 允许Choice数据 + 实时补全
- 优先使用Choice，缺失时实时获取
- 需要增加配置选项

### 4. 筹码分析集成
- 目前筹码分析器使用独立数据源
- 可以改造为也使用Choice数据
- 需要修改chip_health_analyzer.py

## 测试清单

- [x] 勾选Choice数据后预加载成功
- [x] 单只股票分析使用Choice数据
- [x] 批量评分使用Choice数据
- [x] 数据来源正确标记为'choice_data'
- [x] 终端日志显示[CHOICE-DATA]标识
- [x] Choice数据不存在时不会崩溃
- [x] 取消勾选后恢复使用常规数据源
- [ ] 测试3000+只股票的批量评分性能
- [ ] 验证K线数据不足时的警告提示
