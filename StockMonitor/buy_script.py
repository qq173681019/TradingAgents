import tkinter as tk
from tkinter import messagebox
import sys

def main():
    # 隐藏主窗口，只显示弹窗
    root = tk.Tk()
    root.withdraw()
    
    # 获取传递的股票代码（如果有）
    code = sys.argv[1] if len(sys.argv) > 1 else "Unknown"
    
    # 弹出警告框
    messagebox.showwarning("买入信号触发", f"监测到 {code} 出现买点！\n\nMACD金叉，建议执行买入操作。")
    
    root.destroy()

if __name__ == "__main__":
    main()