"""
板块新闻抓取器 - 从东方财富获取今日热门板块相关新闻

数据源:
1. 东方财富板块行情 (涨幅TOP板块)
2. 东方财富新闻搜索 (板块关键词搜索)
3. AKShare 财经新闻 (fallback)
"""

import json
import re
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# 创建共享 Session，禁用环境代理避免 WinError 10022
_session = None
def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.trust_env = False
        _session.headers.update(HEADERS)
    return _session

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.eastmoney.com/',
}


class SectorNewsFetcher:
    """板块新闻抓取"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def fetch_hot_sectors_today(self, top_n: int = 10) -> List[Dict]:
        """
        获取今日涨幅TOP行业板块

        Returns:
            [{'name': '半导体', 'change': 3.5, 'lead_stock': 'xxx', ...}, ...]
        """
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1,
                'pz': top_n,
                'po': 1,  # 降序
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',  # 涨跌幅排序
                'fs': 'm:90+t:2+f:!50',  # 行业板块
                'fields': 'f2,f3,f4,f8,f12,f14',
            }
            resp = _get_session().get(url, params=params, headers=HEADERS, timeout=self.timeout)
            if resp.status_code != 200:
                return []

            data = resp.json()
            items = data.get('data', {}).get('diff', [])
            if not items:
                return []

            sectors = []
            for item in items:
                sectors.append({
                    'name': item.get('f14', ''),
                    'code': item.get('f12', ''),
                    'change_pct': item.get('f3', 0),
                    'price': item.get('f2', 0),
                    'turnover_rate': item.get('f8', 0),
                })

            return sectors

        except Exception as e:
            logger.warning(f"获取行业板块失败: {e}")
            return []

    def fetch_hot_concepts_today(self, top_n: int = 10) -> List[Dict]:
        """
        获取今日涨幅TOP概念板块
        """
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1,
                'pz': top_n,
                'po': 1,
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:90+t:3+f:!50',  # 概念板块
                'fields': 'f2,f3,f4,f8,f12,f14',
            }
            resp = _get_session().get(url, params=params, headers=HEADERS, timeout=self.timeout)
            if resp.status_code != 200:
                return []

            data = resp.json()
            items = data.get('data', {}).get('diff', [])
            if not items:
                return []

            concepts = []
            for item in items:
                concepts.append({
                    'name': item.get('f14', ''),
                    'code': item.get('f12', ''),
                    'change_pct': item.get('f3', 0),
                })

            return concepts

        except Exception as e:
            logger.warning(f"获取概念板块失败: {e}")
            return []

    def fetch_sector_news(self, keyword: str, count: int = 5) -> List[Dict]:
        """
        获取板块相关新闻

        Args:
            keyword: 板块关键词 (如 "半导体", "新能源")
            count: 获取数量

        Returns:
            [{'title': '...', 'content': '...', 'date': '...', 'source': '...'}, ...]
        """
        news = self._fetch_news_eastmoney_search(keyword, count)
        if news:
            return news

        # Fallback: AKShare
        return self._fetch_news_akshare(keyword, count)

    def fetch_market_news_today(self, count: int = 20) -> List[Dict]:
        """
        获取今日A股市场要闻（不针对特定板块）
        """
        news = []

        # 东方财富要闻
        try:
            url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
            params = {
                'client': 'web',
                'biz': 'web_news_col',
                'column': '350',
                'order': '1',
                'needInteractData': '0',
                'page_index': 1,
                'page_size': count,
            }
            resp = _get_session().get(url, params=params, headers=HEADERS, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('data', {}).get('newsList', [])
                for item in items:
                    news.append({
                        'title': item.get('title', ''),
                        'content': item.get('digest', ''),
                        'date': item.get('showTime', ''),
                        'source': item.get('source', '东方财富'),
                    })
        except Exception as e:
            logger.warning(f"获取市场要闻失败: {e}")

        return news

    def _fetch_news_eastmoney_search(self, keyword: str, count: int = 5) -> List[Dict]:
        """东方财富搜索API"""
        try:
            import urllib.parse
            url = (
                f"https://search-api-web.eastmoney.com/search/jsonp?"
                f"cb=jQuery&param={{"
                f"\"uid\":\"\","
                f"\"keyword\":\"{keyword}\","
                f"\"type\":[\"cmsArticleWebOld\"],"
                f"\"client\":\"web\","
                f"\"clientVersion\":\"curr\","
                f"\"param\":{{"
                f"\"cmsArticleWebOld\":{{"
                f"\"searchScope\":\"default\","
                f"\"sort\":\"default\","
                f"\"pageIndex\":1,"
                f"\"pageSize\":{count},"
                f"\"preTag\":\"\","
                f"\"postTag\":\"\""
                f"}}}}}}"
            )
            resp = _get_session().get(url, headers=HEADERS, timeout=self.timeout)
            json_match = re.search(r'jQuery\((.*)\)', resp.text)
            if not json_match:
                return []

            data = json.loads(json_match.group(1))
            news_list = []
            articles = data.get('data', {}).get('cmsArticleWebOld', [])
            for art in articles:
                news_list.append({
                    'title': art.get('title', ''),
                    'content': art.get('digest', ''),
                    'date': art.get('date_time', art.get('show_time', '')),
                    'source': art.get('media_name', ''),
                })
            return news_list

        except Exception as e:
            logger.debug(f"东方财富搜索失败({keyword}): {e}")
            return []

    def _fetch_news_akshare(self, keyword: str, count: int = 5) -> List[Dict]:
        """AKShare fallback"""
        try:
            import akshare as ak
            df = ak.stock_news_em(symbol=keyword)
            if df is None or df.empty:
                return []
            news = []
            for _, row in df.head(count).iterrows():
                news.append({
                    'title': row.get('新闻标题', ''),
                    'content': row.get('新闻内容', ''),
                    'date': row.get('发布时间', ''),
                    'source': '东方财富',
                })
            return news
        except Exception:
            return []


def fetch_all_for_analysis(top_sectors: int = 8, news_per_sector: int = 3,
                           market_news_count: int = 15) -> Dict:
    """
    一次性获取板块数据+新闻，供LLM分析

    Returns:
        {
            'hot_sectors': [...],
            'hot_concepts': [...],
            'sector_news': {sector_name: [news...], ...},
            'market_news': [...],
            'fetch_time': '...',
        }
    """
    fetcher = SectorNewsFetcher()
    t0 = time.time()

    # 1. 今日涨幅TOP行业
    hot_sectors = fetcher.fetch_hot_sectors_today(top_n=top_sectors)
    logger.info(f"热门行业: {len(hot_sectors)} 个")

    # 2. 今日涨幅TOP概念
    hot_concepts = fetcher.fetch_hot_concepts_today(top_n=top_sectors)
    logger.info(f"热门概念: {len(hot_concepts)} 个")

    # 3. 每个板块的关联新闻
    sector_news = {}
    all_keywords = [s['name'] for s in hot_sectors[:5]]  # 只查TOP5
    for kw in all_keywords:
        news = fetcher.fetch_sector_news(kw, count=news_per_sector)
        if news:
            sector_news[kw] = news
        time.sleep(0.3)  # 避免过快

    # 4. 市场要闻
    market_news = fetcher.fetch_market_news_today(count=market_news_count)

    elapsed = time.time() - t0
    return {
        'hot_sectors': hot_sectors,
        'hot_concepts': hot_concepts,
        'sector_news': sector_news,
        'market_news': market_news,
        'fetch_time': f'{elapsed:.1f}s',
    }
