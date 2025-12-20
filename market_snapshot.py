import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
from datetime import datetime
import threading
import time

# ==================== 1. 路径环境配置 (核心修复) ====================
# 假设脚本位于 D:\TradingAgents\market_snapshot.py
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 定位 TradingShared 目录 (在当前目录的子目录下，或者根据你的描述可能在同级？)
# 根据描述：
# 脚本位置: TradingAgents\market_snapshot.py
# 共享库:   TradingAgents\TradingShared\
#           TradingAgents\TradingShared\api\EmQuantAPI.py
#           TradingAgents\TradingShared\libs\windows\EmQuantAPI_x64.dll
#           TradingAgents\TradingShared\config.py

TRADING_SHARED_DIR = os.path.join(CURRENT_SCRIPT_DIR, 'TradingShared')
API_DIR = os.path.join(TRADING_SHARED_DIR, 'api')
LIBS_DIR = os.path.join(TRADING_SHARED_DIR, 'libs')

print("-" * 60)
print(f"脚本位置: {CURRENT_SCRIPT_DIR}")
print(f"API 目录: {API_DIR}")
print(f"Libs目录: {LIBS_DIR}")

# 添加搜索路径，确保能 import config 和 EmQuantAPI
if TRADING_SHARED_DIR not in sys.path and os.path.exists(TRADING_SHARED_DIR):
    sys.path.insert(0, TRADING_SHARED_DIR)
if API_DIR not in sys.path and os.path.exists(API_DIR):
    sys.path.insert(0, API_DIR)

# 尝试导入 Config
try:
    import config
except ImportError:
    print("⚠️ 无法导入 config.py，请检查路径")
    class ConfigMock: CHOICE_USERNAME = ""; CHOICE_PASSWORD = ""
    config = ConfigMock()

# ==================== 2. Choice 补丁与导入 ====================
CHOICE_INSTALLED = False
ChoiceAPI = None

try:
    import EmQuantAPI
    
    # [补丁] 强制指定 DLL 绝对路径，解决 WinError 87
    def custom_get_dll_path():
        is_64bits = sys.maxsize > 2**32
        dll_name = "EmQuantAPI_x64.dll" if is_64bits else "EmQuantAPI.dll"
        
        # 强制指向 TradingShared/libs/windows
        dll_path = os.path.join(LIBS_DIR, 'windows', dll_name)
        
        # 转换为绝对路径 (这是解决 WinError 87 的关键)
        abs_dll_path = os.path.abspath(dll_path)
        
        if os.path.exists(abs_dll_path):
            print(f"✅ [补丁] 锁定 DLL 路径: {abs_dll_path}")
            return abs_dll_path
        else:
            print(f"❌ [补丁] DLL 文件未找到: {abs_dll_path}")
            return ""
    
    # 应用补丁：覆盖 GetLibraryPath 方法
    EmQuantAPI.UtilAccess.GetLibraryPath = staticmethod(custom_get_dll_path)
    
    # 获取核心类 c
    ChoiceAPI = EmQuantAPI.c
    CHOICE_INSTALLED = True
    print("✅ EmQuantAPI 模块导入成功")

except ImportError as e:
    print(f"❌ EmQuantAPI 导入失败: {e}")
except Exception as e:
    print(f"❌ 初始化异常: {e}")

# ==================== 3. 数据引擎类 ====================
class MarketDataEngine:
    def __init__(self):
        self.stock_codes = []
        self.df = pd.DataFrame()
        self.is_connected = False
        
        if CHOICE_INSTALLED:
            self.connect_choice()

    def connect_choice(self):
        try:
            # 从 config 读取账号密码
            username = getattr(config, 'CHOICE_USERNAME', '')
            password = getattr(config, 'CHOICE_PASSWORD', '')
            
            # 检测是否在调试器环境下
            import sys
            is_debugger = sys.gettrace() is not None or 'debugpy' in sys.modules
            
            if is_debugger:
                print("❌ 检测到调试器环境，Choice SDK无法工作")
                print("💡 请使用以下方式之一运行：")
                print("   1. 关闭调试器，直接运行: python market_snapshot.py")
                print("   2. 使用批处理文件启动")
                return False
            
            # 构建登录字符串
            login_str = "ForceLogin=1"
            if username and password:
                login_str += f",User={username},Password={password}"
                print(f"使用账号登录: {username}")
            
            # 登录
            login_result = ChoiceAPI.start(login_str, '', lambda x: None)
            
            if login_result.ErrorCode == 0:
                self.is_connected = True
                print("✅ Choice 登录成功")
                return True
            else:
                print(f"❌ Choice 登录失败 (Code {login_result.ErrorCode}): {login_result.ErrorMsg}")
                
                # 提供具体的错误处理建议
                if login_result.ErrorCode == 10001019:
                    print("💡 设备绑定错误解决方案：")
                    print("   1. 确保在非调试环境下运行")
                    print("   2. 检查Choice账号是否在此设备上激活")
                    print("   3. 尝试重新激活Choice终端")
                    print("   4. 或使用主程序的缓存模式")
                
                return False
        except Exception as e:
            print(f"❌ Choice 连接崩溃: {e}")
            # 这里的 WinError 87 可能会在 start 内部抛出，如果 DLL 路径不对
            return False

    def fetch_all_codes(self):
        """步骤1: 获取全市场代码列表"""
        if not self.is_connected: return []
        try:
            # 001004 = 全部A股
            date_str = datetime.now().strftime("%Y-%m-%d")
            sector_data = ChoiceAPI.sector("001004", date_str)
            if sector_data.ErrorCode != 0:
                print(f"板块获取失败: {sector_data.ErrorMsg}")
                return []
            self.stock_codes = sector_data.Data
            return self.stock_codes
        except Exception as e:
            print(f"代码列表异常: {e}")
            return []

    def fetch_snapshot(self, codes=None):
        """步骤2: 批量获取行情快照"""
        target_codes = codes if codes else self.stock_codes
        if not target_codes or not self.is_connected: 
            # 如果无法连接Choice，尝试从缓存文件获取数据
            return self._fetch_from_cache(target_codes)

        try:
            # 批量获取: 名称, 最新价, 涨跌幅
            data = ChoiceAPI.css(
                target_codes,
                "NAME,PRICE,DIFFER",
                "Ispandas=1,RowIndex=1"
            )
            if isinstance(data, pd.DataFrame):
                # 清洗数据
                data = data.rename(columns={'NAME': '名称', 'PRICE': '现价', 'DIFFER': '涨跌幅'})
                data['现价'] = pd.to_numeric(data['现价'], errors='coerce')
                data['涨跌幅'] = pd.to_numeric(data['涨跌幅'], errors='coerce')
                self.df = data
                return data
            return pd.DataFrame()
        except Exception as e:
            print(f"快照异常: {e}")
            # 如果API调用失败，尝试从缓存获取
            return self._fetch_from_cache(target_codes)

    def _fetch_from_cache(self, codes):
        """从缓存文件获取行情数据"""
        try:
            import json
            import os
            
            # 尝试从多个可能的缓存文件获取数据
            cache_files = [
                os.path.join(TRADING_SHARED_DIR, 'data', 'comprehensive_stock_data.json'),
                os.path.join(TRADING_SHARED_DIR, 'data', 'choice_cache.json'),
                os.path.join(CURRENT_SCRIPT_DIR, 'data', 'choice_cache.json')
            ]
            
            for cache_file in cache_files:
                if os.path.exists(cache_file):
                    print(f"📂 从缓存文件获取数据: {cache_file}")
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    # 提取股票数据
                    stocks_data = {}
                    if 'stocks' in cache_data:
                        stocks_data = cache_data['stocks']
                    elif 'data' in cache_data:
                        stocks_data = cache_data['data']
                    else:
                        stocks_data = cache_data
                    
                    # 构建DataFrame
                    data_list = []
                    for code in codes:
                        if code in stocks_data:
                            stock_info = stocks_data[code]
                            name = stock_info.get('name', stock_info.get('basic_info', {}).get('name', '未知'))
                            
                            # 获取最新价格
                            price = 0.0
                            change_pct = 0.0
                            
                            if 'kline_data' in stock_info and stock_info['kline_data']:
                                kline = stock_info['kline_data']
                                if 'latest_price' in kline:
                                    price = kline['latest_price']
                                elif 'daily' in kline and isinstance(kline['daily'], list) and len(kline['daily']) > 0:
                                    # 取最新一条K线数据
                                    latest_kline = kline['daily'][-1]
                                    price = latest_kline.get('close', 0)
                            
                            data_list.append({
                                '代码': code,
                                '名称': name,
                                '现价': float(price) if price else 0.0,
                                '涨跌幅': float(change_pct) if change_pct else 0.0
                            })
                    
                    if data_list:
                        df = pd.DataFrame(data_list)
                        df.set_index('代码', inplace=True)
                        print(f"✅ 从缓存获取到 {len(df)} 只股票数据")
                        self.df = df
                        return df
            
            print("❌ 未找到可用的缓存数据")
            return pd.DataFrame()
            
        except Exception as e:
            print(f"❌ 缓存数据获取失败: {e}")
            return pd.DataFrame()

# ==================== 4. GUI 界面类 ====================
class MarketApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Choice 全市场看板 (Pandas)")
        self.root.geometry("900x600")
        
        self.engine = MarketDataEngine()
        self._setup_ui()
        
        if not self.engine.is_connected:
            self.status_var.set("❌ Choice 未连接 (请检查 DLL 路径或账号)")
            self.btn_fetch.config(state="disabled")

    def _setup_ui(self):
        # 顶部面板
        frame_top = tk.Frame(self.root, pady=10)
        frame_top.pack(fill=tk.X, padx=10)
        
        self.btn_fetch = tk.Button(frame_top, text="📥 拉取全市场代码", command=self.cmd_fetch_all, bg="#e3f2fd", width=18)
        self.btn_fetch.pack(side=tk.LEFT, padx=5)
        
        self.btn_update = tk.Button(frame_top, text="🔄 刷新行情数据", command=self.cmd_update_data, bg="#e8f5e9", width=18, state="disabled")
        self.btn_update.pack(side=tk.LEFT, padx=5)
        
        self.status_var = tk.StringVar(value="准备就绪")
        tk.Label(frame_top, textvariable=self.status_var, fg="#555").pack(side=tk.LEFT, padx=20)

        # 表格区域
        frame_table = tk.Frame(self.root)
        frame_table.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        cols = ("代码", "名称", "现价", "涨跌幅")
        self.tree = ttk.Treeview(frame_table, columns=cols, show='headings')
        for c in cols:
            self.tree.heading(c, text=c)
            align = "center" if c in ["代码", "名称"] else "e"
            width = 100 if c == "名称" else 80
            self.tree.column(c, width=width, anchor=align)
            
        scroll = ttk.Scrollbar(frame_table, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 底部统计
        self.lbl_stats = tk.Label(self.root, text="Waiting for data...", pady=5)
        self.lbl_stats.pack(side=tk.BOTTOM, anchor="e", padx=10)

        # 配置颜色tag
        self.tree.tag_configure('up', foreground='red')
        self.tree.tag_configure('down', foreground='green')

    def cmd_fetch_all(self):
        def task():
            self.set_status("正在获取A股代码列表...", busy=True)
            codes = self.engine.fetch_all_codes()
            if not codes:
                self.set_status("❌ 代码列表获取失败", busy=False)
                return
            
            self.set_status(f"获取到 {len(codes)} 只股票，正在下载行情...", busy=True)
            df = self.engine.fetch_snapshot()
            self.update_ui(df, "全量拉取完成")
            
        threading.Thread(target=task, daemon=True).start()

    def cmd_update_data(self):
        def task():
            self.set_status("正在刷新行情...", busy=True)
            df = self.engine.fetch_snapshot()
            self.update_ui(df, "刷新成功")
            
        threading.Thread(target=task, daemon=True).start()

    def set_status(self, msg, busy=False):
        self.root.after(0, lambda: self.status_var.set(msg))
        state = "disabled" if busy else "normal"
        # 只有在非busy状态且已有代码时才启用刷新按钮
        update_state = "normal" if (not busy and self.engine.stock_codes) else "disabled"
        self.root.after(0, lambda: self.btn_fetch.config(state=state))
        self.root.after(0, lambda: self.btn_update.config(state=update_state))

    def update_ui(self, df, msg):
        def _update():
            self.btn_fetch.config(state="normal")
            self.btn_update.config(state="normal")
            
            if df.empty:
                self.status_var.set("⚠️ 数据为空")
                return

            # 清空并显示前200条涨幅最高的
            self.tree.delete(*self.tree.get_children())
            df_sorted = df.sort_values(by='涨跌幅', ascending=False)
            
            for code, row in df_sorted.head(200).iterrows():
                tags = ()
                if row['涨跌幅'] > 0: tags = ('up',)
                elif row['涨跌幅'] < 0: tags = ('down',)
                
                vals = (code, row['名称'], f"{row['现价']:.2f}", f"{row['涨跌幅']:.2f}%")
                self.tree.insert("", "end", values=vals, tags=tags)
                
            self.status_var.set(f"✅ {msg} ({datetime.now().strftime('%H:%M:%S')})")
            self.lbl_stats.config(text=f"总股票数: {len(df)} | 展示涨幅Top200")
            
        self.root.after(0, _update)

if __name__ == "__main__":
    root = tk.Tk()
    app = MarketApp(root)
    root.mainloop()