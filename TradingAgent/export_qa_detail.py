"""
导出 QA 验证明细，供用户手动核对
"""
import json
import ssl
import urllib.request

KLINE_PATH = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

with open(KLINE_PATH, 'r', encoding='utf-8') as f:
    cache = json.load(f)

# QA验收员抽样的30只（seed=42）
import random
random.seed(42)
candidates = [k for k in cache if k.startswith(('sh6', 'sz000', 'sz002', 'sz300', 'sz301')) and cache[k] and cache[k][-1].get('date', '') >= '2026-06-10']
sample = random.sample(candidates, 30)

print("=" * 90)
print("QA 验证明细 — 30只随机抽样股票")
print("缓存数据 vs 腾讯财经实时行情")
print("最新交易日: 2026-06-12")
print("=" * 90)
print()
print(f"{'代码':<10} {'名称':<8} {'日期':<12} {'缓存Open':>10} {'缓存High':>10} {'缓存Low':>10} {'缓存Close':>10} {'缓存Vol':>12}")
print("-" * 90)

for key in sorted(sample):
    recs = sorted(cache[key], key=lambda x: x['date'])
    last = recs[-1]
    code = key[2:]
    
    # 获取名称
    name = ""
    score_file = r'D:\GitHub\TradingAgents\TradingShared\data\batch_stock_scores_optimized_主板_20260601_204416.json'
    with open(score_file, 'r', encoding='utf-8') as f:
        scores = json.load(f)
    if code in scores:
        name = scores[code].get('name', '')
    
    print(f"{code:<10} {name:<8} {last['date']:<12} {last.get('open',0):>10.2f} {last.get('high',0):>10.2f} {last.get('low',0):>10.2f} {last.get('close',0):>10.2f} {last.get('volume',0):>12.0f}")

print()
print("=" * 90)
print("手动验证方法：")
print("1. 打开东方财富/同花顺/雪球，搜索代码查看6/12收盘价")
print("2. 对比上面的 缓存Close 列")
print("3. 重点验证: 603267=62.20  002594=91.60  601012=13.46")
print("=" * 90)
