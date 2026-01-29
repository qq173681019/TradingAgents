# -*- coding: utf-8 -*-
"""
TradingAgents 集成版现代化UI
完整集成原系统功能，包括：
- 更新K线数据
- 批量评分
- 获取推荐股票
- 竞价排行
- 等核心功能
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# ==================== 路径配置 ====================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
SHARED_PATH = os.path.join(PARENT_DIR, 'TradingShared')
DATA_PATH = os.path.join(SHARED_PATH, 'data')
API_PATH = os.path.join(SHARED_PATH, 'api')

# 添加到系统路径
for path in [CURRENT_DIR, SHARED_PATH, API_PATH]:
    if path not in sys.path:
        sys.path.insert(0, path)

# ==================== 导入依赖 ====================
try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False
    print("❌ CustomTkinter 未安装，请运行: pip install customtkinter")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("❌ requests 未安装，请运行: pip install requests")


# ==================== 设计系统 ====================
class Colors:
    BG_PRIMARY = "#0F172A"
    BG_SECONDARY = "#1E293B"
    BG_CARD = "#0F172A"
    ACCENT_BLUE = "#3B82F6"
    SUCCESS = "#10B981"
    DANGER = "#EF4444"
    WARNING = "#F59E0B"
    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "#94A3B8"
    TEXT_MUTED = "#64748B"
    BORDER = "#334155"
    ACCENT_HOVER = "#2563EB"


class Spacing:
    XS, SM, MD, LG, XL = 4, 8, 16, 24, 32


class Radius:
    SM, MD, LG = 8, 12, 16


class FontSize:
    XS, SM, MD, LG, XL, XXL = 12, 14, 15, 18, 24, 28


# ==================== 核心功能服务 ====================
class TradingService:
    """交易系统核心服务 - 封装所有业务逻辑"""
    
    # 默认加权比例（技术面:基本面:筹码面:热门板块）
    DEFAULT_WEIGHTS = {'tech': 40, 'fund': 20, 'chip': 40, 'hot': 0}
    
    def __init__(self, status_callback=None):
        self.status_callback = status_callback or print
        self.batch_scores = {}
        self.stock_names = {}
        self.is_busy = False
        self.weights = self.DEFAULT_WEIGHTS.copy()
        self._load_stock_names()
    
    def _update_status(self, msg: str):
        """更新状态"""
        if self.status_callback:
            self.status_callback(msg)
        print(msg)
    
    def _load_stock_names(self):
        """加载股票名称"""
        try:
            fallback_file = os.path.join(DATA_PATH, 'stock_info_fallback.json')
            if os.path.exists(fallback_file):
                with open(fallback_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.stock_names = {k: v.get('name', k) for k, v in data.items() if isinstance(v, dict)}
                self._update_status(f"✓ 加载 {len(self.stock_names)} 只股票名称")
        except Exception as e:
            self._update_status(f"❌ 加载股票名称失败: {e}")
    
    def get_stock_name(self, code: str) -> str:
        return self.stock_names.get(code, code)
    
    # ==================== 评分数据 ====================
    def load_batch_scores(self) -> Dict:
        """加载评分数据"""
        try:
            score_files = [f for f in os.listdir(DATA_PATH) 
                          if f.startswith('batch_stock_scores_optimized_主板') and f.endswith('.json')]
            
            if not score_files:
                score_file = os.path.join(DATA_PATH, 'batch_stock_scores.json')
            else:
                score_files.sort(reverse=True)
                score_file = os.path.join(DATA_PATH, score_files[0])
            
            if os.path.exists(score_file):
                with open(score_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if 'scores' in data:
                    self.batch_scores = data['scores']
                elif 'stocks' in data:
                    self.batch_scores = data['stocks']
                else:
                    self.batch_scores = {k: v for k, v in data.items() 
                                        if isinstance(v, dict) and 'overall_score' in v}
                
                self._update_status(f"✓ 加载 {len(self.batch_scores)} 只股票评分")
                return self.batch_scores
        except Exception as e:
            self._update_status(f"❌ 加载评分失败: {e}")
        return {}
    
    def set_weights(self, tech: int, fund: int, chip: int, hot: int = 0):
        """设置加权比例"""
        self.weights = {'tech': tech, 'fund': fund, 'chip': chip, 'hot': hot}
        total = tech + fund + chip + hot
        if total > 0:
            self._update_status(f"加权比例: 技术{tech}% / 基本面{fund}% / 筹码{chip}% / 热门{hot}%")
    
    def calculate_weighted_score(self, data: Dict) -> float:
        """根据加权比例计算综合分"""
        tech = data.get('short_term_score', 0) or 0
        fund = data.get('medium_term_score', 0) or 0
        chip = data.get('chip_score', 0) or 0
        hot = data.get('hot_score', 0) or 0
        
        total_weight = self.weights['tech'] + self.weights['fund'] + self.weights['chip'] + self.weights['hot']
        if total_weight <= 0:
            return data.get('overall_score', 0)
        
        weighted_score = (
            tech * self.weights['tech'] +
            fund * self.weights['fund'] +
            chip * self.weights['chip'] +
            hot * self.weights['hot']
        ) / total_weight
        
        return weighted_score
    
    def get_top_stocks(self, top_n: int = 20, sort_by: str = 'weighted') -> List[Dict]:
        """获取评分最高的股票
        
        Args:
            top_n: 返回的股票数量
            sort_by: 排序方式
                - 'weighted': 按加权综合分（使用自定义加权）
                - 'overall': 按原始综合分
                - 'tech': 按技术面评分
                - 'fund': 按基本面评分
                - 'chip': 按筹码评分
        """
        if not self.batch_scores:
            self.load_batch_scores()
        
        # 构建带计算分数的列表
        stocks_with_scores = []
        for code, data in self.batch_scores.items():
            if not isinstance(data, dict):
                continue
            
            weighted_score = self.calculate_weighted_score(data)
            
            stocks_with_scores.append({
                'code': code,
                'data': data,
                'weighted_score': weighted_score,
                'overall_score': data.get('overall_score', 0),
                'tech_score': data.get('short_term_score', 0) or 0,
                'fund_score': data.get('medium_term_score', 0) or 0,
                'chip_score': data.get('chip_score', 0) or 0
            })
        
        # 根据排序方式排序
        sort_keys = {
            'weighted': lambda x: x['weighted_score'],
            'overall': lambda x: x['overall_score'],
            'tech': lambda x: x['tech_score'],
            'fund': lambda x: x['fund_score'],
            'chip': lambda x: x['chip_score']
        }
        sort_key = sort_keys.get(sort_by, sort_keys['weighted'])
        
        sorted_stocks = sorted(stocks_with_scores, key=sort_key, reverse=True)[:top_n]
        
        result = []
        for item in sorted_stocks:
            code = item['code']
            data = item['data']
            name = data.get('name') or self.get_stock_name(code) or code
            
            # 根据排序方式决定显示的主分数
            if sort_by == 'tech':
                display_score = item['tech_score']
                score_type = '技术分'
            elif sort_by == 'fund':
                display_score = item['fund_score']
                score_type = '基本面分'
            elif sort_by == 'chip':
                display_score = item['chip_score']
                score_type = '筹码分'
            elif sort_by == 'weighted':
                display_score = item['weighted_score']
                score_type = '加权综合分'
            else:
                display_score = item['overall_score']
                score_type = '综合分'
            
            result.append({
                'code': code,
                'name': name,
                'industry': data.get('industry', 'A股'),
                'overall_score': item['overall_score'],
                'weighted_score': item['weighted_score'],
                'tech_score': item['tech_score'],
                'fund_score': item['fund_score'],
                'capital_score': data.get('long_term_score', 0),
                'chip_score': item['chip_score'],
                'display_score': display_score,
                'score_type': score_type,
                'recommendation': data.get('recommendation', ''),
                'trend': data.get('trend', '')
            })
        return result
    
    def get_stock_detail(self, code: str) -> Optional[Dict]:
        """获取股票详情"""
        if code in self.batch_scores:
            data = self.batch_scores[code]
            name = data.get('name') or self.get_stock_name(code) or code
            return {
                'code': code,
                'name': name,
                'industry': data.get('industry', 'A股'),
                'overall_score': data.get('overall_score', 0),
                'tech_score': data.get('short_term_score', 0),
                'fund_score': data.get('medium_term_score', 0),
                'capital_score': data.get('long_term_score', 0),
                'chip_score': data.get('chip_score', 0),
                'chip_level': data.get('chip_level', ''),
                'recommendation': data.get('recommendation', ''),
                'analysis': data.get('analysis_reason', ''),
                'trend': data.get('trend', '')
            }
        return None
    
    # ==================== 实时行情 ====================
    def fetch_index_quotes(self) -> List[Dict]:
        """获取大盘指数行情"""
        try:
            indices = [
                ('sh000001', '上证指数'),
                ('sz399001', '深证成指'),
                ('sz399006', '创业板指'),
                ('sh000688', '科创50')
            ]
            
            codes = ','.join([idx[0] for idx in indices])
            url = f"http://qt.gtimg.cn/q={codes}"
            resp = requests.get(url, timeout=5)
            
            result = []
            if resp.status_code == 200:
                lines = resp.text.strip().split('\n')
                for i, line in enumerate(lines):
                    if '~' in line:
                        parts = line.split('~')
                        if len(parts) > 35:
                            price = float(parts[3]) if parts[3] else 0
                            prev_close = float(parts[4]) if parts[4] else 0
                            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
                            
                            result.append({
                                'name': indices[i][1] if i < len(indices) else parts[1],
                                'value': f"{price:,.2f}",
                                'change': f"{change_pct:+.2f}%",
                                'is_positive': change_pct >= 0
                            })
            
            if not result:
                return [{'name': n, 'value': '--', 'change': '--', 'is_positive': True} 
                       for _, n in indices]
            return result
        except Exception as e:
            self._update_status(f"获取指数行情失败: {e}")
            return [{'name': '上证指数', 'value': '--', 'change': '--', 'is_positive': True},
                   {'name': '深证成指', 'value': '--', 'change': '--', 'is_positive': True},
                   {'name': '创业板指', 'value': '--', 'change': '--', 'is_positive': True},
                   {'name': '科创50', 'value': '--', 'change': '--', 'is_positive': True}]
    
    # ==================== 核心功能：更新K线 ====================
    def update_kline_data(self, callback=None):
        """更新K线数据 - 调用原有脚本"""
        if self.is_busy:
            self._update_status("⚠️ 有任务正在执行，请稍候...")
            return
        
        self.is_busy = True
        self._update_status("🔄 开始更新K线数据...")
        
        def run():
            try:
                script_path = os.path.join(CURRENT_DIR, 'update_kline_batch.py')
                if os.path.exists(script_path):
                    self._update_status(f"📂 运行脚本: {os.path.basename(script_path)}")
                    
                    # 使用Popen实时获取输出
                    process = subprocess.Popen(
                        [sys.executable, script_path],
                        cwd=CURRENT_DIR,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1
                    )
                    
                    # 实时读取输出
                    for line in iter(process.stdout.readline, ''):
                        if line.strip():
                            self._update_status(f"  {line.strip()[:80]}")
                    
                    process.wait(timeout=600)
                    
                    if process.returncode == 0:
                        self._update_status("✅ K线数据更新完成！")
                    else:
                        self._update_status(f"❌ K线更新失败 (返回码: {process.returncode})")
                else:
                    self._update_status(f"❌ 找不到脚本: {script_path}")
            except subprocess.TimeoutExpired:
                self._update_status("⚠️ K线更新超时")
                process.kill()
            except Exception as e:
                self._update_status(f"❌ K线更新异常: {e}")
            finally:
                self.is_busy = False
                if callback:
                    callback()
        
        threading.Thread(target=run, daemon=True).start()
    
    # ==================== 核心功能：生成评分 ====================
    def generate_scores(self, callback=None):
        """生成主板评分 - 调用原有脚本"""
        if self.is_busy:
            self._update_status("⚠️ 有任务正在执行，请稍候...")
            return
        
        self.is_busy = True
        self._update_status("🔄 开始生成主板评分...")
        
        def run():
            try:
                script_path = os.path.join(CURRENT_DIR, 'generate_mainboard_scores.py')
                if os.path.exists(script_path):
                    result = subprocess.run(
                        [sys.executable, script_path],
                        cwd=CURRENT_DIR,
                        capture_output=True,
                        text=True,
                        timeout=1800  # 30分钟超时
                    )
                    if result.returncode == 0:
                        self._update_status("✅ 评分生成完成！")
                        # 重新加载评分
                        self.load_batch_scores()
                    else:
                        self._update_status(f"❌ 评分生成失败: {result.stderr[:200]}")
                else:
                    self._update_status(f"❌ 找不到脚本: {script_path}")
            except subprocess.TimeoutExpired:
                self._update_status("⚠️ 评分生成超时")
            except Exception as e:
                self._update_status(f"❌ 评分生成异常: {e}")
            finally:
                self.is_busy = False
                if callback:
                    callback()
        
        threading.Thread(target=run, daemon=True).start()
    
    # ==================== 核心功能：竞价排行 ====================
    def get_auction_ranking(self, callback=None):
        """获取竞价排行"""
        if self.is_busy:
            self._update_status("⚠️ 有任务正在执行，请稍候...")
            return []
        
        self.is_busy = True
        self._update_status("🔄 获取竞价排行...")
        
        try:
            script_path = os.path.join(API_PATH, 'get_call_auction_ranking.py')
            if os.path.exists(script_path):
                result = subprocess.run(
                    [sys.executable, script_path],
                    cwd=API_PATH,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode == 0:
                    self._update_status("✅ 竞价排行获取完成！")
                    # 解析输出
                    return self._parse_auction_output(result.stdout)
                else:
                    self._update_status(f"❌ 竞价排行失败")
            else:
                self._update_status(f"❌ 找不到竞价脚本")
        except Exception as e:
            self._update_status(f"❌ 竞价排行异常: {e}")
        finally:
            self.is_busy = False
        return []
    
    def _parse_auction_output(self, output: str) -> List[Dict]:
        """解析竞价排行输出"""
        # 简单解析，实际需要根据脚本输出格式调整
        return []
    
    # ==================== 核心功能：启动原系统 ====================
    def launch_original_gui(self):
        """启动原有GUI系统"""
        self._update_status("🚀 启动原系统...")
        script_path = os.path.join(CURRENT_DIR, 'a_share_gui_compatible.py')
        if os.path.exists(script_path):
            subprocess.Popen([sys.executable, script_path], cwd=CURRENT_DIR)
            self._update_status("✅ 原系统已启动")
        else:
            self._update_status(f"❌ 找不到: {script_path}")


# ==================== UI组件 ====================

class MetricCard(ctk.CTkFrame):
    """指标卡片"""
    def __init__(self, master, label="", value="--", change="--", is_positive=True, **kwargs):
        super().__init__(master, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.MD, **kwargs)
        
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=FontSize.SM),
                    text_color=Colors.TEXT_SECONDARY).pack(fill="x", padx=Spacing.LG, pady=(Spacing.LG, Spacing.XS))
        
        self.value_label = ctk.CTkLabel(self, text=value, font=ctk.CTkFont(size=FontSize.XXL, weight="bold"),
                                        text_color=Colors.TEXT_PRIMARY)
        self.value_label.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.XS))
        
        change_color = Colors.SUCCESS if is_positive else Colors.DANGER
        self.change_label = ctk.CTkLabel(self, text=f"{'↑' if is_positive else '↓'} {change}",
                                         font=ctk.CTkFont(size=FontSize.SM, weight="bold"),
                                         text_color=change_color)
        self.change_label.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
    
    def update_data(self, value, change, is_positive):
        self.value_label.configure(text=value)
        color = Colors.SUCCESS if is_positive else Colors.DANGER
        self.change_label.configure(text=f"{'↑' if is_positive else '↓'} {change}", text_color=color)


class StockRow(ctk.CTkFrame):
    """股票行"""
    def __init__(self, master, name="", code="", score="", recommendation="", is_positive=True, on_click=None, **kwargs):
        super().__init__(master, fg_color=Colors.BG_CARD, corner_radius=Radius.SM, height=56, **kwargs)
        self.pack_propagate(False)
        self.on_click = on_click
        
        # 绑定点击
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda e: self.configure(fg_color=Colors.BG_SECONDARY))
        self.bind("<Leave>", lambda e: self.configure(fg_color=Colors.BG_CARD))
        
        # 左侧
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="y", padx=Spacing.MD, pady=Spacing.SM)
        
        self.name_label = ctk.CTkLabel(left, text=name, font=ctk.CTkFont(size=FontSize.MD, weight="bold"),
                                       text_color=Colors.TEXT_PRIMARY, anchor="w")
        self.name_label.pack(anchor="w")
        
        self.code_label = ctk.CTkLabel(left, text=code, font=ctk.CTkFont(size=FontSize.XS),
                                       text_color=Colors.TEXT_MUTED, anchor="w")
        self.code_label.pack(anchor="w")
        
        # 右侧
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", fill="y", padx=Spacing.MD, pady=Spacing.SM)
        
        color = Colors.SUCCESS if is_positive else Colors.DANGER
        self.score_label = ctk.CTkLabel(right, text=score, font=ctk.CTkFont(size=FontSize.MD, weight="bold"),
                                        text_color=color, anchor="e")
        self.score_label.pack(anchor="e")
        
        self.rec_label = ctk.CTkLabel(right, text=recommendation[:10] if recommendation else "",
                                      font=ctk.CTkFont(size=FontSize.XS), text_color=Colors.TEXT_MUTED, anchor="e")
        self.rec_label.pack(anchor="e")
        
        # 让子组件也响应点击
        for w in [left, right, self.name_label, self.code_label, self.score_label, self.rec_label]:
            w.bind("<Button-1>", self._click)
    
    def _click(self, e):
        if self.on_click:
            self.on_click()


class ActionButton(ctk.CTkButton):
    """操作按钮"""
    def __init__(self, master, text="", icon="", variant="primary", **kwargs):
        colors = {
            "primary": (Colors.ACCENT_BLUE, Colors.ACCENT_HOVER),
            "success": (Colors.SUCCESS, "#059669"),
            "danger": (Colors.DANGER, "#DC2626"),
            "warning": (Colors.WARNING, "#D97706"),
            "secondary": (Colors.BG_SECONDARY, Colors.BG_CARD)
        }
        fg, hover = colors.get(variant, colors["primary"])
        
        super().__init__(master, text=f"{icon} {text}" if icon else text,
                        fg_color=fg, hover_color=hover, text_color=Colors.TEXT_PRIMARY,
                        corner_radius=Radius.SM, font=ctk.CTkFont(size=FontSize.SM, weight="bold"),
                        height=40, **kwargs)


# ==================== 主应用 ====================

class TradingApp(ctk.CTk):
    """集成版交易应用"""
    
    def __init__(self):
        super().__init__()
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.title("TradingAgents - A股智能分析系统 (集成版)")
        self.geometry("1600x1000")
        self.state('zoomed')  # Windows下最大化窗口
        self.configure(fg_color=Colors.BG_PRIMARY)
        
        # 服务
        self.service = TradingService(status_callback=self._update_status)
        
        # 状态
        self.stock_rows = []
        self.selected_stock = None
        self.metric_cards = []
        self.current_sort_by = 'weighted'  # 当前排序方式
        self.weight_sliders = {}  # 加权滑块
        
        # 构建UI
        self._create_layout()
        self._create_sidebar()
        self._create_main_content()
        
        # 加载数据
        self.after(100, self._load_data)
    
    def _create_layout(self):
        # 侧边栏
        self.sidebar = ctk.CTkFrame(self, fg_color=Colors.BG_SECONDARY, width=280, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        
        # 主内容
        self.main_content = ctk.CTkFrame(self, fg_color=Colors.BG_PRIMARY, corner_radius=0)
        self.main_content.pack(side="left", fill="both", expand=True)
    
    def _create_sidebar(self):
        # Logo
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=48)
        logo_frame.pack(fill="x", padx=Spacing.MD, pady=Spacing.LG)
        
        ctk.CTkLabel(logo_frame, text="📈", font=ctk.CTkFont(size=24),
                    text_color=Colors.ACCENT_BLUE).pack(side="left", padx=Spacing.SM)
        ctk.CTkLabel(logo_frame, text="TradingAgents", font=ctk.CTkFont(size=20, weight="bold"),
                    text_color=Colors.TEXT_PRIMARY).pack(side="left")
        
        ctk.CTkFrame(self.sidebar, fg_color=Colors.BORDER, height=1).pack(fill="x", padx=Spacing.MD, pady=Spacing.SM)
        
        # ==================== 功能按钮区 ====================
        func_label = ctk.CTkLabel(self.sidebar, text="📌 核心功能", font=ctk.CTkFont(size=FontSize.SM, weight="bold"),
                                  text_color=Colors.TEXT_SECONDARY, anchor="w")
        func_label.pack(fill="x", padx=Spacing.LG, pady=(Spacing.MD, Spacing.SM))
        
        # 更新K线
        ActionButton(self.sidebar, text="更新K线数据", icon="📊", variant="primary",
                    command=self._on_update_kline).pack(fill="x", padx=Spacing.MD, pady=2)
        
        # 生成评分
        ActionButton(self.sidebar, text="生成主板评分", icon="⭐", variant="success",
                    command=self._on_generate_scores).pack(fill="x", padx=Spacing.MD, pady=2)
        
        # 刷新数据
        ActionButton(self.sidebar, text="刷新推荐列表", icon="🔄", variant="secondary",
                    command=self._load_data).pack(fill="x", padx=Spacing.MD, pady=2)
        
        # 热门板块分析
        ActionButton(self.sidebar, text="热门板块分析", icon="🔥", variant="warning",
                    command=self._on_hot_sectors).pack(fill="x", padx=Spacing.MD, pady=2)
        
        ctk.CTkFrame(self.sidebar, fg_color=Colors.BORDER, height=1).pack(fill="x", padx=Spacing.MD, pady=Spacing.MD)
        
        # ==================== 排序方式 ====================
        sort_label = ctk.CTkLabel(self.sidebar, text="📊 排序方式", font=ctk.CTkFont(size=FontSize.SM, weight="bold"),
                                  text_color=Colors.TEXT_SECONDARY, anchor="w")
        sort_label.pack(fill="x", padx=Spacing.LG, pady=(Spacing.SM, Spacing.SM))
        
        self.sort_var = ctk.StringVar(value="weighted")
        sort_options = [
            ("加权综合分", "weighted"),
            ("技术面评分", "tech"),
            ("基本面评分", "fund"),
            ("筹码评分", "chip"),
            ("原始综合分", "overall")
        ]
        
        for text, value in sort_options:
            rb = ctk.CTkRadioButton(self.sidebar, text=text, variable=self.sort_var, value=value,
                                   fg_color=Colors.ACCENT_BLUE, hover_color=Colors.ACCENT_HOVER,
                                   text_color=Colors.TEXT_PRIMARY, font=ctk.CTkFont(size=FontSize.SM),
                                   command=self._on_sort_changed)
            rb.pack(fill="x", padx=Spacing.LG, pady=2)
        
        ctk.CTkFrame(self.sidebar, fg_color=Colors.BORDER, height=1).pack(fill="x", padx=Spacing.MD, pady=Spacing.MD)
        
        # ==================== 加权比例设置 ====================
        weight_label = ctk.CTkLabel(self.sidebar, text="⚖️ 加权比例", font=ctk.CTkFont(size=FontSize.SM, weight="bold"),
                                    text_color=Colors.TEXT_SECONDARY, anchor="w")
        weight_label.pack(fill="x", padx=Spacing.LG, pady=(Spacing.SM, Spacing.SM))
        
        # 加权滑块
        weight_items = [
            ("技术面", "tech", 40, Colors.SUCCESS),
            ("基本面", "fund", 20, Colors.ACCENT_BLUE),
            ("筹码面", "chip", 40, Colors.WARNING),
            ("热门板块", "hot", 0, Colors.DANGER)
        ]
        
        for name, key, default, color in weight_items:
            row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
            row.pack(fill="x", padx=Spacing.MD, pady=2)
            
            ctk.CTkLabel(row, text=name, font=ctk.CTkFont(size=FontSize.XS),
                        text_color=Colors.TEXT_SECONDARY, width=50).pack(side="left")
            
            slider = ctk.CTkSlider(row, from_=0, to=100, number_of_steps=20,
                                  fg_color=Colors.BG_CARD, progress_color=color,
                                  button_color=color, button_hover_color=color,
                                  width=100, height=16)
            slider.set(default)
            slider.pack(side="left", padx=Spacing.SM)
            
            value_label = ctk.CTkLabel(row, text=f"{default}%", font=ctk.CTkFont(size=FontSize.XS),
                                      text_color=Colors.TEXT_PRIMARY, width=35)
            value_label.pack(side="left")
            
            self.weight_sliders[key] = (slider, value_label)
            slider.configure(command=lambda v, k=key: self._on_weight_changed(k, v))
        
        # 加权比例显示
        self.weight_display = ctk.CTkLabel(self.sidebar, text="40% : 20% : 40% : 0%",
                                          font=ctk.CTkFont(size=FontSize.XS),
                                          text_color=Colors.TEXT_MUTED)
        self.weight_display.pack(fill="x", padx=Spacing.LG, pady=Spacing.SM)
        
        # 重算综合分按钮
        ActionButton(self.sidebar, text="重算综合分", icon="🔄", variant="primary",
                    command=self._on_recalculate).pack(fill="x", padx=Spacing.MD, pady=Spacing.SM)
        
        ctk.CTkFrame(self.sidebar, fg_color=Colors.BORDER, height=1).pack(fill="x", padx=Spacing.MD, pady=Spacing.MD)
        
        # ==================== 其他功能 ====================
        other_label = ctk.CTkLabel(self.sidebar, text="🔧 其他", font=ctk.CTkFont(size=FontSize.SM, weight="bold"),
                                   text_color=Colors.TEXT_SECONDARY, anchor="w")
        other_label.pack(fill="x", padx=Spacing.LG, pady=(Spacing.SM, Spacing.SM))
        
        # 启动原系统
        ActionButton(self.sidebar, text="启动完整版GUI", icon="🖥️", variant="secondary",
                    command=self._on_launch_original).pack(fill="x", padx=Spacing.MD, pady=2)
        
        # 状态区
        ctk.CTkFrame(self.sidebar, fg_color=Colors.BORDER, height=1).pack(fill="x", padx=Spacing.MD, pady=Spacing.MD)
        
        status_label = ctk.CTkLabel(self.sidebar, text="📋 状态", font=ctk.CTkFont(size=FontSize.SM, weight="bold"),
                                    text_color=Colors.TEXT_SECONDARY, anchor="w")
        status_label.pack(fill="x", padx=Spacing.LG, pady=(Spacing.SM, Spacing.SM))
        
        self.status_text = ctk.CTkTextbox(self.sidebar, height=200, fg_color=Colors.BG_CARD,
                                          text_color=Colors.TEXT_SECONDARY, font=ctk.CTkFont(size=FontSize.XS),
                                          corner_radius=Radius.SM)
        self.status_text.pack(fill="x", padx=Spacing.MD, pady=Spacing.SM)
        self.status_text.insert("1.0", "系统就绪...\n")
    
    def _create_main_content(self):
        # 顶部栏
        header = ctk.CTkFrame(self.main_content, fg_color="transparent", height=56)
        header.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)
        header.pack_propagate(False)
        
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        
        ctk.CTkLabel(left, text="交易仪表板", font=ctk.CTkFont(size=FontSize.XL, weight="bold"),
                    text_color=Colors.TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkLabel(left, text=datetime.now().strftime("%Y年%m月%d日 %A"),
                    font=ctk.CTkFont(size=FontSize.SM), text_color=Colors.TEXT_MUTED).pack(anchor="w")
        
        # 搜索
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right")
        
        self.search_entry = ctk.CTkEntry(right, placeholder_text="🔍 输入股票代码...",
                                         width=200, height=40, fg_color=Colors.BG_SECONDARY,
                                         border_color=Colors.BORDER, text_color=Colors.TEXT_PRIMARY,
                                         corner_radius=Radius.SM)
        self.search_entry.pack(side="left", padx=(0, Spacing.SM))
        self.search_entry.bind("<Return>", self._on_search)
        self.search_entry.bind("<KP_Enter>", self._on_search)  # 小键盘回车
        
        # 搜索按钮
        self.search_btn = ActionButton(right, text="搜索", icon="🔍", variant="primary",
                                       width=80, command=self._on_search)
        self.search_btn.pack(side="left")
        
        # 指标卡片行
        metrics_frame = ctk.CTkFrame(self.main_content, fg_color="transparent", height=120)
        metrics_frame.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
        
        for i, name in enumerate(["上证指数", "深证成指", "创业板指", "科创50"]):
            card = MetricCard(metrics_frame, label=name, value="加载中...", change="--")
            card.pack(side="left", fill="both", expand=True, padx=(0 if i == 0 else Spacing.SM, 0))
            self.metric_cards.append(card)
        
        # 内容区
        content_row = ctk.CTkFrame(self.main_content, fg_color="transparent")
        content_row.pack(fill="both", expand=True, padx=Spacing.LG, pady=0)
        
        # 左侧：股票列表
        left_col = ctk.CTkFrame(content_row, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, Spacing.SM))
        
        list_header = ctk.CTkFrame(left_col, fg_color="transparent")
        list_header.pack(fill="x", pady=(0, Spacing.MD))
        
        self.list_title = ctk.CTkLabel(list_header, text="📋 今日推荐股票 (按加权综合分排序)",
                    font=ctk.CTkFont(size=FontSize.LG, weight="bold"),
                    text_color=Colors.TEXT_PRIMARY)
        self.list_title.pack(side="left")
        
        self.stock_list = ctk.CTkScrollableFrame(left_col, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.MD)
        self.stock_list.pack(fill="both", expand=True)
        
        # 右侧：详情卡片
        right_col = ctk.CTkFrame(content_row, fg_color="transparent", width=420)
        right_col.pack(side="right", fill="y", padx=(Spacing.SM, 0))
        right_col.pack_propagate(False)
        
        ctk.CTkLabel(right_col, text="📊 股票详情", font=ctk.CTkFont(size=FontSize.LG, weight="bold"),
                    text_color=Colors.TEXT_PRIMARY, anchor="w").pack(fill="x", pady=(0, Spacing.MD))
        
        self.detail_card = ctk.CTkFrame(right_col, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.MD)
        self.detail_card.pack(fill="both", expand=True)
        
        self._create_detail_card()
    
    def _create_detail_card(self):
        """创建详情卡片内容"""
        # 头部
        header = ctk.CTkFrame(self.detail_card, fg_color="transparent")
        header.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)
        
        self.detail_name = ctk.CTkLabel(header, text="选择一只股票", font=ctk.CTkFont(size=FontSize.LG, weight="bold"),
                                        text_color=Colors.TEXT_PRIMARY, anchor="w")
        self.detail_name.pack(anchor="w")
        
        self.detail_code = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=FontSize.SM),
                                        text_color=Colors.TEXT_MUTED, anchor="w")
        self.detail_code.pack(anchor="w")
        
        ctk.CTkFrame(self.detail_card, fg_color=Colors.BORDER, height=1).pack(fill="x", padx=Spacing.LG)
        
        # 评分区
        scores_frame = ctk.CTkFrame(self.detail_card, fg_color="transparent")
        scores_frame.pack(fill="x", padx=Spacing.LG, pady=Spacing.MD)
        
        ctk.CTkLabel(scores_frame, text="综合评分", font=ctk.CTkFont(size=FontSize.SM),
                    text_color=Colors.TEXT_SECONDARY).pack(anchor="w", pady=(0, Spacing.SM))
        
        scores_row = ctk.CTkFrame(scores_frame, fg_color="transparent")
        scores_row.pack(fill="x")
        
        self.score_labels = {}
        for name, color in [("技术面", Colors.SUCCESS), ("基本面", Colors.ACCENT_BLUE), 
                           ("资金面", Colors.WARNING), ("筹码", Colors.DANGER)]:
            frame = ctk.CTkFrame(scores_row, fg_color=Colors.BG_CARD, corner_radius=Radius.SM)
            frame.pack(side="left", fill="both", expand=True, padx=2)
            
            score_lbl = ctk.CTkLabel(frame, text="--", font=ctk.CTkFont(size=FontSize.XXL, weight="bold"),
                                    text_color=color)
            score_lbl.pack(pady=(Spacing.MD, Spacing.XS))
            
            ctk.CTkLabel(frame, text=name, font=ctk.CTkFont(size=FontSize.XS),
                        text_color=Colors.TEXT_SECONDARY).pack(pady=(0, Spacing.MD))
            
            self.score_labels[name] = score_lbl
        
        ctk.CTkFrame(self.detail_card, fg_color=Colors.BORDER, height=1).pack(fill="x", padx=Spacing.LG)
        
        # 分析建议
        analysis_frame = ctk.CTkFrame(self.detail_card, fg_color="transparent")
        analysis_frame.pack(fill="x", padx=Spacing.LG, pady=Spacing.MD)
        
        ctk.CTkLabel(analysis_frame, text="分析建议", font=ctk.CTkFont(size=FontSize.SM),
                    text_color=Colors.TEXT_SECONDARY).pack(anchor="w", pady=(0, Spacing.SM))
        
        self.analysis_text = ctk.CTkTextbox(analysis_frame, height=100, fg_color=Colors.BG_CARD,
                                           text_color=Colors.TEXT_PRIMARY, font=ctk.CTkFont(size=FontSize.SM),
                                           corner_radius=Radius.SM)
        self.analysis_text.pack(fill="x")
        self.analysis_text.insert("1.0", "点击左侧股票查看详细分析...")
        self.analysis_text.configure(state="disabled")
        
        ctk.CTkFrame(self.detail_card, fg_color=Colors.BORDER, height=1).pack(fill="x", padx=Spacing.LG)
        
        # 操作按钮（说明）
        actions_frame = ctk.CTkFrame(self.detail_card, fg_color="transparent")
        actions_frame.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)
        
        note = ctk.CTkLabel(actions_frame, text="💡 提示：实际交易请使用券商软件",
                           font=ctk.CTkFont(size=FontSize.XS), text_color=Colors.TEXT_MUTED)
        note.pack(anchor="w")
    
    # ==================== 事件处理 ====================
    def _update_status(self, msg: str):
        """更新状态显示"""
        def update():
            self.status_text.insert("end", f"{datetime.now().strftime('%H:%M:%S')} {msg}\n")
            self.status_text.see("end")
        self.after(0, update)
    
    def _load_data(self, sort_by: str = None):
        """加载数据"""
        if sort_by is None:
            sort_by = self.current_sort_by
        self._update_status("正在加载数据...")
        
        def load():
            # 加载指数
            indices = self.service.fetch_index_quotes()
            self.after(0, lambda: self._update_indices(indices))
            
            # 加载股票
            self.service.load_batch_scores()
            stocks = self.service.get_top_stocks(30, sort_by=sort_by)
            self.after(0, lambda: self._update_stock_list(stocks, sort_by))
            
            # 更新标题
            sort_names = {
                'weighted': '加权综合分',
                'tech': '技术面评分',
                'fund': '基本面评分',
                'chip': '筹码评分',
                'overall': '原始综合分'
            }
            title = f"📋 今日推荐股票 (按{sort_names.get(sort_by, '评分')}排序)"
            self.after(0, lambda: self.list_title.configure(text=title))
            
            self._update_status(f"已加载 {len(stocks)} 只推荐股票 (按{sort_names.get(sort_by, '评分')}排序)")
        
        threading.Thread(target=load, daemon=True).start()
    
    def _update_indices(self, indices):
        for i, data in enumerate(indices):
            if i < len(self.metric_cards):
                self.metric_cards[i].update_data(data['value'], data['change'], data['is_positive'])
    
    def _update_stock_list(self, stocks, sort_by: str = 'weighted'):
        for row in self.stock_rows:
            row.destroy()
        self.stock_rows.clear()
        
        for stock in stocks:
            # 根据排序方式显示对应分数
            display_score = stock.get('display_score', stock.get('overall_score', 0))
            score_type = stock.get('score_type', '综合分')
            
            row = StockRow(
                self.stock_list,
                name=stock['name'],
                code=stock['code'],
                score=f"{display_score:.1f}分",
                recommendation=score_type,
                is_positive=display_score >= 7,
                on_click=lambda s=stock: self._on_stock_click(s)
            )
            row.pack(fill="x", padx=Spacing.MD, pady=Spacing.XS)
            self.stock_rows.append(row)
        
        if stocks:
            self._on_stock_click(stocks[0])
    
    def _on_stock_click(self, stock: Dict):
        """点击股票"""
        self.selected_stock = stock['code']
        
        detail = self.service.get_stock_detail(stock['code']) or stock
        
        self.detail_name.configure(text=detail['name'])
        self.detail_code.configure(text=f"{detail['code']} · {detail.get('industry', 'A股')}")
        
        # 更新评分
        self.score_labels["技术面"].configure(text=f"{int(detail.get('tech_score', 0) * 10)}")
        self.score_labels["基本面"].configure(text=f"{int(detail.get('fund_score', 0) * 10)}")
        self.score_labels["资金面"].configure(text=f"{int(detail.get('capital_score', 0) * 10)}")
        self.score_labels["筹码"].configure(text=f"{int(detail.get('chip_score', 0) * 10)}")
        
        # 更新分析
        analysis = detail.get('recommendation', '') or detail.get('analysis', '') or '暂无分析'
        trend = detail.get('trend', '')
        chip_level = detail.get('chip_level', '')
        
        # 计算加权综合分
        weighted = detail.get('weighted_score', 0)
        if not weighted and hasattr(self.service, 'calculate_weighted_score'):
            # 尝试从原始数据重新计算
            stock_data = self.service.batch_scores.get(detail.get('code', ''), {})
            if stock_data:
                weighted = self.service.calculate_weighted_score(stock_data)
        
        full_analysis = f"原始综合评分: {detail.get('overall_score', 0):.1f}\n"
        full_analysis += f"加权综合评分: {weighted:.1f}\n"
        full_analysis += f"技术面: {detail.get('tech_score', 0):.1f} | 基本面: {detail.get('fund_score', 0):.1f} | 筹码: {detail.get('chip_score', 0):.1f}\n"
        if trend:
            full_analysis += f"趋势: {trend}\n"
        if chip_level:
            full_analysis += f"筹码等级: {chip_level}\n"
        full_analysis += f"\n{analysis}"
        
        self.analysis_text.configure(state="normal")
        self.analysis_text.delete("1.0", "end")
        self.analysis_text.insert("1.0", full_analysis)
        self.analysis_text.configure(state="disabled")
        
        self._update_status(f"已选中: {detail['name']} ({stock['code']}) - 评分 {detail.get('overall_score', 0):.1f}")
    
    def _on_search(self, event=None):
        query = self.search_entry.get().strip()
        if query:
            detail = self.service.get_stock_detail(query)
            if detail:
                self._on_stock_click(detail)
            else:
                self._update_status(f"❌ 未找到股票: {query}")
    
    def _on_sort_changed(self):
        """排序方式变更"""
        self.current_sort_by = self.sort_var.get()
        self._load_data(self.current_sort_by)
    
    def _on_weight_changed(self, key: str, value: float):
        """加权比例变更"""
        int_value = int(value)
        slider, label = self.weight_sliders[key]
        label.configure(text=f"{int_value}%")
        
        # 更新显示
        weights = {
            'tech': int(self.weight_sliders['tech'][0].get()),
            'fund': int(self.weight_sliders['fund'][0].get()),
            'chip': int(self.weight_sliders['chip'][0].get()),
            'hot': int(self.weight_sliders['hot'][0].get())
        }
        self.weight_display.configure(
            text=f"{weights['tech']}% : {weights['fund']}% : {weights['chip']}% : {weights['hot']}%"
        )
    
    def _on_recalculate(self):
        """重新计算综合分"""
        # 获取当前加权比例
        weights = {
            'tech': int(self.weight_sliders['tech'][0].get()),
            'fund': int(self.weight_sliders['fund'][0].get()),
            'chip': int(self.weight_sliders['chip'][0].get()),
            'hot': int(self.weight_sliders['hot'][0].get())
        }
        
        # 设置到服务
        self.service.set_weights(weights['tech'], weights['fund'], weights['chip'], weights['hot'])
        
        # 切换到加权综合分排序并刷新
        self.sort_var.set('weighted')
        self.current_sort_by = 'weighted'
        self._load_data('weighted')
    
    def _on_update_kline(self):
        """更新K线"""
        self._update_status("🔄 开始更新K线数据...")
        self.service.update_kline_data(callback=self._load_data)
    
    def _on_generate_scores(self):
        """生成评分"""
        self._update_status("🔄 开始生成评分...")
        self.service.generate_scores(callback=self._load_data)
    
    def _on_hot_sectors(self):
        """热门板块分析"""
        self._update_status("🔥 分析热门板块...")
        
        def analyze():
            try:
                # 统计各行业股票数量和平均分
                industry_stats = {}
                for code, data in self.service.batch_scores.items():
                    if not isinstance(data, dict):
                        continue
                    industry = data.get('industry', '未知')
                    if not industry or industry == '未知':
                        continue
                    
                    if industry not in industry_stats:
                        industry_stats[industry] = {'count': 0, 'total_score': 0, 'stocks': []}
                    
                    score = data.get('overall_score', 0)
                    industry_stats[industry]['count'] += 1
                    industry_stats[industry]['total_score'] += score
                    if score >= 7:  # 只收集高分股
                        industry_stats[industry]['stocks'].append({
                            'code': code,
                            'name': data.get('name', code),
                            'score': score
                        })
                
                # 计算平均分并排序
                hot_sectors = []
                for industry, stats in industry_stats.items():
                    if stats['count'] >= 3:  # 至少3只股票的板块
                        avg_score = stats['total_score'] / stats['count']
                        high_score_count = len(stats['stocks'])
                        hot_sectors.append({
                            'industry': industry,
                            'avg_score': avg_score,
                            'count': stats['count'],
                            'high_score_count': high_score_count,
                            'top_stocks': sorted(stats['stocks'], key=lambda x: x['score'], reverse=True)[:5]
                        })
                
                # 按高分股数量和平均分排序
                hot_sectors.sort(key=lambda x: (x['high_score_count'], x['avg_score']), reverse=True)
                
                # 显示结果
                self._update_status("\n" + "=" * 40)
                self._update_status("🔥 热门板块分析结果")
                self._update_status("=" * 40)
                
                for i, sector in enumerate(hot_sectors[:10], 1):
                    self._update_status(f"\n{i}. 【{sector['industry']}】")
                    self._update_status(f"   平均分: {sector['avg_score']:.1f} | 股票数: {sector['count']} | 高分股: {sector['high_score_count']}")
                    if sector['top_stocks']:
                        top_names = ", ".join([f"{s['name']}({s['score']:.1f})" for s in sector['top_stocks'][:3]])
                        self._update_status(f"   热门: {top_names}")
                
                self._update_status("\n" + "=" * 40)
                self._update_status(f"✅ 共分析 {len(industry_stats)} 个板块")
                
            except Exception as e:
                self._update_status(f"❌ 板块分析失败: {e}")
        
        threading.Thread(target=analyze, daemon=True).start()
    
    def _on_launch_original(self):
        """启动原系统"""
        self.service.launch_original_gui()


# ==================== 入口 ====================
def main():
    app = TradingApp()
    app.mainloop()


if __name__ == "__main__":
    main()
