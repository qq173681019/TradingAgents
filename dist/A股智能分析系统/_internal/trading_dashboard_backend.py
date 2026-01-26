"""
交易仪表盘后端服务
提供实时数据API支持HTML仪表盘的交互
"""

import json
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

# 添加共享路径
SHARED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'TradingShared')
if SHARED_PATH not in sys.path:
    sys.path.insert(0, SHARED_PATH)
if os.path.join(SHARED_PATH, 'api') not in sys.path:
    sys.path.insert(0, os.path.join(SHARED_PATH, 'api'))


class TrendType(Enum):
    """趋势类型"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


@dataclass
class KPIData:
    """KPI指标数据"""
    name: str
    value: str
    change: float
    change_text: str
    trend: TrendType


@dataclass
class StockData:
    """股票数据"""
    rank: int
    code: str
    name: str
    price: float
    change_percent: float
    volume: str
    market_cap: str
    pe_ratio: float


@dataclass
class SectorData:
    """板块数据"""
    name: str
    change_percent: float
    stock_count: int
    leading_stock: str


@dataclass
class TechnicalIndicator:
    """技术指标"""
    name: str
    value: float
    status: str  # 'strong', 'normal', 'weak'
    description: str


class TradingDashboardService:
    """交易仪表盘数据服务"""

    def __init__(self):
        """初始化服务"""
        self.last_update = None
        self.cache = {}
        self.update_lock = threading.Lock()
        self._init_sample_data()

    def _init_sample_data(self):
        """初始化示例数据"""
        self.sample_stocks = [
            StockData(1, "600519", "贵州茅台", 2850.50, 5.23, "1.2M", "¥2.4T", 85.5),
            StockData(2, "000858", "五粮液", 298.75, 4.85, "3.5M", "¥1.2T", 62.3),
            StockData(3, "000651", "格力电器", 45.20, -2.15, "5.8M", "¥980B", 28.5),
            StockData(4, "601888", "中国国旅", 156.80, 3.42, "2.2M", "¥780B", 45.2),
            StockData(5, "600036", "招商银行", 48.95, 2.18, "8.9M", "¥2.1T", 12.3),
        ]

        self.sample_sectors = [
            SectorData("计算机", 6.2, 285, "600519"),
            SectorData("电子", 5.8, 342, "000858"),
            SectorData("医药生物", 4.5, 198, "600036"),
            SectorData("电气设备", 4.2, 156, "601888"),
            SectorData("机械设备", 3.8, 214, "000651"),
        ]

    def get_kpi_data(self) -> List[Dict]:
        """获取KPI指标数据"""
        return [
            {
                "label": "涨跌家数",
                "value": "2,847",
                "change": 12.5,
                "change_text": "↑ 12.5%",
                "tooltip": "今日上涨股票数量"
            },
            {
                "label": "成交总额",
                "value": "¥825.4B",
                "change": 8.3,
                "change_text": "↑ 8.3%",
                "tooltip": "当前市场成交量"
            },
            {
                "label": "平均涨幅",
                "value": "+2.34%",
                "change": 2.34,
                "change_text": "↑ 强势",
                "tooltip": "当前市场平均涨幅"
            },
            {
                "label": "主力资金",
                "value": "¥12.3B",
                "change": 15.2,
                "change_text": "↑ 净流入",
                "tooltip": "主力资金净流入"
            }
        ]

    def get_market_indices(self) -> Dict:
        """获取大盘指数"""
        return {
            "上证指数": {
                "value": 3564.20,
                "change": 85.45,
                "change_percent": 2.45,
                "time": datetime.now().strftime("%H:%M:%S")
            },
            "深证成指": {
                "value": 10825.47,
                "change": 198.32,
                "change_percent": 1.87,
                "time": datetime.now().strftime("%H:%M:%S")
            },
            "创业板指": {
                "value": 2134.56,
                "change": 52.18,
                "change_percent": 2.50,
                "time": datetime.now().strftime("%H:%M:%S")
            }
        }

    def get_top_stocks(self, limit: int = 50, stock_type: str = "all", 
                       sort_by: str = "change", min_change: float = 0) -> List[Dict]:
        """获取涨幅排行榜"""
        stocks = self.sample_stocks.copy()
        
        # 按涨幅排序
        if sort_by == "change":
            stocks.sort(key=lambda x: x.change_percent, reverse=True)
        elif sort_by == "volume":
            stocks.sort(key=lambda x: float(x.volume.replace('M', '')), reverse=True)
        elif sort_by == "price":
            stocks.sort(key=lambda x: x.price, reverse=True)

        # 筛选最小涨幅
        stocks = [s for s in stocks if s.change_percent >= min_change]

        return [
            {
                "rank": i + 1,
                "code": s.code,
                "name": s.name,
                "price": s.price,
                "change_percent": s.change_percent,
                "volume": s.volume,
                "market_cap": s.market_cap,
                "pe_ratio": s.pe_ratio,
                "trend": "up" if s.change_percent > 0 else "down"
            }
            for i, s in enumerate(stocks[:limit])
        ]

    def get_sector_analysis(self) -> List[Dict]:
        """获取板块分析数据"""
        return [
            {
                "name": s.name,
                "change_percent": s.change_percent,
                "stock_count": s.stock_count,
                "leading_stock": s.leading_stock,
                "status": "hot" if s.change_percent > 4 else "normal" if s.change_percent > 0 else "cold"
            }
            for s in self.sample_sectors
        ]

    def get_technical_analysis(self) -> Dict:
        """获取技术指标分析"""
        return {
            "macd": {
                "strong_buy": 285,
                "buy": 680,
                "neutral": 1240,
                "sell": 520,
                "strong_sell": 180
            },
            "rsi": {
                "overbought": 340,  # >70
                "normal": 2180,
                "oversold": 276  # <30
            },
            "bollinger_bands": {
                "above": 486,
                "middle": 1842,
                "below": 468
            }
        }

    def get_money_flow(self) -> Dict:
        """获取资金流向数据"""
        days = ["周一", "周二", "周三", "周四", "周五", "今日"]
        inflow = [185, 225, 180, 240, 205, 230]
        outflow = [45, 35, 60, 32, 48, 38]

        return {
            "days": days,
            "inflow": inflow,
            "outflow": outflow,
            "total_inflow": sum(inflow),
            "total_outflow": sum(outflow),
            "net_flow": sum(inflow) - sum(outflow)
        }

    def analyze_stock(self, code: str) -> Dict:
        """分析单个股票"""
        # 在实际应用中，这里会调用真实的数据分析逻辑
        return {
            "code": code,
            "name": "示例股票",
            "technical_score": 7.5,
            "fundamental_score": 6.8,
            "chip_score": 7.2,
            "recommendation": "买入",
            "short_term": "看多",
            "medium_term": "看多",
            "long_term": "看多",
            "risk_level": "中等",
            "key_indicators": {
                "ma5": 45.2,
                "ma10": 44.8,
                "ma20": 43.5,
                "rsi": 65.2,
                "macd": "golden_cross"
            }
        }

    def export_data(self, export_type: str = "csv") -> str:
        """导出数据"""
        stocks = self.get_top_stocks(limit=50)
        
        if export_type == "csv":
            csv_content = "排名,代码,名称,现价,涨幅(%),成交量,市值,PE\n"
            for stock in stocks:
                csv_content += f"{stock['rank']},{stock['code']},{stock['name']},"
                csv_content += f"{stock['price']},{stock['change_percent']:.2f},"
                csv_content += f"{stock['volume']},{stock['market_cap']},{stock['pe_ratio']}\n"
            return csv_content
        
        elif export_type == "json":
            return json.dumps(stocks, ensure_ascii=False, indent=2)

        return ""

    def get_dashboard_summary(self) -> Dict:
        """获取仪表盘摘要"""
        return {
            "update_time": datetime.now().isoformat(),
            "market_status": "开市",
            "trading_day": datetime.now().strftime("%Y-%m-%d"),
            "kpi": self.get_kpi_data(),
            "indices": self.get_market_indices(),
            "top_stocks": self.get_top_stocks(limit=10),
            "sectors": self.get_sector_analysis(),
            "technical": self.get_technical_analysis(),
            "money_flow": self.get_money_flow()
        }


class DashboardAPI:
    """仪表盘API接口"""

    def __init__(self, service: TradingDashboardService):
        """初始化API"""
        self.service = service

    def handle_request(self, request_type: str, **kwargs) -> Dict:
        """处理API请求"""
        handlers = {
            "get_kpi": self.service.get_kpi_data,
            "get_indices": self.service.get_market_indices,
            "get_stocks": lambda: self.service.get_top_stocks(**kwargs),
            "get_sectors": self.service.get_sector_analysis,
            "get_technical": self.service.get_technical_analysis,
            "get_money_flow": self.service.get_money_flow,
            "analyze_stock": lambda: self.service.analyze_stock(kwargs.get('code')),
            "export_data": lambda: self.service.export_data(kwargs.get('type', 'csv')),
            "get_summary": self.service.get_dashboard_summary
        }

        handler = handlers.get(request_type)
        if handler:
            try:
                result = handler()
                return {"success": True, "data": result}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        return {"success": False, "error": f"Unknown request type: {request_type}"}


# 全局实例
_dashboard_service = TradingDashboardService()
_dashboard_api = DashboardAPI(_dashboard_service)


def get_dashboard_data(request_type: str, **kwargs) -> Dict:
    """获取仪表盘数据的便捷函数"""
    return _dashboard_api.handle_request(request_type, **kwargs)


def get_service() -> TradingDashboardService:
    """获取仪表盘服务实例"""
    return _dashboard_service


if __name__ == "__main__":
    # 测试示例
    print("=" * 80)
    print("交易仪表盘后端服务测试")
    print("=" * 80)

    # 获取KPI数据
    print("\n【KPI指标】")
    kpi_data = get_dashboard_data("get_kpi")
    for item in kpi_data['data']:
        print(f"  {item['label']}: {item['value']} ({item['change_text']})")

    # 获取大盘指数
    print("\n【大盘指数】")
    indices = get_dashboard_data("get_indices")
    for name, data in indices['data'].items():
        print(f"  {name}: {data['value']:.2f} ({data['change_percent']:+.2f}%)")

    # 获取涨幅排行
    print("\n【涨幅排行前5】")
    stocks = get_dashboard_data("get_stocks", limit=5)
    for stock in stocks['data']:
        print(f"  {stock['rank']}. {stock['code']} {stock['name']}: "
              f"¥{stock['price']} ({stock['change_percent']:+.2f}%)")

    # 获取板块分析
    print("\n【板块热力分析】")
    sectors = get_dashboard_data("get_sectors")
    for sector in sectors['data']:
        print(f"  {sector['name']}: {sector['change_percent']:+.2f}% "
              f"({sector['stock_count']}只股票)")

    # 获取技术指标
    print("\n【技术指标分布】")
    technical = get_dashboard_data("get_technical")
    macd = technical['data']['macd']
    print(f"  MACD - 强烈看多: {macd['strong_buy']}, 看多: {macd['buy']}, "
          f"平衡: {macd['neutral']}, 看空: {macd['sell']}, 强烈看空: {macd['strong_sell']}")

    # 获取资金流向
    print("\n【资金流向分析】")
    money_flow = get_dashboard_data("get_money_flow")
    print(f"  净流入: ¥{money_flow['data']['total_inflow']:.0f}亿")
    print(f"  净流出: ¥{money_flow['data']['total_outflow']:.0f}亿")
    print(f"  日均成交额: ¥825.4B")

    # 获取完整摘要
    print("\n【仪表盘摘要】")
    summary = get_dashboard_data("get_summary")
    print(f"  更新时间: {summary['data']['update_time']}")
    print(f"  市场状态: {summary['data']['market_status']}")
    print(f"  交易日: {summary['data']['trading_day']}")
    print(f"  KPI项目: {len(summary['data']['kpi'])}个")
    print(f"  前十股票: {len(summary['data']['top_stocks'])}只")

    print("\n✅ 测试完成！")
