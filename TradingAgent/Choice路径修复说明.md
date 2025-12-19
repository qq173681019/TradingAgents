# Choice数据路径修复说明

## 修复时间
2025-12-19 15:00

## 问题
- Choice复选框无法勾选
- 原因：数据文件路径还指向旧的 data/ 目录

## 修复内容

### 1. a_share_gui_compatible.py
-  _preload_choice_data(): 修复为使用共享数据目录
-  _test_choice_wrapper(): 修复为使用共享数据目录

### 2. get_choice_data.py
-  output_file: 修复输出路径到共享数据目录

## 修复后的路径
所有Choice数据现在统一保存和读取位置：
```
D:\TradingAgents\TradingShared\data\comprehensive_stock_data.json
```

## 验证
 共享目录中已有Choice数据文件
 包含3013只股票
 数据源: choice_api
 收集时间: 2025-12-14

## 使用说明
1. 重启程序
2. 勾选"使用Choice数据"复选框
3. 系统会自动加载共享目录中的Choice数据
4. 如需更新Choice数据，运行 get_choice_data.py 即可

---
现在Choice复选框应该可以正常勾选了！