import tkinter as tk
from tkinter import messagebox, ttk
import mplfinance as mpf
import pandas as pd
import datetime
import threading
import time
import os
import shutil
import sys
import importlib.util
import requests
import json

# --- TradingShared路径设置 ---
SHARED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'TradingShared')
if SHARED_PATH not in sys.path:
    sys.path.insert(0, SHARED_PATH)
if os.path.join(SHARED_PATH, 'api') not in sys.path:
    sys.path.insert(0, os.path.join(SHARED_PATH, 'api'))

# --- Matplotlib 后端设置 ---
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- 1. Choice 加载逻辑 ---
def force_load_choice():
    shared_api_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'TradingShared', 'api', 'EmQuantAPI.py')
    possible_paths = [
        r"C:\ChoiceTerminal\EmQuantAPI\Python\EmQuantAPI.py",
        r"D:\ChoiceTerminal\EmQuantAPI\Python\EmQuantAPI.py",
        r"C:\EmQuantAPI\Python\EmQuantAPI.py",
        shared_api_path,
        os.path.join(os.getcwd(), "EmQuantAPI.py")
    ]
    for file_path in possible_paths:
        if os.path.exists(file_path):
            try:
                spec = importlib.util.spec_from_file_location("EmQuantAPI", file_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules["EmQuantAPI"] = module
                spec.loader.exec_module(module)
                lib_path = os.path.dirname(file_path)
                if lib_path not in sys.path: sys.path.insert(0, lib_path)
                return module
            except: pass
    return None

c = force_load_choice()
HAS_CHOICE = False
if c is not None and hasattr(c, 'c_start'):
    HAS_CHOICE = True
else:
    try:
        import EmQuantAPI as c
        if hasattr(c, 'c_start'): HAS_CHOICE = True
    except: pass

# --- 2. AkShare 加载 ---
HAS_AKSHARE = False
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError: pass

# --- 3. SSL 修复 ---
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

# --- 配置 ---
try:
    from config import CHOICE_USER, CHOICE_PASS
except ImportError:
    CHOICE_USER = "user"
    CHOICE_PASS = "pass"

DEFAULT_CODE = "600519"

class StockMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("A股量化监控终端 V3 (Stable)")
        self.root.geometry("1100x850")
        
        self.init_datasources()
        
        self.raw_code = DEFAULT_CODE
        self.is_running = True
        
        self.create_gui()
        self.init_plot()
        
        # 延迟启动定时器，防止初始化未完成就刷新
        self.root.after(1000, self.start_timer)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def init_datasources(self):
        if HAS_CHOICE:
            try:
                login_res = c.c_start()
                if login_res.ErrorCode != 0:
                    c.c_start(f"ForceLogin=1,User={CHOICE_USER},Password={CHOICE_PASS}")
            except: pass

    def create_gui(self):
        ctrl_frame = tk.Frame(self.root, pady=10)
        ctrl_frame.pack(side=tk.TOP, fill=tk.X, padx=15)

        tk.Label(ctrl_frame, text="数据源:", font=("微软雅黑", 11)).pack(side=tk.LEFT)
        self.cmb_strategy = ttk.Combobox(
            ctrl_frame, 
            values=["Smart (Choice>Sina>Ak)", "Force Sina", "Force Choice"], 
            width=20, state="readonly"
        )
        self.cmb_strategy.current(0)
        self.cmb_strategy.pack(side=tk.LEFT, padx=5)

        tk.Label(ctrl_frame, text="代码:", font=("微软雅黑", 11)).pack(side=tk.LEFT, padx=(15, 0))
        self.entry_code = tk.Entry(ctrl_frame, width=8, font=("Arial", 11))
        self.entry_code.insert(0, self.raw_code)
        self.entry_code.pack(side=tk.LEFT, padx=5)

        btn = tk.Button(ctrl_frame, text="刷新", command=self.on_refresh_click, bg="#e1e1e1", width=10)
        btn.pack(side=tk.LEFT, padx=10)

        self.lbl_status = tk.Label(ctrl_frame, text="就绪", fg="blue", font=("微软雅黑", 10))
        self.lbl_status.pack(side=tk.RIGHT)

        self.plot_frame = tk.Frame(self.root)
        self.plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def init_plot(self):
        # 初始化空图表
        self.fig = mpf.figure(style='yahoo', figsize=(10, 8))
        self.ax1 = self.fig.add_subplot(2, 1, 1)
        self.ax2 = self.fig.add_subplot(2, 1, 2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # ================= 修复后的数据获取 =================

    def fetch_choice(self, pure_code, full_code):
        if not HAS_CHOICE: raise Exception("Choice SDK 未加载")
        
        c_suffix = ".SH" if pure_code.startswith("6") else ".SZ"
        if pure_code.startswith(("4", "8")): c_suffix = ".BSE"
        c_code = pure_code + c_suffix
        
        end = datetime.datetime.now().strftime("%Y-%m-%d")
        start = (datetime.datetime.now() - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        
        data = c.csd(c_code, "OPEN,HIGH,LOW,CLOSE,VOLUME", start, end, "period=6,adjustflag=1,curtype=1")
        
        if data.ErrorCode != 0: raise Exception(f"Choice Err: {data.ErrorMsg}")
        
        df = pd.DataFrame({
            'Date': pd.to_datetime(data.Dates),
            'Open': pd.to_numeric(data.Data[0]), 
            'High': pd.to_numeric(data.Data[1]), 
            'Low': pd.to_numeric(data.Data[2]),
            'Close': pd.to_numeric(data.Data[3]), 
            'Volume': pd.to_numeric(data.Data[4])
        })
        df.set_index('Date', inplace=True)
        return df.tail(240), "Choice"

    def fetch_sina(self, pure_code, full_code):
        # [Fix 1]: 添加 User-Agent 伪装，防止返回 Empty Data
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "http://finance.sina.com.cn/"
        }
        
        prefix = "sh" if pure_code.startswith("6") else "sz"
        sina_symbol = f"{prefix}{pure_code}"
        
        url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_symbol}&scale=1&ma=no&datalen=240"
        
        try:
            resp = requests.get(url, headers=headers, timeout=3)
            if resp.status_code != 200: raise Exception(f"HTTP {resp.status_code}")
            
            # [Fix 2]: 增加数据校验，防止解析空 JSON
            try:
                data_list = resp.json()
            except:
                raise Exception("Sina JSON Parse Err")

            if not data_list: 
                raise Exception("Sina Empty Data (Market Closed or Bad Code)")
            
            df = pd.DataFrame(data_list)
            df.rename(columns={'day': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col])
                
            return df, "Sina"
            
        except Exception as e:
            raise Exception(f"Sina: {str(e)}")

    def fetch_akshare(self, pure_code, full_code):
        if not HAS_AKSHARE: raise Exception("AkShare Missing")
        try:
            df = ak.stock_zh_a_hist_min_em(symbol=pure_code, start_date="2024-01-01", period="1", adjust="qfq")
            if df.empty: raise Exception("AkShare Empty")
            
            df.rename(columns={"时间": "Date", "开盘": "Open", "收盘": "Close", "最高": "High", "最低": "Low", "成交量": "Volume"}, inplace=True)
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']: df[col] = pd.to_numeric(df[col])
            return df.tail(240), "AkShare"
        except Exception as e:
            raise Exception(f"AkShare: {str(e)}")

    def smart_fetch(self):
        pure_code = self.entry_code.get().strip().split(".")[0]
        full_code = pure_code 
        strategy = self.cmb_strategy.get()
        
        methods = []
        if "Smart" in strategy:
            methods = [(self.fetch_choice, "Choice"), (self.fetch_sina, "Sina"), (self.fetch_akshare, "AkShare")]
        elif "Sina" in strategy:
            methods = [(self.fetch_sina, "Sina")]
        elif "Choice" in strategy:
            methods = [(self.fetch_choice, "Choice")]

        errors = []
        for func, name in methods:
            try:
                self.update_status_signal(f"尝试 {name}...", "blue")
                if name == "Sina": time.sleep(0.02)
                
                df, source = func(pure_code, full_code)
                return df, source, pure_code
            except Exception as e:
                # print(f"[{name} Failed]: {e}") # 调试用
                errors.append(f"{name}:{str(e)[:10]}")
                continue
        
        raise Exception(" | ".join(errors))

    # ================= 界面控制 =================

    def start_timer(self):
        if not self.is_running: return
        threading.Thread(target=self.run_task, daemon=True).start()
        # [Fix 3]: 使用更安全的 after 调用，检查窗口是否存在
        if self.root.winfo_exists():
            self.root.after(5000, self.start_timer)

    def on_refresh_click(self):
        threading.Thread(target=self.run_task, daemon=True).start()

    def update_status_signal(self, text, color):
        if self.root.winfo_exists():
            self.root.after(0, lambda: self.safe_config(self.lbl_status, text=text, fg=color))

    def safe_config(self, widget, **kwargs):
        # [Fix 4]: 安全配置 Widget 属性，防止 destroyed error
        try:
            if self.root.winfo_exists():
                widget.config(**kwargs)
        except: pass

    def run_task(self):
        try:
            df, source, code = self.smart_fetch()
            # 必须通过 after 回到主线程更新 UI
            if self.root.winfo_exists():
                self.root.after(0, lambda: self.update_success(df, source, code))
        except Exception as e:
            if self.root.winfo_exists():
                self.root.after(0, lambda: self.update_fail(str(e)))

    def update_success(self, df, source, code):
        try:
            if df.empty or not self.root.winfo_exists(): return
            
            latest = df.iloc[-1]
            price = latest['Close']
            curr_time = latest.name.strftime('%H:%M')
            
            self.safe_config(self.lbl_status, text=f"✅ {source} | {code} | {price:.2f} | {curr_time}", fg="#006400")
            
            self.ax1.clear(); self.ax2.clear()
            self.ax1.set_title(f"Code: {code} Source: {source}", fontsize=10)
            
            # [Fix 5]: 修复 style 报错，正确参数是 base_mpf_style
            mc = mpf.make_marketcolors(up='red', down='green', inherit=True)
            s = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='yahoo') 
            
            mpf.plot(
                df, 
                type='candle', 
                ax=self.ax1, 
                volume=self.ax2, 
                style=s,
                ylabel='',
                ylabel_lower=''
            )
            self.canvas.draw()
            
        except Exception as e:
            print(f"Plot Error Detail: {e}")
            self.safe_config(self.lbl_status, text=f"绘图错误: {e}", fg="red")

    def update_fail(self, msg):
        self.safe_config(self.lbl_status, text=f"⚠️ {msg}", fg="red")

    def on_close(self):
        self.is_running = False
        if HAS_CHOICE:
            try: c.c_stop()
            except: pass
        try:
            self.root.destroy()
        except: pass

if __name__ == "__main__":
    root = tk.Tk()
    app = StockMonitorApp(root)
    root.mainloop()