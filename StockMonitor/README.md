# StockMonitor - 股票实时监控系统

## 项目简介
实时监控A股分时数据，提供1分钟K线图表展示。

## 依赖资源
- **共享API**: `D:\TradingShared\api\`
  - EmQuantAPI.py (Choice API)
  - 其他数据源API
  
- **共享数据**: `D:\TradingShared\data\`
  - 缓存数据文件

## 启动方式
1. 双击 `启动股票监控.bat`
2. 或运行: `python stock_monitor.py`

## 功能特性
- 实时分时图展示
- 1分钟K线图
- 多数据源支持 (Choice/AKShare/Tushare)
- 自动刷新机制

## 配置
- 默认股票代码: 600519
- 用户名密码在代码中配置
- Choice连接信息: CHOICE_USER, CHOICE_PASS

## 技术栈
- tkinter (GUI)
- mplfinance (K线图)
- pandas (数据处理)
- matplotlib (图表渲染)
