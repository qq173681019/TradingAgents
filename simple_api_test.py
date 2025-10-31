import urllib.request
import time

def test_data_sources():
    ticker = "600519"  # 贵州茅台
    print(f"测试股票: {ticker}")
    
    # 测试新浪财经
    try:
        code = f"sh{ticker}"
        url = f"http://hq.sinajs.cn/list={code}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=5)
        data = response.read().decode('gbk', errors='ignore')
        
        if 'var hq_str_' in data:
            parts = data.split('="')[1].split('",')[0].split(',')
            if len(parts) > 3 and parts[3]:
                price = float(parts[3])
                print(f"新浪财经: {price}")
    except Exception as e:
        print(f"新浪财经失败: {e}")
    
    time.sleep(1)
    
    # 测试腾讯财经
    try:
        code = f"sh{ticker}"
        url = f"http://qt.gtimg.cn/q={code}"
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://finance.qq.com'}
        
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=5)
        data = response.read().decode('gbk', errors='ignore')
        
        if f'v_{code}=' in data:
            parts = data.split('="')[1].split('"')[0].split('~')
            if len(parts) > 3 and parts[3]:
                price = float(parts[3])
                print(f"腾讯财经: {price}")
    except Exception as e:
        print(f"腾讯财经失败: {e}")

if __name__ == "__main__":
    test_data_sources()