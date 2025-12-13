# py_mini_racer 崩溃问题修复说明

## 问题描述
在使用akshare获取股票数据时，程序崩溃并显示以下错误：
```
Failed to open startup resource 'snapshot_blob.bin'
Fatal error in , line 0
Failed to deserialize the V8 snapshot blob.
```

## 原因分析
1. **akshare依赖问题**: `akshare.stock_zh_a_hist` 和 `akshare.stock_zh_a_daily` 依赖 `py_mini_racer` 包
2. **py_mini_racer问题**: 这是一个V8 JavaScript引擎的Python绑定，在某些环境下不稳定
3. **触发条件**: 
   - 用户名包含中文字符（路径编码问题）
   - Windows系统路径问题
   - py_mini_racer包损坏或版本不兼容

## 解决方案
**完全禁用akshare的相关功能**，使用其他稳定的数据源：

### 已修改的文件

#### 1. chip_health_analyzer.py
- ❌ 禁用: `akshare.stock_zh_a_hist` (东方财富源)
- ❌ 禁用: `akshare.stock_zh_a_daily` (新浪源)
- ✅ 使用: 腾讯财经API、Baostock等其他稳定数据源

#### 2. a_share_gui_compatible.py
- ❌ 禁用: line 8771-8785 的 `ak.stock_zh_a_hist` 调用
- ✅ 使用: 其他优先级更高的数据源（Tushare、腾讯等）

#### 3. comprehensive_data_collector.py  
- ❌ 禁用: line 1073 主数据源的akshare调用
- ❌ 禁用: line 1252 替代处理的akshare调用
- ❌ 禁用: line 1315 兜底处理的akshare调用
- ✅ 使用: 腾讯、Baostock、JoinQuant等稳定数据源

## 数据源优先级（修复后）

### 筹码健康度分析 (chip_health_analyzer.py)
1. ~~akshare.stock_zh_a_hist~~ (已禁用)
2. ~~akshare.stock_zh_a_daily~~ (已禁用)
3. **腾讯财经API** ⭐ (现为首选)
4. **Baostock** (备选)
5. **缓存数据** (兜底)

### K线数据获取 (comprehensive_data_collector.py)
1. **腾讯K线API** (主数据源)
2. **JoinQuant** (如果配置)
3. ~~AKShare~~ (已禁用)
4. **Baostock** (兜底)

### 实时行情 (a_share_gui_compatible.py)
1. **Tushare** (如果有token)
2. **腾讯API**
3. **Baostock**
4. ~~AKShare~~ (已禁用)

## 测试确认
修复后，请测试以下场景：
- [ ] 单只股票分析（000001）
- [ ] 筹码健康度计算
- [ ] 批量评分
- [ ] K线数据获取

所有测试应该不再出现py_mini_racer崩溃错误。

## 如果仍需使用akshare
如果确实需要使用akshare的某些功能，请：

### 方案1: 修复py_mini_racer（不推荐）
```bash
pip uninstall py_mini_racer -y
pip install py_mini_racer --force-reinstall
```

### 方案2: 更换用户名（不现实）
- 将Windows用户名改为纯英文
- 或创建新的英文用户账号

### 方案3: 使用其他akshare功能
akshare中不依赖py_mini_racer的函数仍然可以安全使用：
- `ak.stock_zh_a_spot_em()` - 实时行情（不使用JavaScript）
- `ak.stock_individual_info_em()` - 股票基本信息
- 其他不涉及历史数据的功能

## 相关资源
- py_mini_racer GitHub: https://github.com/sqreen/PyMiniRacer
- akshare文档: https://akshare.akfamily.xyz/
- 相关Issue: py_mini_racer在Windows中文用户名下崩溃是已知问题
