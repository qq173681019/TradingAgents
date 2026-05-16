"""09:00 每日国际行情快报（含邮件推送）"""
import sys, requests, re, os
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')

s = requests.Session()
s.trust_env = False

results = []

def sina(code, name, price_idx=1, chg_idx=2):
    try:
        r = s.get(f'https://hq.sinajs.cn/list={code}', timeout=10,
                  headers={'Referer': 'https://finance.sina.com.cn/'})
        if r.status_code == 200:
            r.encoding = 'gbk'
            raw = r.text
            m = re.search(r'"(.+)"', raw)
            if m and m.group(1):
                parts = m.group(1).split(',')
                try:
                    price = float(parts[price_idx])
                    chg_pct = float(parts[chg_idx])
                    sign = '+' if chg_pct >= 0 else ''
                    line = f'{name}: {price:,.2f} ({sign}{chg_pct:.2f}%)'
                    print(line)
                    results.append((name, f'{price:,.2f}', f'{sign}{chg_pct:.2f}%'))
                except (ValueError, IndexError):
                    print(f'{name}: 盘中暂无')
            else:
                print(f'{name}: 盘中暂无')
        else:
            print(f'{name}: HTTP {r.status_code}')
    except Exception as e:
        print(f'{name}: {str(e)[:50]}')

today = datetime.now().strftime('%Y-%m-%d')
print(f'=== 每日国际行情 {today} ===')
print()

# 美股隔夜收盘
sina('gb_dji', '🇺🇸 道琼斯')
sina('gb_ixic', '🇺🇸 纳斯达克')
sina('gb_inx', '🇺🇸 标普500')

# 亚太（恒生指数rt格式特殊）
try:
    r = s.get('https://hq.sinajs.cn/list=rt_hkHSI', timeout=10,
              headers={'Referer': 'https://finance.sina.com.cn/'})
    r.encoding = 'gbk'
    m = re.search(r'"(.+)"', r.text)
    if m and m.group(1):
        parts = m.group(1).split(',')
        price = float(parts[3])
        # 计算涨跌：用昨收(parts[14])和当前价
        prev_close = float(parts[14]) if len(parts) > 14 else 0
        chg_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
        sign = '+' if chg_pct >= 0 else ''
        line = f'🇭🇰 恒生指数: {price:,.2f} ({sign}{chg_pct:.2f}%)'
        print(line)
        results.append(('🇭🇰 恒生指数', f'{price:,.2f}', f'{sign}{chg_pct:.2f}%'))
except Exception as e:
    print(f'🇭🇰 恒生指数: {str(e)[:50]}')
sina('b_NKY', '🇯🇵 日经225', 1, 3)
sina('b_KOSPI', '🇰🇷 韩国KOSPI', 1, 3)

print()

# 汇率
usdcny = '数据暂无'
try:
    r = s.get('https://hq.sinajs.cn/list=fx_susdcny', timeout=10,
              headers={'Referer': 'https://finance.sina.com.cn/'})
    r.encoding = 'gbk'
    m = re.search(r'"(.+)"', r.text)
    if m and m.group(1):
        parts = m.group(1).split(',')
        usdcny = parts[1]
        print(f'💱 美元/人民币: {usdcny}')
except:
    pass

# 黄金
try:
    r = s.get('https://hq.sinajs.cn/list=hf_GC', timeout=10,
              headers={'Referer': 'https://finance.sina.com.cn/'})
    r.encoding = 'gbk'
    m = re.search(r'"(.+)"', r.text)
    if m and m.group(1):
        parts = m.group(1).split(',')
        gold = float(parts[0])
        print(f'🥇 COMEX黄金: {gold:,.2f} USD')
        results.append(('🥇 COMEX黄金', f'{gold:,.2f} USD', ''))
except:
    pass

# === 邮件推送 ===
if results:
    rows = ''
    for name, price, chg in results:
        color = '#e74c3c' if '-' in chg else '#2ecc71'
        rows += f'<tr><td>{name}</td><td style="text-align:right">{price}</td><td style="color:{color};text-align:right">{chg}</td></tr>\n'

    html = f'''
    <html><body style="font-family: Arial, sans-serif; max-width: 500px;">
    <h3>📈 每日国际行情 {today}</h3>
    <table style="border-collapse:collapse; width:100%;">
    <tr style="background:#f0f0f0;"><th style="padding:6px;text-align:left">指数</th><th style="padding:6px;text-align:right">点位</th><th style="padding:6px;text-align:right">涨跌%</th></tr>
    {rows}
    </table>
    <p>💱 美元/人民币: {usdcny}</p>
    <hr style="border:none;border-top:1px solid #eee;">
    <p style="color:#999;font-size:12px;">小呆 AI · 每日定时推送</p>
    </body></html>
    '''

    sys.path.insert(0, r'C:\Users\admin\.openclaw\workspace')
    from notify import notify_email
    notify_email(f'📈 每日国际行情 {today}', html)
