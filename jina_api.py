import requests
import json
import time
import re
from typing import Dict, Any, List, Optional

class JinaAPI:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.base_url = "https://r.jina.ai/"
        self.search_url = "https://s.jina.ai/"
        
    def search(self, query: str) -> str:
        """使用Jina Search API搜索信息"""
        if not self.api_key:
            return "Error: API Key not provided"
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Retain-Images": "none"
        }
        
        try:
            # 对查询进行URL编码
            encoded_query = requests.utils.quote(query)
            url = f"{self.search_url}{encoded_query}"
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
            else:
                return f"Error: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Exception: {str(e)}"

    def read(self, url: str) -> str:
        """使用Jina Reader API读取网页内容"""
        if not self.api_key:
            return "Error: API Key not provided"
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Retain-Images": "none"
        }
        
        try:
            target_url = f"{self.base_url}{url}"
            response = requests.get(target_url, headers=headers)
            if response.status_code == 200:
                return response.text
            else:
                return f"Error: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Exception: {str(e)}"
            
    def get_stock_news(self, code: str, name: str) -> List[Dict[str, str]]:
        """获取股票相关新闻"""
        query = f"{name} {code} 最新财经新闻"
        search_result = self.search(query)
        
        if search_result.startswith("Error") or search_result.startswith("Exception"):
            print(f"[WARN] Jina Search failed: {search_result}")
            return []
        
        # 解析Markdown格式的搜索结果
        news_items = []
        # 简单的Markdown链接解析: [Title](URL)
        # Jina Search通常返回带有标题和链接的列表
        
        lines = search_result.split('\n')
        current_item = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 尝试匹配Markdown链接 [Title](URL)
            match = re.search(r'\[(.*?)\]\((.*?)\)', line)
            if match:
                title = match.group(1)
                link = match.group(2)
                
                # 过滤掉非新闻链接 (如Jina自身的链接等)
                if 'jina.ai' in link:
                    continue
                    
                news_items.append({
                    'title': title,
                    'link': link,
                    'date': '最近', # Jina Search结果可能不包含明确日期
                    'source': 'Jina Search'
                })
                
        return news_items[:5] # 返回前5条

    def get_company_info_fallback(self, code: str, name: str) -> Dict[str, Any]:
        """使用Jina搜索作为公司基本信息的兜底"""
        query = f"{name} {code} 公司简介 主营业务 行业"
        search_result = self.search(query)
        
        if search_result.startswith("Error") or search_result.startswith("Exception"):
            return {}
            
        # 尝试从搜索结果中提取信息 (这里只是一个简单的示例，实际可能需要LLM来提取)
        info = {
            'description': search_result[:500] + "...", # 截取前500字符作为简介
            'source': 'jina_search'
        }
        return info
