import mplfinance as mpf
import pandas as pd
import numpy as np
import tkinter as tk
from tkinter import simpledialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from datetime import datetime, timedelta


def update_success(self, df, source, code):
        try:
            if df.empty or not self.root.winfo_exists(): return
            
            latest = df.iloc[-1]
            price = latest['Close']
            curr_time = latest.name.strftime('%H:%M')
            
            self.safe_config(self.lbl_status, text=f"✅ {source} | {code} | {price:.2f} | {curr_time}", fg="#006400")
            # 初始化交互状态（仅第一次）
            if not getattr(self, '_kline_initialized', False):
                self.kline_options = [30, 60, 120, 'D']
                # 默认显示 index=1 -> 60 根
                self.kline_idx = 1
                self._last_df = None
                self._kline_initialized = True

                # 绑定滚轮：上滚放大（显示更少根），下滚缩小（更多根）
                def _on_scroll(event):
                    try:
                        if self._last_df is None:
                            return
                        if hasattr(event, 'button') and event.button == 'up':
                            # zoom in
                            if self.kline_idx > 0:
                                self.kline_idx -= 1
                        else:
                            # zoom out (button=='down' or other)
                            if self.kline_idx < len(self.kline_options) - 1:
                                self.kline_idx += 1
                        # 重新绘制最近一次的数据
                        self._redraw_kline()
                    except Exception as _e:
                        print('Scroll handler error', _e)

                # 右键点击切换到下一个模式（30->60->120->日线）
                def _on_click(event):
                    try:
                        # 在画布区域右键（button==3）切换
                        if hasattr(event, 'button') and event.button == 3:
                            self.kline_idx = (self.kline_idx + 1) % len(self.kline_options)
                            self._redraw_kline()
                    except Exception as _e:
                        print('Click handler error', _e)

                # 绘制函数（复用在滚轮/点击里）
                def _redraw():
                    try:
                        if self._last_df is None: return
                        opt = self.kline_options[self.kline_idx]
                        # 日线需要重采样到日级别
                        if opt == 'D':
                            try:
                                res = self._last_df.resample('D').agg({
                                    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
                                }).dropna()
                                plot_df_local = res.tail(60)
                            except Exception:
                                plot_df_local = self._last_df.tail(60)
                        else:
                            plot_df_local = self._last_df.tail(int(opt))

                        self.ax1.clear(); self.ax2.clear()
                        title_mode = f"Mode: {opt}" if opt != 'D' else "Mode: 日线"
                        self.ax1.set_title(f"Code: {code} Source: {source} | {title_mode}", fontsize=10)

                        mc = mpf.make_marketcolors(up='red', down='green', inherit=True)
                        s = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='yahoo')

                        mpf.plot(
                            plot_df_local,
                            type='candle',
                            ax=self.ax1,
                            volume=self.ax2,
                            style=s,
                            ylabel='',
                            ylabel_lower='',
                        )
                        self.canvas.draw()
                    except Exception as e:
                        print('Redraw error', e)

                # 将内部函数挂到实例，方便其他地方调用/测试
                self._on_scroll = _on_scroll
                self._on_click = _on_click
                self._redraw_kline = _redraw

                try:
                    # canvas 可能是 FigureCanvasTkAgg
                    self.canvas.mpl_connect('scroll_event', self._on_scroll)
                    self.canvas.mpl_connect('button_press_event', self._on_click)
                except Exception:
                    # 兼容性：有些 canvas 实现可能不支持 mpl_connect
                    pass

            # 缓存当前 df 以便交互使用（保留引用以节省内存）
            self._last_df = df

            # 调用绘制（第一次或每次更新都走这里）
            # 根据当前选项决定要显示多少根K线
            opt_now = self.kline_options[self.kline_idx] if getattr(self, 'kline_options', None) else 60
            if opt_now == 'D':
                try:
                    resdf = df.resample('D').agg({
                        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
                    }).dropna()
                    plot_df = resdf.tail(60)
                except Exception:
                    plot_df = df.tail(60)
            else:
                plot_df = df.tail(int(opt_now))
            
            mc = mpf.make_marketcolors(up='red', down='green', inherit=True)
            s = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='yahoo') 
            
            mpf.plot(
                plot_df,  # 这里传入截取后的数据
                type='candle', 
                ax=self.ax1, 
                volume=self.ax2, 
                style=s,
                ylabel='',
                ylabel_lower='',
            )
            self.canvas.draw()
            
        except Exception as e:
            print(f"Plot Error Detail: {e}")
            self.safe_config(self.lbl_status, text=f"绘图错误: {e}", fg="red")


def _make_demo_df(periods=200, freq='T'):
    # 生成演示用的价格数据（分钟级）
    end = datetime.now()
    idx = pd.date_range(end=end, periods=periods, freq=freq)
    # 简单随机漫步
    price = np.cumsum(np.random.randn(periods)) + 100
    openp = price + np.random.randn(periods) * 0.2
    high = np.maximum(openp, price) + np.abs(np.random.randn(periods) * 0.5)
    low = np.minimum(openp, price) - np.abs(np.random.randn(periods) * 0.5)
    close = price
    vol = (np.abs(np.random.randn(periods)) * 1000).astype(int)
    df = pd.DataFrame({'Open': openp, 'High': high, 'Low': low, 'Close': close, 'Volume': vol}, index=idx)
    return df


if __name__ == '__main__':
    # 最小化演示：创建 tkinter 窗口与 matplotlib 画布，调用 update_success 进行绘图
    root = tk.Tk()
    root.wm_title('StockMonitor Demo')

    # 状态标签
    lbl = tk.Label(root, text='状态')
    lbl.pack(side='top', fill='x')

    fig = Figure(figsize=(8, 6))
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1])
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)

    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().pack(fill='both', expand=1)

    class Dummy:
        pass

    inst = Dummy()
    inst.root = root
    inst.lbl_status = lbl
    inst.ax1 = ax1
    inst.ax2 = ax2
    inst.canvas = canvas
    def safe_config(lbl, **kwargs):
        try:
            lbl.config(**kwargs)
            lbl.update_idletasks()
        except Exception:
            pass
    inst.safe_config = safe_config

    demo_df = _make_demo_df(200, 'T')

    # 要求用户输入股票代码，默认 000001，用户需手动确认
    try:
        user_code = simpledialog.askstring('输入股票代码', '请输入股票代码（默认 000001）：', initialvalue='000001', parent=root)
        if not user_code:
            user_code = '000001'
    except Exception:
        user_code = '000001'

    # 首次绘制（使用用户确认的代码）
    try:
        update_success(inst, demo_df, 'DEMO', user_code)
    except Exception as e:
        print('Demo plot failed:', e)

    root.mainloop()