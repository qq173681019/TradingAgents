"""
QA 验收工具：从多个独立数据源获取K线数据，与缓存做交叉验证
数据源：
1. 东方财富 datacenter API (urllib，不走代理)
2. 新浪财经 API
3. 腾讯财经 API (if available)
"""
import json
import os
import ssl
import urllib.request
import urllib.parse
import random
import time
from datetime import datetime

KLINE_PATH = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def fetch_em_kline(code: str, days: int = 5):
    """东方财富行情API获取最近N天K线"""
    # 判断市场
    if code.startswith('6'):
        secid = f"1.{code}"
    else:
        secid = f"0.{code}"
    
    url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        'secid': secid,
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
        'klt': '101',  # 日K
        'fqt': '1',    # 前复权
        'end': '20500101',
        'lmt': str(days),
    }
    url_full = url + "?" + urllib.parse.urlencode(params)
    
    try:
        req = urllib.request.Request(url_full, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        klines = data.get("data", {}).get("klines", [])
        result = []
        for k in klines:
            parts = k.split(",")
            if len(parts) >= 7:
                result.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                })
        return result
    except Exception as e:
        return [{"error": str(e)}]


def fetch_sina_kline(code: str, days: int = 5):
    """新浪财经API获取最近N天K线"""
    # 判断市场前缀
    if code.startswith('6'):
        prefix = 'sh'
    else:
        prefix = 'sz'
    
    url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData"
    params = {
        'symbol': f'{prefix}{code}',
        'scale': '240',  # 日K
        'datalen': str(days),
    }
    url_full = url + "?" + urllib.parse.urlencode(params)
    
    try:
        req = urllib.request.Request(url_full, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn"
        })
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            text = resp.read().decode("utf-8")
        
        # Sina returns JSONP: =([...])
        text = text.strip()
        if text.startswith('=') or text.startswith('var'):
            # Extract JSON array
            start = text.index('[')
            end = text.rindex(']') + 1
            data = json.loads(text[start:end])
        
        result = []
        for item in data:
            result.append({
                "date": item.get("day", ""),
                "open": float(item.get("open", 0)),
                "close": float(item.get("close", 0)),
                "high": float(item.get("high", 0)),
                "low": float(item.get("low", 0)),
                "volume": float(item.get("volume", 0)),
            })
        return result
    except Exception as e:
        return [{"error": str(e)}]


def compare_data(cache_rec: dict, source_rec: dict, tolerance: float = 0.01):
    """比较两条K线记录，允许 tolerance 百分比的误差"""
    mismatches = []
    for field in ["open", "close", "high", "low"]:
        cv = cache_rec.get(field)
        sv = source_rec.get(field)
        if cv is None or sv is None:
            continue
        diff = abs(cv - sv)
        pct = diff / sv if sv > 0 else 0
        if pct > tolerance:
            mismatches.append(f"{field}: cache={cv:.2f} vs source={sv:.2f} (diff={pct*100:.2f}%)")
    
    # 成交量允许更大误差（不同数据源计算口径不同）
    cv_vol = cache_rec.get("volume", 0)
    sv_vol = source_rec.get("volume", 0)
    if cv_vol > 0 and sv_vol > 0:
        vol_pct = abs(cv_vol - sv_vol) / sv_vol
        if vol_pct > 0.1:  # 10% tolerance for volume
            mismatches.append(f"volume: cache={cv_vol:.0f} vs source={sv_vol:.0f} (diff={vol_pct*100:.1f}%)")
    
    return mismatches


def qa_verify(sample_size: int = 30):
    """QA 验收主流程"""
    print("=" * 70)
    print("QA 验收：K线数据交叉验证")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 加载缓存
    with open(KLINE_PATH, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    
    # 随机抽样：优先选沪深主板，最新日期为 2026-06-13 的
    candidates = []
    for key in cache:
        if key.startswith(('sh6', 'sz000', 'sz002', 'sz300', 'sz301')):
            recs = cache[key]
            if recs and recs[-1].get('date', '') >= '2026-06-10':
                candidates.append(key)
    
    sample = random.sample(candidates, min(sample_size, len(candidates)))
    print(f"\n候选池: {len(candidates)} 只, 抽样: {len(sample)} 只\n")
    
    results = []
    total_checks = 0
    total_matches = 0
    mismatches_detail = []
    
    for key in sample:
        code = key[2:]  # remove sh/sz prefix
        cache_recs = sorted(cache[key], key=lambda x: x['date'])
        cache_last3 = cache_recs[-3:] if len(cache_recs) >= 3 else cache_recs
        
        # 从东方财富获取
        em_data = fetch_em_kline(code, days=5)
        
        if isinstance(em_data, list) and em_data and 'error' not in em_data[0]:
            for cache_rec in cache_last3:
                date = cache_rec['date']
                # 找对应日期的源数据
                em_match = None
                for em_rec in em_data:
                    if em_rec['date'] == date:
                        em_match = em_rec
                        break
                
                if em_match:
                    total_checks += 1
                    mm = compare_data(cache_rec, em_match)
                    if mm:
                        mismatches_detail.append({
                            "code": code,
                            "date": date,
                            "source": "EastMoney",
                            "mismatches": mm,
                        })
                    else:
                        total_matches += 1
            
            status = "✅" if not any(m['code'] == code for m in mismatches_detail) else "❌"
            last_close = cache_last3[-1].get('close', '?') if cache_last3 else '?'
            last_date = cache_last3[-1].get('date', '?') if cache_last3 else '?'
            print(f"  {status} {code}  最后: {last_date} C:{last_close}")
        else:
            err = em_data[0].get('error', 'unknown') if em_data else 'empty'
            print(f"  ⚠️  {code}  东财获取失败: {err}")
            # Try Sina as backup
            sina_data = fetch_sina_kline(code, days=5)
            if isinstance(sina_data, list) and sina_data and 'error' not in sina_data[0]:
                for cache_rec in cache_last3:
                    date = cache_rec['date']
                    sina_match = None
                    for s_rec in sina_data:
                        if s_rec['date'] == date:
                            sina_match = s_rec
                            break
                    if sina_match:
                        total_checks += 1
                        mm = compare_data(cache_rec, sina_match)
                        if mm:
                            mismatches_detail.append({
                                "code": code,
                                "date": date,
                                "source": "Sina",
                                "mismatches": mm,
                            })
                        else:
                            total_matches += 1
                status = "✅" if not any(m['code'] == code for m in mismatches_detail) else "❌"
                print(f"  {status} {code} (新浪验证)")
        
        time.sleep(0.3)  # rate limit
    
    # 汇总
    accuracy = total_matches / total_checks * 100 if total_checks > 0 else 0
    print(f"\n{'=' * 70}")
    print(f"QA 验收报告")
    print(f"{'=' * 70}")
    print(f"抽样股票: {len(sample)} 只")
    print(f"交叉验证记录数: {total_checks}")
    print(f"匹配: {total_matches}")
    print(f"不匹配: {total_checks - total_matches}")
    print(f"准确率: {accuracy:.1f}%")
    
    if mismatches_detail:
        print(f"\n不匹配详情:")
        for m in mismatches_detail:
            print(f"  {m['code']} {m['date']} ({m['source']}):")
            for mm in m['mismatches']:
                print(f"    {mm}")
    else:
        print(f"\n✅ 全部匹配！数据准确率 100%")
    
    return accuracy == 100.0


if __name__ == "__main__":
    import sys
    sample = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    success = qa_verify(sample)
    sys.exit(0 if success else 1)
