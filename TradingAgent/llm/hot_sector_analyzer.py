"""
热门板块 LLM 分析器

输入: 板块涨幅数据 + 新闻标题
输出: LLM 语义化分析结论（板块持续性、政策驱动、风险提示等）

被 daily_recommender_v28.py 在评分步骤后调用，
用 LLM 的分析结果调整板块评分或提供文字分析。
"""

import json
import logging
from typing import Dict, List, Optional, Any

from .base_client import LLMClient, get_llm_client
from .sector_news_fetcher import fetch_all_for_analysis

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位资深A股市场分析师，擅长从板块轮动、政策催化、资金博弈角度分析市场热点。
你需要根据提供的板块行情数据和新闻，给出简洁、有判断力的分析。
不要模棱两可，直接给出你的判断。"""


class HotSectorAnalyzer:
    """热门板块 LLM 分析器"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or get_llm_client()
        self._cache = None  # 缓存当次分析结果

    def analyze(self, internal_hot_sectors: List = None,
                fetch_news: bool = True) -> Dict[str, Any]:
        """
        执行完整分析流程

        Args:
            internal_hot_sectors: 来自 daily_recommender_v28 的 identify_hot_sectors() 结果
                                 格式: [('半导体', 3.5), ('新能源', 2.1), ...]
            fetch_news: 是否从网络抓取新闻

        Returns:
            {
                'hot_sectors_analysis': [...],     # TOP板块分析
                'market_summary': '...',            # 市场整体判断
                'sector_boost': {'半导体': 1.2, ...}, # 板块加分(-2 ~ +2)
                'risk_warnings': ['...'],           # 风险提示
                'provider': 'Qwen',                 # 使用的LLM
                'raw_data': {...},                  # 原始数据
            }
        """
        # 1. 抓取数据
        raw = {}
        if fetch_news:
            logger.info("正在抓取板块数据和新闻...")
            raw = fetch_all_for_analysis(top_sectors=8, news_per_sector=3, market_news_count=10)
            logger.info(f"数据抓取完成({raw.get('fetch_time', '?')})")

        # 2. 构建 prompt
        prompt = self._build_analysis_prompt(raw, internal_hot_sectors)

        # 3. 调用 LLM
        logger.info("正在调用LLM分析...")
        result = self.llm.chat_json(SYSTEM_PROMPT, prompt, temperature=0.3, max_tokens=2000)

        if result is None:
            logger.warning("LLM分析失败，返回中性结果")
            return self._neutral_result(raw)

        # 4. 解析和校验
        analysis = self._parse_result(result)
        analysis['provider'] = self.llm.last_provider or 'unknown'
        analysis['raw_data'] = raw

        self._cache = analysis
        return analysis

    def _build_analysis_prompt(self, raw: Dict, internal_sectors: List = None) -> str:
        """构建分析 prompt"""

        sections = []

        # A. 行业板块行情
        if raw.get('hot_sectors'):
            lines = []
            for s in raw['hot_sectors'][:10]:
                lines.append(f"  - {s['name']}: 涨幅{s['change_pct']:+.2f}%, 换手{s.get('turnover_rate', 0):.1f}%")
            sections.append(f"### 今日涨幅TOP行业板块\n" + "\n".join(lines))

        # B. 概念板块行情
        if raw.get('hot_concepts'):
            lines = []
            for c in raw['hot_concepts'][:10]:
                lines.append(f"  - {c['name']}: 涨幅{c['change_pct']:+.2f}%")
            sections.append(f"### 今日涨幅TOP概念板块\n" + "\n".join(lines))

        # C. 内部评分系统识别的热点
        if internal_sectors:
            lines = []
            for name, score in internal_sectors[:8]:
                lines.append(f"  - {name}: 内部评分{score:.2f}")
            sections.append(f"### 量化评分系统识别的热门板块\n" + "\n".join(lines))

        # D. 板块相关新闻
        news_parts = []
        for sector, news_list in raw.get('sector_news', {}).items():
            titles = [f"  - [{n.get('date', '')[:10]}] {n.get('title', '')}" for n in news_list[:3]]
            news_parts.append(f"**{sector}相关新闻:**\n" + "\n".join(titles))

        if news_parts:
            sections.append("### 板块相关新闻\n" + "\n".join(news_parts))

        # E. 市场要闻
        if raw.get('market_news'):
            titles = [f"  - [{n.get('date', '')[:10]}] {n.get('title', '')}" for n in raw['market_news'][:8]]
            sections.append("### 今日市场要闻\n" + "\n".join(titles))

        if not sections:
            sections.append("（今日无可用数据）")

        data_text = "\n\n".join(sections)

        prompt = f"""请分析今日A股市场板块热点，基于以下数据：

{data_text}

请直接输出JSON，不要包含任何markdown标记（如```json```），不要输出其他任何文字。JSON格式如下：

{{
    "top_sectors": [
        {{
            "name": "板块名称",
            "hotness": "高/中/低",
            "sustainability": "持续/一日游/观察",
            "driver": "政策催化/业绩驱动/资金博弈/事件驱动/超跌反弹",
            "summary": "一句话判断（20字以内）"
        }}
    ],
    "market_summary": "今日市场整体判断（50字以内）",
    "sector_boost": {{
        "板块名称": 1.5
    }},
    "risk_warnings": ["风险提示1", "风险提示2"],
    "tomorrow_focus": ["明天值得关注的板块/方向"]
}}

**sector_boost 说明**: 对每个热门板块给出一个调整分数(-2到+2)，
正数表示看好、负数表示看空。只列你有判断的板块。
这个分数会被叠加到量化评分系统的板块得分上。

**注意**: 
- top_sectors 至少分析3个板块，最多8个
- sector_boost 只需要有把握的板块，不需要全部
- risk_warnings 列出系统性风险或异常信号
"""

        return prompt

    def _parse_result(self, result: Dict) -> Dict:
        """解析和校验 LLM 结果"""
        analysis = {
            'hot_sectors_analysis': [],
            'market_summary': '',
            'sector_boost': {},
            'risk_warnings': [],
            'tomorrow_focus': [],
        }

        # 解析 top_sectors
        top = result.get('top_sectors', [])
        if isinstance(top, list):
            for s in top[:8]:
                if isinstance(s, dict) and s.get('name'):
                    analysis['hot_sectors_analysis'].append({
                        'name': str(s.get('name', '')),
                        'hotness': str(s.get('hotness', '中')),
                        'sustainability': str(s.get('sustainability', '观察')),
                        'driver': str(s.get('driver', '未知')),
                        'summary': str(s.get('summary', '')),
                    })

        # market_summary
        analysis['market_summary'] = str(result.get('market_summary', ''))[:200]

        # sector_boost - 校验范围
        boost = result.get('sector_boost', {})
        if isinstance(boost, dict):
            for k, v in boost.items():
                try:
                    val = float(v)
                    val = max(-2.0, min(2.0, val))  # clamp
                    analysis['sector_boost'][str(k)] = val
                except (ValueError, TypeError):
                    pass

        # risk_warnings
        warnings_list = result.get('risk_warnings', [])
        if isinstance(warnings_list, list):
            analysis['risk_warnings'] = [str(w) for w in warnings_list[:5]]

        # tomorrow_focus
        focus = result.get('tomorrow_focus', [])
        if isinstance(focus, list):
            analysis['tomorrow_focus'] = [str(f) for f in focus[:5]]

        return analysis

    def _neutral_result(self, raw: Dict = None) -> Dict:
        """LLM 失败时的中性 fallback"""
        return {
            'hot_sectors_analysis': [],
            'market_summary': 'LLM分析不可用，仅使用量化数据',
            'sector_boost': {},
            'risk_warnings': [],
            'tomorrow_focus': [],
            'provider': 'none',
            'raw_data': raw or {},
        }

    def get_sector_boost(self, sector_name: str) -> float:
        """获取某个板块的LLM加分"""
        if not self._cache:
            return 0.0
        boost_map = self._cache.get('sector_boost', {})

        # 精确匹配
        if sector_name in boost_map:
            return boost_map[sector_name]

        # 模糊匹配（包含关系）
        for k, v in boost_map.items():
            if k in sector_name or sector_name in k:
                return v

        return 0.0

    def format_report(self) -> str:
        """格式化输出分析报告"""
        if not self._cache:
            return "（未执行分析）"

        lines = []
        lines.append(f"=== LLM 板块分析报告 ===")
        lines.append(f"Provider: {self._cache.get('provider', '?')}")
        lines.append("")

        # 市场总结
        summary = self._cache.get('market_summary', '')
        if summary:
            lines.append(f"📊 市场判断: {summary}")
            lines.append("")

        # 板块分析
        for s in self._cache.get('hot_sectors_analysis', []):
            boost = self._cache.get('sector_boost', {}).get(s['name'], 0)
            boost_str = f"(LLM加分:{boost:+.1f})" if boost else ""
            lines.append(
                f"🔥 {s['name']} | 热度:{s['hotness']} | "
                f"持续性:{s['sustainability']} | 驱动:{s['driver']} {boost_str}"
            )
            if s.get('summary'):
                lines.append(f"   → {s['summary']}")

        # 风险提示
        warnings = self._cache.get('risk_warnings', [])
        if warnings:
            lines.append("")
            lines.append("⚠️ 风险提示:")
            for w in warnings:
                lines.append(f"   - {w}")

        # 明日关注
        focus = self._cache.get('tomorrow_focus', [])
        if focus:
            lines.append("")
            lines.append("👁 明日关注:")
            for f in focus:
                lines.append(f"   - {f}")

        return "\n".join(lines)
