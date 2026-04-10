# -*- coding: utf-8 -*-
"""
个股新闻情绪分析模块

功能：
1. 获取个股近期新闻（支持多个数据源）
2. 使用DeepSeek LLM分析新闻情绪
3. 批量分析多只股票的新闻情绪

依赖：
- akshare: 新闻数据获取
- requests: HTTP请求
- DeepSeek API: 情绪分析
"""

import os
import sys
import json
import time
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

# 设置路径以导入共享配置
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TradingShared'))

try:
    from config import (
        DEEPSEEK_API_KEY,
        DEEPSEEK_API_URL,
        DEEPSEEK_MODEL_NAME,
        AI_TEMPERATURE,
        AI_MAX_TOKENS,
        API_TIMEOUT
    )
except ImportError:
    # 如果无法导入，使用默认值
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL_NAME = "deepseek-chat"
    AI_TEMPERATURE = 0.3
    AI_MAX_TOKENS = 500
    API_TIMEOUT = 60


class NewsAnalyzer:
    """个股新闻情绪分析器

    支持从多个数据源获取个股新闻，并使用LLM分析新闻情绪。

    Attributes:
        api_key: DeepSeek API密钥
        api_url: DeepSeek API地址
        model_name: 使用的模型名称
        request_delay: 请求间隔时间（秒）
        max_retries: 最大重试次数
    """

    def __init__(self, api_key: str = None, api_url: str = None, model_name: str = None):
        """初始化新闻分析器

        Args:
            api_key: DeepSeek API密钥，默认从配置文件读取
            api_url: DeepSeek API地址，默认从配置文件读取
            model_name: 模型名称，默认从配置文件读取
        """
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.api_url = api_url or DEEPSEEK_API_URL
        self.model_name = model_name or DEEPSEEK_MODEL_NAME
        self.request_delay = 1.0  # 请求间隔1秒
        self.max_retries = 2  # 最大重试2次

        if not self.api_key:
            print("警告: DeepSeek API密钥未配置，将返回中性评分")

    def fetch_stock_news(self, stock_code: str, stock_name: str, days: int = 7, count: int = 10) -> List[Dict]:
        """获取个股近期新闻

        优先使用akshare，失败时尝试东方财富API。

        Args:
            stock_code: 股票代码（如 '600000' 或 '600000.SH'）
            stock_name: 股票名称（如 '浦发银行'）
            days: 获取最近几天的新闻
            count: 获取新闻数量

        Returns:
            新闻列表，每条新闻包含 {title, content, date, source, url}
        """
        # 方案1: 优先使用akshare
        news = self._fetch_news_akshare(stock_code, stock_name, count)
        if news:
            print(f"[akshare] 获取到 {len(news)} 条新闻")
            return news[:count]

        # 方案2: 东方财富API
        news = self._fetch_news_eastmoney(stock_name, count)
        if news:
            print(f"[东方财富] 获取到 {len(news)} 条新闻")
            return news[:count]

        print(f"未获取到 {stock_name}({stock_code}) 的新闻")
        return []

    def _fetch_news_akshare(self, stock_code: str, stock_name: str, count: int = 10) -> List[Dict]:
        """使用akshare获取个股新闻

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            count: 获取数量

        Returns:
            新闻列表
        """
        try:
            import akshare as ak

            # 尝试多种akshare接口
            news_list = []

            # 方法1: 东方财富个股新闻（推荐）
            try:
                df = ak.stock_news_em(symbol=stock_name)
                if df is not None and not df.empty:
                    for _, row in df.head(count).iterrows():
                        news_list.append({
                            'title': row.get('新闻标题', ''),
                            'content': row.get('新闻内容', row.get('新闻标题', '')),
                            'date': row.get('发布时间', ''),
                            'source': '东方财富',
                            'url': row.get('新闻链接', '')
                        })
            except Exception as e:
                print(f"[akshare] 东方财富接口失败: {e}")

            # 方法2: 腾讯财经新闻
            if not news_list:
                try:
                    df = ak.stock_news_tx(stock=stock_code)
                    if df is not None and not df.empty:
                        for _, row in df.head(count).iterrows():
                            news_list.append({
                                'title': row.get('title', ''),
                                'content': row.get('content', ''),
                                'date': row.get('time', ''),
                                'source': '腾讯财经',
                                'url': row.get('url', '')
                            })
                except Exception as e:
                    print(f"[akshare] 腾讯接口失败: {e}")

            return news_list

        except ImportError:
            print("[akshare] 未安装akshare库，请运行: pip install akshare")
            return []
        except Exception as e:
            print(f"[akshare] 获取新闻失败: {e}")
            return []

    def _fetch_news_eastmoney(self, stock_name: str, count: int = 10) -> List[Dict]:
        """通过东方财富搜索API获取新闻

        Args:
            stock_name: 股票名称
            count: 获取数量

        Returns:
            新闻列表
        """
        try:
            import requests
            import urllib.parse

            keyword = urllib.parse.quote(stock_name)
            url = (
                f"https://search-api-web.eastmoney.com/search/jsonp?"
                f"cb=jQuery&param={{"
                f"\"uid\":\"\","
                f"\"keyword\":\"{stock_name}\","
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

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=10)

            # 解析JSONP返回
            json_match = re.search(r'jQuery\((.*)\)', response.text)
            if not json_match:
                return []

            data = json.loads(json_match.group(1))

            news_list = []
            if 'data' in data and 'cmsArticleWebOld' in data['data']:
                articles = data['data']['cmsArticleWebOld']
                for article in articles:
                    news_list.append({
                        'title': article.get('title', ''),
                        'content': article.get('digest', article.get('title', '')),
                        'date': article.get('date_time', article.get('show_time', '')),
                        'source': article.get('media_name', '东方财富'),
                        'url': article.get('url', '')
                    })

            return news_list

        except Exception as e:
            print(f"[东方财富API] 获取新闻失败: {e}")
            return []

    def _call_deepseek_api(self, prompt: str, retry_count: int = 0) -> Optional[Dict]:
        """调用DeepSeek API

        Args:
            prompt: 提示词
            retry_count: 当前重试次数

        Returns:
            解析后的响应字典，失败返回None
        """
        if not self.api_key:
            return None

        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一位专业的A股投资分析师，擅长分析新闻对股价的影响。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": AI_TEMPERATURE,
                "max_tokens": AI_MAX_TOKENS
            }

            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=API_TIMEOUT
            )

            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                # 解析JSON响应
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # 尝试提取JSON部分
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            return json.loads(json_match.group())
                        except json.JSONDecodeError:
                            pass

                    # 解析失败，返回默认值
                    print(f"[LLM] 响应解析失败: {content[:100]}")
                    return {"sentiment": "中性", "score": 5.0, "reason": "LLM响应格式异常"}

            elif response.status_code == 429:
                # 限流，等待后重试
                if retry_count < self.max_retries:
                    print(f"[LLM] 请求限流，等待5秒后重试...")
                    time.sleep(5)
                    return self._call_deepseek_api(prompt, retry_count + 1)
                else:
                    print(f"[LLM] 达到最大重试次数")
                    return None

            else:
                print(f"[LLM] API请求失败: {response.status_code} - {response.text[:200]}")
                return None

        except Exception as e:
            print(f"[LLM] 调用异常: {e}")
            if retry_count < self.max_retries:
                print(f"[LLM] 等待后重试...")
                time.sleep(3)
                return self._call_deepseek_api(prompt, retry_count + 1)
            return None

    def analyze_sentiment(self, stock_name: str, news_list: List[Dict]) -> Dict:
        """使用DeepSeek LLM分析新闻情绪

        Args:
            stock_name: 股票名称
            news_list: 新闻列表

        Returns:
            分析结果 {sentiment, score, reason, news_analyzed}
        """
        if not news_list:
            return {
                "sentiment": "中性",
                "score": 5.0,
                "reason": "无新闻数据",
                "news_analyzed": 0
            }

        if not self.api_key:
            return {
                "sentiment": "中性",
                "score": 5.0,
                "reason": "API密钥未配置",
                "news_analyzed": len(news_list)
            }

        # 构建新闻摘要（限制长度避免超token）
        news_summary = ""
        for i, news in enumerate(news_list[:10], 1):  # 最多分析10条
            news_summary += f"\n{i}. 标题: {news.get('title', '无标题')}"
            if news.get('content'):
                content = news['content'][:100]  # 限制内容长度
                news_summary += f"\n   内容: {content}..."

        # 构建prompt
        prompt = f"""请分析以下关于{stock_name}的新闻，判断对股价的短期影响（1-3个交易日）。

新闻列表：{news_summary}

请按以下JSON格式回复：
{{
    "sentiment": "利好/利空/中性",
    "score": 数字（0-10），其中：
              - 8-10分：强利好，可能大幅上涨
              - 6-8分：利好，可能上涨
              - 4-6分：中性，影响有限
              - 2-4分：利空，可能下跌
              - 0-2分：强利空，可能大幅下跌
    "reason": "简要分析理由（50字以内）"
}}

注意：
1. 综合考虑所有新闻的整体影响
2. 区分新闻的重要性和时效性
3. 考虑市场情绪和预期差
4. 只返回JSON，不要其他内容"""

        result = self._call_deepseek_api(prompt)

        if result:
            # 验证评分范围
            score = result.get("score", 5.0)
            if not isinstance(score, (int, float)) or score < 0 or score > 10:
                score = 5.0

            return {
                "sentiment": result.get("sentiment", "中性"),
                "score": float(score),
                "reason": result.get("reason", "分析完成"),
                "news_analyzed": len(news_list)
            }

        # API失败返回中性
        return {
            "sentiment": "中性",
            "score": 5.0,
            "reason": "API调用失败",
            "news_analyzed": len(news_list)
        }

    def get_sentiment_score(self, stock_code: str, stock_name: str, days: int = 7) -> Dict:
        """获取单只股票的新闻情绪评分（0-10）

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            days: 获取最近几天的新闻

        Returns:
            {score: float, sentiment: str, reason: str, news_count: int}
        """
        print(f"\n[新闻分析] 开始分析 {stock_name}({stock_code})...")

        # 获取新闻
        news_list = self.fetch_stock_news(stock_code, stock_name, days)

        if not news_list:
            print(f"[新闻分析] 未获取到新闻，返回中性评分")
            return {
                "score": 5.0,
                "sentiment": "中性",
                "reason": "无近期新闻",
                "news_count": 0
            }

        # 分析情绪
        result = self.analyze_sentiment(stock_name, news_list)

        print(f"[新闻分析] 完成 - 情绪: {result['sentiment']}, 评分: {result['score']:.1f}/10")
        print(f"[新闻分析] 理由: {result['reason']}")

        return {
            "score": result["score"],
            "sentiment": result["sentiment"],
            "reason": result["reason"],
            "news_count": result["news_analyzed"]
        }

    def batch_analyze(self, stocks: List[Dict], days: int = 7) -> List[Dict]:
        """批量分析多只股票的新闻情绪

        Args:
            stocks: 股票列表，每只股票包含 {code, name, ...}
            days: 获取最近几天的新闻

        Returns:
            带sentiment_score的股票列表
        """
        results = []
        total = len(stocks)

        print(f"\n[批量分析] 开始分析 {total} 只股票的新闻情绪...")

        for i, stock in enumerate(stocks, 1):
            stock_code = stock.get('code', stock.get('symbol', ''))
            stock_name = stock.get('name', '')

            if not stock_code or not stock_name:
                print(f"[批量分析] 跳过无效股票: {stock}")
                continue

            print(f"[批量分析] 进度: {i}/{total}")

            # 获取情绪评分
            sentiment_result = self.get_sentiment_score(stock_code, stock_name, days)

            # 合并结果
            stock_with_sentiment = stock.copy()
            stock_with_sentiment.update({
                'sentiment_score': sentiment_result['score'],
                'sentiment': sentiment_result['sentiment'],
                'sentiment_reason': sentiment_result['reason'],
                'news_count': sentiment_result['news_count']
            })

            results.append(stock_with_sentiment)

            # 请求间隔避免限流
            if i < total:
                time.sleep(self.request_delay)

        print(f"\n[批量分析] 完成！共分析 {len(results)} 只股票")
        return results

    def save_results(self, results: List[Dict], filename: str = None) -> str:
        """保存分析结果到文件

        Args:
            results: 分析结果列表
            filename: 保存文件名，默认自动生成

        Returns:
            保存的文件路径
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"news_sentiment_{timestamp}.json"

        # 确保使用共享数据目录
        shared_data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'TradingShared',
            'data'
        )
        os.makedirs(shared_data_dir, exist_ok=True)

        filepath = os.path.join(shared_data_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"[保存] 结果已保存到: {filepath}")
        return filepath

    def load_cached_results(self, filename: str) -> List[Dict]:
        """加载缓存的分析结果

        Args:
            filename: 缓存文件名

        Returns:
            缓存的结果列表
        """
        shared_data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'TradingShared',
            'data'
        )
        filepath = os.path.join(shared_data_dir, filename)

        if not os.path.exists(filepath):
            return []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[缓存] 加载失败: {e}")
            return []


# 便捷函数
def analyze_single_stock(stock_code: str, stock_name: str) -> Dict:
    """分析单只股票的新闻情绪（便捷函数）

    Args:
        stock_code: 股票代码
        stock_name: 股票名称

    Returns:
        {score, sentiment, reason, news_count}
    """
    analyzer = NewsAnalyzer()
    return analyzer.get_sentiment_score(stock_code, stock_name)


def analyze_multiple_stocks(stocks: List[Dict]) -> List[Dict]:
    """批量分析多只股票的新闻情绪（便捷函数）

    Args:
        stocks: 股票列表，每只包含 {code, name}

    Returns:
        带sentiment_score的股票列表
    """
    analyzer = NewsAnalyzer()
    return analyzer.batch_analyze(stocks)


# 测试代码
if __name__ == "__main__":
    # 单股测试
    print("=" * 50)
    print("单股新闻情绪分析测试")
    print("=" * 50)

    result = analyze_single_stock("600519", "贵州茅台")
    print(f"\n结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # 批量测试
    print("\n" + "=" * 50)
    print("批量新闻情绪分析测试")
    print("=" * 50)

    test_stocks = [
        {"code": "600519", "name": "贵州茅台"},
        {"code": "000858", "name": "五粮液"},
        {"code": "600036", "name": "招商银行"},
    ]

    results = analyze_multiple_stocks(test_stocks)

    print("\n批量分析结果:")
    for stock in results:
        print(f"{stock['name']}({stock['code']}): "
              f"{stock['sentiment']} {stock['sentiment_score']:.1f}分 - "
              f"{stock['sentiment_reason']}")
