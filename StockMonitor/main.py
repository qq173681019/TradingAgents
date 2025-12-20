import os
import sys
import tkinter as tk
from tkinter import messagebox
import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import threading
import subprocess
import requests

# ==================== 0. 智能中文修复 (核心修改) ====================
def get_chinese_font():
    """检测并返回系统中可用的可用中文字体"""
    # 优先列表：微软雅黑 (Win默认), 黑体 (Win通用), Arial Unicode (Mac), PingFang (Mac)
    priority_fonts = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'PingFang SC']
    
    # 获取系统所有字体名
    system_fonts = set(f.name for f in font_manager.fontManager.ttflist)
    
    for f in priority_fonts:
        if f in system_fonts:
            print(f"✅ 已检测到中文字体: {f}")
            return f
            
    # 如果没找到，尝试回退配置
    return 'sans-serif'

# 获取最佳字体
CHINESE_FONT = get_chinese_font()

# 全局应用
plt.rcParams['font.sans-serif'] = [CHINESE_FONT]
plt.rcParams['axes.unicode_minus'] = False 

# ==================== 1. 智能路径配置 ====================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
TRADING_SHARED_DIR = os.path.join(ROOT_DIR, 'TradingShared')
API_DIR = os.path.join(TRADING_SHARED_DIR, 'api')
LIBS_DIR = os.path.join(TRADING_SHARED_DIR, 'libs')

if API_DIR not in sys.path and os.path.exists(API_DIR):
    sys.path.insert(0, API_DIR)
if TRADING_SHARED_DIR not in sys.path and os.path.exists(TRADING_SHARED_DIR):
    sys.path.insert(0, TRADING_SHARED_DIR)

# ==================== 2. 导入与补丁 ====================
CHOICE_INSTALLED = False
ChoiceAPI = None 

try:
    import EmQuantAPI
    # [补丁] 强制修改 EmQuantAPI 寻找 DLL 的逻辑
    def custom_get_dll_path():
        is_64bits = sys.maxsize > 2**32
        dll_name = "EmQuantAPI_x64.dll" if is_64bits else "EmQuantAPI.dll"
        dll_path = os.path.join(LIBS_DIR, 'windows', dll_name)
        if os.path.exists(dll_path):
            return dll_path
        return ""

    EmQuantAPI.UtilAccess.GetLibraryPath = staticmethod(custom_get_dll_path)
    ChoiceAPI = EmQuantAPI.c 
    CHOICE_INSTALLED = True
except ImportError:
    pass
except AttributeError:
    pass

# ==================== 3. 导入 Config ====================
try:
    import config
except ImportError:
    class ConfigMock:
        TUSHARE_TOKEN = ""
        CHOICE_USERNAME = ""
        CHOICE_PASSWORD = ""
    config = ConfigMock()

try:
    import tushare as ts
except ImportError:
    pass

# ==================== 4. 指标计算函数 ====================
def EMA(S: np.ndarray, N: int) -> np.ndarray:
    return pd.Series(S).ewm(span=N, adjust=False).mean().values

def MACD(CLOSE: np.ndarray, SHORT: int = 12, LONG: int = 26, M: int = 9) -> tuple:
    DIF = EMA(CLOSE, SHORT) - EMA(CLOSE, LONG)
    DEA = EMA(DIF, M)
    MACD_BAR = (DIF - DEA) * 2
    return DIF, DEA, MACD_BAR

# ==================== 5. 数据获取类 ====================
class DataFetcher:
    def __init__(self):
        self.pro = None
        self.choice_active = False
        if CHOICE_INSTALLED:
            self.init_choice()
        self.init_tushare()

    def init_tushare(self):
        token = getattr(config, 'TUSHARE_TOKEN', '')
        if token:
            try:
                ts.set_token(token)
                self.pro = ts.pro_api()
            except Exception:
                pass

    def init_choice(self):
        try:
            username = getattr(config, 'CHOICE_USERNAME', '')
            password = getattr(config, 'CHOICE_PASSWORD', '')
            login_str = "ForceLogin=1"
            if username and password:
                login_str += f",User={username},Password={password}"
            
            login_result = ChoiceAPI.start(login_str, '', lambda x: None)
            
            if hasattr(login_result, 'ErrorCode') and login_result.ErrorCode == 0:
                self.choice_active = True
                print("✅ Choice 登录成功")
            else:
                # 登录失败时明确标记不可用
                self.choice_active = False
                err_msg = getattr(login_result, 'ErrorMsg', '未知错误')
                print(f"⚠️ Choice 暂时不可用 (代码 {login_result.ErrorCode}): {err_msg}")
                if login_result.ErrorCode == 35:
                    print("提示: 请尝试解绑其他设备或联系 Choice 客服。程序将自动切换至备用源。")
        except Exception as e:
            print(f"❌ Choice 初始化异常: {e}")
            self.choice_active = False

    def get_sina_data(self, code):
        """新浪财经免费接口"""
        try:
            sina_code = code
            if code.endswith('.SH'): sina_code = 'sh' + code.split('.')[0]
            elif code.endswith('.SZ'): sina_code = 'sz' + code.split('.')[0]
            elif code.endswith('.BJ'): sina_code = 'bj' + code.split('.')[0]
            else:
                if code.startswith('6'): sina_code = 'sh' + code
                elif code.startswith('8') or code.startswith('4'): sina_code = 'bj' + code
                else: sina_code = 'sz' + code

            url = f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_code}&scale=1&ma=no&datalen=300"
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            r = requests.get(url, headers=headers, timeout=3)
            data = r.json()
            
            if not data: return pd.DataFrame()

            df = pd.DataFrame(data)
            df = df.rename(columns={
                'day': 'trade_time', 'open': 'Open', 'high': 'High', 
                'low': 'Low', 'close': 'Close', 'volume': 'Volume'
            })
            df['trade_time'] = pd.to_datetime(df['trade_time'])
            df.set_index('trade_time', inplace=True)
            
            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
            
            return df
        except Exception:
            return pd.DataFrame()

    def get_realtime_data(self, code, use_choice=True):
        std_code = code 
        if not code.endswith(('.SH', '.SZ', '.BJ')):
            if code.startswith('6'): std_code = f"{code}.SH"
            elif code.startswith(('4', '8')): std_code = f"{code}.BJ"
            else: std_code = f"{code}.SZ"

        # 1. Choice
        if use_choice and CHOICE_INSTALLED and self.choice_active:
            try:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=10)
                data = ChoiceAPI.csd(
                    std_code, "OPEN,HIGH,LOW,CLOSE,VOLUME", 
                    start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), 
                    "period=1,adjustflag=1,curdate=1"
                )
                if hasattr(data, 'ErrorCode') and data.ErrorCode == 0:
                     if hasattr(data, 'Data') and std_code in data.Data:
                        stock_data = data.Data[std_code]
                        if len(stock_data) >= 5:
                            df = pd.DataFrame({
                                'Open': stock_data[0], 'High': stock_data[1], 'Low': stock_data[2],
                                'Close': stock_data[3], 'Volume': stock_data[4]
                            })
                            if hasattr(data, 'Dates'): df.index = pd.to_datetime(data.Dates)
                            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                            df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
                            return df.tail(300), "Choice"
            except Exception:
                pass

        # 2. 新浪财经
        df_sina = self.get_sina_data(code)
        if not df_sina.empty:
            return df_sina, "新浪财经"

        # 3. Tushare
        try:
            if self.pro:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=5)
                df = ts.pro_bar(ts_code=std_code, adj='qfq', 
                              start_date=start_date.strftime('%Y%m%d'), end_date=end_date.strftime('%Y%m%d'), 
                              freq='1min')
                if df is not None and not df.empty:
                    df = df.sort_values('trade_date').reset_index(drop=True)
                    df['trade_time'] = pd.to_datetime(df['trade_time'])
                    df.set_index('trade_time', inplace=True)
                    df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'vol': 'Volume'})
                    return df.tail(300), "Tushare"
        except Exception:
            pass
            
        return pd.DataFrame(), "Failed"

# ==================== 6. GUI主程序 ====================
class StockMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VibeStock 智能监控终端")
        self.root.geometry("1000x800")
        
        self.fetcher = DataFetcher()
        self.current_code = "000001" 
        self.df = None
        self.last_signal_time = None
        self.kline_options = [30, 60, 120, 'D']
        self.kline_idx = 1
        
        self._setup_ui()
        self._start_timer()

    def _setup_ui(self):
        control_frame = tk.Frame(self.root, pady=5)
        control_frame.pack(side=tk.TOP, fill=tk.X)
        
        tk.Label(control_frame, text="股票代码:").pack(side=tk.LEFT, padx=5)
        self.entry_code = tk.Entry(control_frame, width=10)
        self.entry_code.insert(0, self.current_code)
        self.entry_code.pack(side=tk.LEFT, padx=5)
        
        self.use_choice_var = tk.BooleanVar(value=True)
        self.chk_choice = tk.Checkbutton(control_frame, text="优先Choice", variable=self.use_choice_var)
        self.chk_choice.pack(side=tk.LEFT, padx=5)
        
        btn_refresh = tk.Button(control_frame, text="确认/刷新", command=self.manual_refresh, bg="#e1f5fe")
        btn_refresh.pack(side=tk.LEFT, padx=5)
        
        self.lbl_status = tk.Label(control_frame, text="准备就绪", fg="gray")
        self.lbl_status.pack(side=tk.LEFT, padx=20)
        
        self.fig = mpf.figure(style='yahoo', figsize=(10, 8))
        self.fig_canvas = Figure(figsize=(10, 8), dpi=100)
        
        gs = self.fig_canvas.add_gridspec(3, 1, height_ratios=[3, 1, 1.5])
        self.ax_kline = self.fig_canvas.add_subplot(gs[0])
        self.ax_vol = self.fig_canvas.add_subplot(gs[1], sharex=self.ax_kline)
        self.ax_macd = self.fig_canvas.add_subplot(gs[2], sharex=self.ax_kline)
        
        self.canvas = FigureCanvasTkAgg(self.fig_canvas, master=self.root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect('scroll_event', self._on_scroll)

    def _start_timer(self):
        self.update_data()
        self.root.after(60000, self._start_timer)

    def manual_refresh(self):
        code = self.entry_code.get().strip()
        if code:
            self.current_code = code
            self.last_signal_time = None
            self.update_data()

    def update_data(self):
        use_choice = self.use_choice_var.get()
        def task():
            self.root.after(0, lambda: self.lbl_status.config(text=f"获取 {self.current_code}...", fg="blue"))
            df, source = self.fetcher.get_realtime_data(self.current_code, use_choice=use_choice)
            self.root.after(0, lambda: self.handle_data_update(df, source))
        threading.Thread(target=task, daemon=True).start()

    def handle_data_update(self, df, source):
        if df.empty:
            self.lbl_status.config(text=f"获取失败: 数据源不可用 (Choice错误/新浪无数据)", fg="red")
            return
            
        self.df = df
        latest_price = df.iloc[-1]['Close']
        latest_time = df.index[-1].strftime('%H:%M')
        self.lbl_status.config(text=f"✅ 来源: {source} | 现价: {latest_price:.2f} | 更新: {latest_time}", fg="green")
        
        self.check_and_trigger_signal(df)
        self.redraw_chart()

    def check_and_trigger_signal(self, df):
        if df is None or len(df) < 30: return
        try:
            close_prices = df['Close'].values
            dif, dea, macd_bar = MACD(close_prices)
            curr_bar = macd_bar[-1]; prev_bar = macd_bar[-2]
            current_time_idx = df.index[-1]
            
            if self.last_signal_time == current_time_idx: return
            
            signal_triggered = False
            if prev_bar <= 0 and curr_bar > 0:
                print(f"【买入信号】{current_time_idx}"); self.run_bat_script("buy.bat"); signal_triggered = True
            elif prev_bar >= 0 and curr_bar < 0:
                print(f"【卖出信号】{current_time_idx}"); self.run_bat_script("sell.bat"); signal_triggered = True
            
            if signal_triggered: self.last_signal_time = current_time_idx
        except Exception as e: print(f"信号检测错误: {e}")

    def run_bat_script(self, script_name):
        try:
            script_path = os.path.join(CURRENT_DIR, script_name)
            if os.path.exists(script_path): subprocess.Popen([script_path, self.current_code], shell=True)
        except Exception: pass

    def _on_scroll(self, event):
        if event.button == 'up': 
            if self.kline_idx > 0: self.kline_idx -= 1
        elif event.button == 'down': 
            if self.kline_idx < len(self.kline_options) - 1: self.kline_idx += 1
        self.redraw_chart()

    def redraw_chart(self):
        if self.df is None or self.df.empty: return
        try:
            opt = self.kline_options[self.kline_idx]
            plot_df = self.df.copy()
            title_suffix = ""
            
            if opt == 'D':
                plot_df = plot_df.resample('D').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna().tail(60)
                title_suffix = "模式: 日线"
            else:
                plot_df = plot_df.tail(int(opt))
                title_suffix = f"模式: 最近{opt}分钟"

            close_prices = plot_df['Close'].values
            dif, dea, macd_bar = MACD(close_prices)
            buy_signals = [np.nan]*len(plot_df); sell_signals = [np.nan]*len(plot_df)
            
            for i in range(1, len(macd_bar)):
                if i >= len(macd_bar): break
                if np.isnan(macd_bar[i-1]) or np.isnan(macd_bar[i]): continue
                if macd_bar[i-1] <= 0 and macd_bar[i] > 0: buy_signals[i] = plot_df['Low'].iloc[i] * 0.999 
                elif macd_bar[i-1] >= 0 and macd_bar[i] < 0: sell_signals[i] = plot_df['High'].iloc[i] * 1.001

            self.ax_kline.clear(); self.ax_vol.clear(); self.ax_macd.clear()
            
            mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='inherit')
            
            # --- 关键修复：将中文字体强制注入到样式配置中 ---
            # rc 参数会覆盖 matplotlib 的默认配置
            s = mpf.make_mpf_style(
                marketcolors=mc, 
                base_mpf_style='yahoo', 
                rc={'font.family': CHINESE_FONT}
            )

            ap = []
            if not np.all(np.isnan(buy_signals)): ap.append(mpf.make_addplot(buy_signals, type='scatter', markersize=100, marker='^', color='m', ax=self.ax_kline))
            if not np.all(np.isnan(sell_signals)): ap.append(mpf.make_addplot(sell_signals, type='scatter', markersize=100, marker='v', color='k', ax=self.ax_kline))
            ap.append(mpf.make_addplot(dif, color='orange', width=1, ax=self.ax_macd))
            ap.append(mpf.make_addplot(dea, color='blue', width=1, ax=self.ax_macd))
            ap.append(mpf.make_addplot(macd_bar, type='bar', color=['red' if v > 0 else 'green' for v in macd_bar], ax=self.ax_macd))

            mpf.plot(plot_df, type='candle', ax=self.ax_kline, volume=self.ax_vol, addplot=ap, style=s, datetime_format='%H:%M', ylabel='', ylabel_lower='')
            
            # 设置标题时再次确认字体（双重保险）
            self.ax_kline.set_title(f"{self.current_code} - {title_suffix}", fontsize=12, fontname=CHINESE_FONT)
            
            self.canvas.draw()
        except Exception as e: print(f"绘图错误: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = StockMonitorApp(root)
    root.mainloop()