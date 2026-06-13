# Choice API 诊断报告

**诊断时间**: 2026-06-10 01:19 ~ 01:22 (Asia/Shanghai)  
**诊断工程师**: OpenClaw Subagent

---

## 🔴 根本原因：Choice API 账号已过期

**错误码**: `10001004`  
**错误信息**: `user access for this API expired`  
**SDK日志**: `login fail: code:170`

账号 `hczq2048` 的 Choice API 访问权限已过期，无法通过任何方式调用数据接口。

---

## 诊断过程

### Step 1: 基础环境检查 ✅

| 检查项 | 结果 | 状态 |
|--------|------|------|
| `C:\veighna_studio\python.exe` 存在 | 存在 | ✅ |
| `EmQuantAPI` 模块导入 | 导入成功 | ✅ |
| `ChoicePython` 模块 | 不存在（不需要，项目用的是 EmQuantAPI） | ℹ️ |
| Choice 终端安装 | Choice 9.7.0.3 已安装 (`C:\Eastmoney\Choice\`) | ✅ |
| Choice 终端进程 | **未运行**（无任何 Choice 相关进程） | ⚠️ |

### Step 2: 运行现有测试脚本 ✅

| 测试脚本 | 结果 |
|----------|------|
| `test_choice_data.py` | 所有测试返回 `success: False`，在 test[3] 处因 GBK 编码错误崩溃 |
| `test_choice_data2.py` | 未运行（test1 已确认问题） |

**根本原因一致**：所有失败均源于底层登录失败 `user access for this API expired`。

### Step 3: Worker 脚本检查 ✅

- `choice_worker.py` 使用 `EmQuantAPI` SDK（非 ChoicePython）
- 代码逻辑正确，有重试机制
- 登录失败时返回 `ErrorCode: 10001004`
- Worker 通过 `choice_api_wrapper.py` 以独立进程调用，隔离机制完善

### Step 4: 手动登录测试 ✅

```
直接调用 EmQuantAPI:
  c.start('UserName=hczq2048,Password=yo336999')
  
结果:
  ErrorCode: 10001004
  ErrorMsg: user access for this API expired
  SDK日志: login fail: code:170
```

### Step 5: Choice 终端状态 ✅

- Choice 终端 **未运行**（无进程）
- 终端安装路径: `C:\Eastmoney\Choice\`
- 主程序: `C:\Eastmoney\Choice\Choice.exe`
- 版本: 9.7.0.3
- EmQuantAPI 版本: V2.6.1.0

### Step 6: 错误分类

**分类结果**: **账号过期 (Account Expired)**

- ❌ 不是 SDK 模块缺失（EmQuantAPI 正常安装）
- ❌ 不是代码 Bug（Worker/Wrapper 逻辑正确）
- ❌ 不是终端未运行问题（即使启动终端，API 认证也会失败）
- ❌ 不是网络问题（已成功连接服务器，服务器返回过期信息）
- ✅ **是账号过期**：服务器明确返回 `user access for this API expired`

---

## 已有替代方案

项目中已有完善的替代方案文档 `CHOICE_API替代方案.md`：

### 当前可用数据源

| 数据源 | 状态 | 用途 |
|--------|------|------|
| **AKShare** | ✅ 可用 | A股实时行情、热门概念、财务数据 |
| **BaoStock** | ✅ 可用 | 历史K线数据 |
| **Tushare Pro** | ✅ 已配置 Token | 专业级补充数据 |
| **Choice API** | ❌ 已过期 | 需续费才能使用 |

### config.py 配置

```python
ENABLE_CHOICE = True  # 当前为启用状态
CHOICE_USERNAME = "hczq2048"
CHOICE_PASSWORD = "yo336999"
TUSHARE_TOKEN = "4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28"
```

---

## 建议操作

### 方案 A: 续费 Choice API（如需专业数据）
1. 联系东方财富销售续费账号 `hczq2048`
2. 续费后无需修改任何代码，直接可用
3. 建议同时启动 Choice 终端 `C:\Eastmoney\Choice\Choice.exe`

### 方案 B: 继续使用免费替代方案（推荐）
1. 将 `config.py` 中 `ENABLE_CHOICE = False` 避免无效尝试
2. 系统已有 AKShare + BaoStock + Tushare 的完整替代方案
3. 现有 BAT 文件已支持自动 fallback 到免费数据源

### 方案 C: 混合方案
1. 日常使用 AKShare + BaoStock
2. 需要高精度数据时临时续费 Choice
3. Tushare Pro 作为专业数据补充

---

## 环境信息汇总

```
Python: C:\veighna_studio\python.exe (VeighNa Studio)
EmQuantAPI: V2.6.1.0 (已安装, pip package: choice 0.1)
Choice 终端: 9.7.0.3 (C:\Eastmoney\Choice\)
账号: hczq2048
错误: 10001004 - user access for this API expired (code:170)
```

---

**结论**: Choice API 不能用是因为**账号已过期**，非技术问题。系统已有完善的免费替代方案（AKShare + BaoStock + Tushare），可以正常工作。如需继续使用 Choice，需联系东方财富续费。
