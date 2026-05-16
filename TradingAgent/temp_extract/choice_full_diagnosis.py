"""Choice API 全面诊断测试 - 基于 Hermes 报告验证"""
import os, sys, json, time
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared')
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared\api')

from EmQuantAPI import c
from config import CHOICE_USERNAME, CHOICE_PASSWORD

print("=" * 70)
print("Choice API 全面诊断")
print("=" * 70)

# ========== 登录 ==========
print("\n[0] 登录测试")
r = c.start(f"USERNAME={CHOICE_USERNAME},PASSWORD={CHOICE_PASSWORD}")
print(f"  ErrorCode: {r.ErrorCode}")
print(f"  ErrorMsg: {r.ErrorMsg}")
if r.ErrorCode != 0:
    print("  登录失败，退出")
    sys.exit(1)
print("  ✅ 登录成功")

# ========== 1. CSD (时序K线) ==========
print("\n" + "=" * 70)
print("[1] CSD - 时序K线")
print("=" * 70)

# 1a. 单只基础K线
print("\n[1a] 单只 OHLCV (5天)")
d = c.csd("000001.SZ", "OPEN,HIGH,LOW,CLOSE,VOLUME", "2026-05-06", "2026-05-09", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0:
    print(f"  ✅ Dates: {d.Dates}")
    if hasattr(d, 'Data') and '000001.SZ' in d.Data:
        print(f"  Data: CLOSE={d.Data['000001.SZ'][3]}")
else:
    print(f"  ❌ 失败")

# 1b. 扩展指标
print("\n[1b] 单只扩展指标 (TURN, CHGPCT, AMOUNT)")
d = c.csd("000001.SZ", "CLOSE,VOLUME,TURN,CHGPCT,AMOUNT", "2026-05-06", "2026-05-09", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0:
    for i, ind in enumerate(d.Indicators):
        vals = d.Data.get('000001.SZ', [[]])[i] if '000001.SZ' in d.Data else []
        has_data = any(v is not None for v in vals) if vals else False
        status = "✅" if has_data else "❌ None"
        print(f"  {status} {ind}: {vals}")
else:
    print(f"  ❌ 失败")

# 1c. 估值指标
print("\n[1c] 估值指标 (PE, PB, PS)")
d = c.csd("000001.SZ", "CLOSE,PE,PB,PS", "2026-05-06", "2026-05-09", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0:
    for i, ind in enumerate(d.Indicators):
        vals = d.Data.get('000001.SZ', [[]])[i] if '000001.SZ' in d.Data else []
        has_data = any(v is not None for v in vals) if vals else False
        status = "✅" if has_data else "❌ None"
        print(f"  {status} {ind}: {vals}")
else:
    print(f"  ❌ 失败")

# 1d. 60天数据
print("\n[1d] 60天历史K线")
d = c.csd("000001.SZ", "OPEN,HIGH,LOW,CLOSE,VOLUME", "2026-02-01", "2026-05-09", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0:
    print(f"  ✅ Days: {len(d.Dates)}")
else:
    print(f"  ❌ 失败")

# 1e. 另一只股票
print("\n[1e] 另一只股票 600519.SH (贵州茅台)")
d = c.csd("600519.SH", "CLOSE,VOLUME", "2026-05-06", "2026-05-09", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0:
    print(f"  ✅ Data: {d.Data.get('600519.SH', [])}")
else:
    print(f"  ❌ 失败")

# ========== 2. CSS (截面数据) ==========
print("\n" + "=" * 70)
print("[2] CSS - 截面数据")
print("=" * 70)

# 2a. 单只单字段 - Hermes说这个可以
print("\n[2a] 单只单字段 CLOSE (Hermes说可以)")
d = c.css("000001.SZ", "CLOSE", "", "", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0 and hasattr(d, 'Data'):
    print(f"  ✅ Data: {d.Data}")
else:
    print(f"  ❌ 失败")

# 2b. 单只多字段
print("\n[2b] 单只多字段 OPEN,HIGH,LOW,CLOSE")
d = c.css("000001.SZ", "OPEN,HIGH,LOW,CLOSE", "", "", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0 and hasattr(d, 'Data'):
    print(f"  ✅ Data: {d.Data}")
else:
    print(f"  ❌ 失败")

# 2c. 带日期参数
print("\n[2c] 单只 CLOSE + tradeDate参数")
d = c.css("000001.SZ", "CLOSE", "TradeDate=2026-05-08", "", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0 and hasattr(d, 'Data'):
    print(f"  ✅ Data: {d.Data}")
else:
    print(f"  ❌ 失败")

# 2d. PE/PB
print("\n[2d] PE,PB")
d = c.css("000001.SZ", "PE,PB", "", "", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0 and hasattr(d, 'Data'):
    print(f"  ✅ Data: {d.Data}")
else:
    print(f"  ❌ 失败")

# 2e. 多只股票
print("\n[2e] 多只股票 CLOSE")
d = c.css("000001.SZ,600036.SH", "CLOSE", "", "", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0 and hasattr(d, 'Data'):
    print(f"  ✅ Data: {d.Data}")
else:
    print(f"  ❌ 失败")

# 2f. 各种其他字段
print("\n[2f] 其他字段逐一测试")
for field in ["SEC_NAME", "INDUSTRY", "VOLUME", "TURN", "CHGPCT", "AMOUNT", "TOTALMV", "NEGOTIABLEMV", "EPS", "BPS", "ROE"]:
    d = c.css("000001.SZ", field, "", "", "")
    ok = d.ErrorCode == 0
    data = d.Data if ok else None
    has_real = False
    if ok and hasattr(d, 'Data') and isinstance(d.Data, dict):
        for k, v in d.Data.items():
            if v is not None and v != '' and v != []:
                has_real = True
                break
    status = "✅" if has_real else "❌"
    print(f"  {status} {field}: ErrorCode={d.ErrorCode}, Data={d.Data if ok else d.ErrorMsg}")
    time.sleep(0.3)

# ========== 3. CFC (财务数据) ==========
print("\n" + "=" * 70)
print("[3] CFC - 财务指标 (Hermes说 funtype=css)")
print("=" * 70)

# 3a. 基础CFC
print("\n[3a] CFC 基础测试 ROE")
d = c.cfc("000001.SZ", "ROE", "2026-03-31", "", "", "funtype=css")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0 and hasattr(d, 'Data'):
    print(f"  ✅ Data: {d.Data}")
else:
    print(f"  ❌ 失败")

# 3b. PE/PB via CFC
print("\n[3b] CFC PE,PB,EPS")
d = c.cfc("000001.SZ", "PE,PB,EPS,BPS", "2026-03-31", "", "", "funtype=css")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0 and hasattr(d, 'Data'):
    print(f"  ✅ Data: {d.Data}")
else:
    print(f"  ❌ 失败")

# 3c. 不带 funtype
print("\n[3c] CFC 不带 funtype=css")
d = c.cfc("000001.SZ", "ROE", "2026-03-31", "", "", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0 and hasattr(d, 'Data'):
    print(f"  ✅ Data: {d.Data}")
else:
    print(f"  ❌ 失败")

# 3d. 更多财务指标
print("\n[3d] CFC 更多指标")
for field in ["NETPROFIT", "REVENUE", "GROSSPROFITMARGIN", "CURRENT", "QUICK", "DEBTASSET"]:
    d = c.cfc("000001.SZ", field, "2026-03-31", "", "", "funtype=css")
    ok = d.ErrorCode == 0
    has_data = ok and hasattr(d, 'Data') and d.Data and any(v is not None for v in str(d.Data) if v)
    status = "✅" if ok else "❌"
    val = d.Data if ok else d.ErrorMsg
    print(f"  {status} {field}: {val}")
    time.sleep(0.3)

# ========== 4. SECTOR (板块成分) ==========
print("\n" + "=" * 70)
print("[4] SECTOR - 板块成分")
print("=" * 70)

# 4a. 按文档顺序
print("\n[4a] sector('2026-05-08', '001') (文档顺序)")
try:
    d = c.sector("2026-05-08", "001")
    print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
    if d.ErrorCode == 0:
        print(f"  ✅ Count: {len(d.Data) if hasattr(d, 'Data') else 'N/A'}")
    else:
        print(f"  ❌ 失败")
except Exception as e:
    print(f"  ❌ Exception: {e}")

# 4b. 参数互换 (Hermes说这样才行)
print("\n[4b] sector('001', '2026-05-08') (参数互换)")
try:
    d = c.sector("001", "2026-05-08")
    print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
    if d.ErrorCode == 0:
        print(f"  ✅ Count: {len(d.Data) if hasattr(d, 'Data') else 'N/A'}")
        if hasattr(d, 'Data') and d.Data:
            print(f"  Sample: {str(d.Data)[:200]}")
    else:
        print(f"  ❌ 失败")
except Exception as e:
    print(f"  ❌ Exception: {e}")

# 4c. 更多板块代码
print("\n[4c] 其他板块代码")
for code, desc in [("001", "深证成指"), ("003", "上证成指"), ("8011", "银行"), ("001004", "主板")]:
    try:
        d = c.sector(code, "2026-05-08")
        ok = d.ErrorCode == 0
        cnt = len(d.Data) if ok and hasattr(d, 'Data') else 0
        status = "✅" if ok else "❌"
        print(f"  {status} {code} ({desc}): {cnt} stocks, ErrorMsg={d.ErrorMsg if not ok else 'OK'}")
    except Exception as e:
        print(f"  ❌ {code} ({desc}): Exception {e}")

# ========== 5. TRADEDATES (交易日) ==========
print("\n" + "=" * 70)
print("[5] TRADEDATES - 交易日")
print("=" * 70)

try:
    d = c.tradedates("2026-05-01", "2026-05-10")
    print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
    if d.ErrorCode == 0:
        print(f"  ✅ Dates: {d.Data if hasattr(d, 'Data') else 'N/A'}")
    else:
        print(f"  ❌ 失败")
except Exception as e:
    print(f"  ❌ Exception: {e}")

# ========== 6. CHQ (实时K线) ==========
print("\n" + "=" * 70)
print("[6] CHQ - 实时K线")
print("=" * 70)

d = c.chq("000001.SZ", "2026-05-08", "", "")
print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
if d.ErrorCode == 0 and hasattr(d, 'Data'):
    print(f"  ✅ Data: {str(d.Data)[:200]}")
else:
    print(f"  ❌ 失败")

# ========== 7. CSES (历史成分) ==========
print("\n" + "=" * 70)
print("[7] CSES - 历史成分")
print("=" * 70)

print("\n[7a] cses 标准板块代码")
try:
    d = c.cses("B0010001", "date,wind_code,sec_name", "2026-05-08", "2026-05-08", "")
    print(f"  ErrorCode: {d.ErrorCode} ({d.ErrorMsg})")
    if d.ErrorCode == 0:
        print(f"  ✅ Data: {str(d.Data)[:200] if hasattr(d, 'Data') else 'N/A'}")
    else:
        print(f"  ❌ 失败")
except Exception as e:
    print(f"  ❌ Exception: {e}")

# ========== 总结 ==========
print("\n" + "=" * 70)
print("诊断完成")
print("=" * 70)

c.stop()
print("已断开连接")
