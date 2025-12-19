"""Choice API包装器 - 通过独立进程避免调试器环境污染"""
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta


class ChoiceAPIWrapper:
    """Choice API包装器，使用独立Python进程避免环境污染"""
    
    def __init__(self, python_exe=r"C:\veighna_studio\python.exe", timeout=30, use_batch=True, use_powershell=True):
        """
        初始化
        
        参数:
            python_exe: Python解释器路径，默认使用veighna_studio的Python
            timeout: 超时时间（秒）
            use_batch: 是否使用批处理文件作为中介（更彻底的隔离）
            use_powershell: 是否使用PowerShell Start-Process（最彻底隔离）
        """
        self.python_exe = python_exe
        self.timeout = timeout
        self.use_batch = use_batch
        self.use_powershell = use_powershell
        self.worker_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "choice_worker.py"
        )
        
        # 验证worker脚本存在
        if not os.path.exists(self.worker_script):
            raise FileNotFoundError(f"Choice worker脚本不存在: {self.worker_script}")
    
    def _call_worker(self, *args):
        """
        调用worker进程
        
        参数:
            *args: 传递给worker的命令行参数
        
        返回:
            dict: JSON解析后的结果
        """
        try:
            # 准备干净的环境 - 移除所有可能影响Choice SDK的环境变量
            env = os.environ.copy()
            
            # 清理Python相关环境变量
            for key in ['PYTHONPATH', 'PYTHONSTARTUP', 'PYTHONHOME', 
                        'VIRTUAL_ENV', 'CONDA_DEFAULT_ENV', 'CONDA_PREFIX']:
                if key in env:
                    del env[key]
            
            # 清理调试器相关环境变量
            debug_vars = [k for k in env.keys() if 'DEBUG' in k.upper() or 'PYDEV' in k.upper()]
            for key in debug_vars:
                del env[key]
            
            # 执行命令 - 根据配置选择启动方式
            import sys
            
            if self.use_powershell and sys.platform == 'win32':
                # 方案A: 使用PowerShell Start-Process（最彻底隔离）
                result = self._call_via_powershell(args, env)
            elif self.use_batch and sys.platform == 'win32':
                # 方案B: 使用临时批处理文件启动
                result = self._call_via_batch(args, env)
            else:
                # 方案B: 直接subprocess（使用DETACHED_PROCESS）
                cmd = [self.python_exe, self.worker_script] + list(args)
                
                if sys.platform == 'win32':
                    # DETACHED_PROCESS (0x00000008) + CREATE_NEW_PROCESS_GROUP (0x00000200)
                    creation_flags = 0x00000008 | 0x00000200
                else:
                    creation_flags = 0
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=self.timeout,
                    cwd=os.path.dirname(self.worker_script),
                    env=env,
                    creationflags=creation_flags,
                    shell=False
                )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Worker进程退出异常: {result.returncode}",
                    "stderr": result.stderr
                }
            
            # 解析JSON输出 - 提取标记之间的内容
            try:
                stdout = result.stdout
                # 查找JSON标记
                start_marker = "===CHOICE_JSON_START==="
                end_marker = "===CHOICE_JSON_END==="
                
                if start_marker in stdout and end_marker in stdout:
                    # 提取标记之间的JSON
                    start_idx = stdout.find(start_marker) + len(start_marker)
                    end_idx = stdout.find(end_marker)
                    json_str = stdout[start_idx:end_idx].strip()
                    return json.loads(json_str)
                else:
                    # 兼容旧格式：直接解析整个输出
                    return json.loads(stdout)
                    
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"JSON解析失败: {e}",
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Worker进程超时 ({self.timeout}秒)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Worker调用异常: {type(e).__name__}: {e}"
            }
    
    def _call_via_powershell(self, args, env):
        """
        通过PowerShell Start-Process启动worker（最彻底的隔离）
        
        PowerShell的Start-Process -Wait创建完全独立的进程，不继承父进程内部状态
        """
        # 创建临时输出文件
        output_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        output_path = output_file.name
        output_file.close()
        
        # 构造PowerShell的ArgumentList
        # 每个参数用单引号包裹，用逗号分隔
        ps_args = [self.worker_script] + list(args)
        args_list = ','.join([f"'{arg}'" for arg in ps_args])
        
        # 构造PowerShell命令
        # 使用正确的语法传递参数数组
        ps_command = f'''
$env:PYTHONPATH = $null
$env:PYTHONSTARTUP = $null
$env:VSCODE_PID = $null
$env:DEBUGPY_LAUNCHER_PORT = $null
Start-Process -FilePath '{self.python_exe}' -ArgumentList {args_list} -NoNewWindow -Wait -RedirectStandardOutput '{output_path}' -RedirectStandardError '{output_path}.err'
'''
        
        try:
            # 执行PowerShell命令
            import time
            ps_result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_command],
                capture_output=True,
                timeout=self.timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            # 等待文件写入完成
            time.sleep(0.5)
            
            # 读取输出
            stdout = ""
            try:
                with open(output_path, 'r', encoding='utf-8', errors='replace') as f:
                    stdout = f.read()
            except:
                pass
            
            # 读取错误输出
            stderr = ""
            try:
                with open(output_path + '.err', 'r', encoding='utf-8', errors='replace') as f:
                    stderr = f.read()
            except:
                pass
            
            # 构造返回对象
            class FakeResult:
                def __init__(self, stdout, stderr):
                    self.returncode = 0
                    self.stdout = stdout
                    self.stderr = stderr
            
            return FakeResult(stdout, stderr)
            
        finally:
            # 清理临时文件
            try:
                os.unlink(output_path)
            except:
                pass
            try:
                os.unlink(output_path + '.err')
            except:
                pass
    
    def _call_via_batch(self, args, env):
        """
        通过临时批处理文件启动worker（最彻底的隔离方案）
        
        使用 cmd /c start 创建完全独立的进程树，不继承任何父进程状态
        """
        # 创建临时输出文件
        output_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        output_path = output_file.name
        output_file.close()
        
        # 创建临时完成标记文件
        done_file = tempfile.NamedTemporaryFile(mode='w', suffix='.done', delete=False, encoding='utf-8')
        done_path = done_file.name
        done_file.close()
        
        # 创建临时批处理文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='gbk') as f:
            batch_file = f.name
            
            # 写入批处理命令
            f.write('@echo off\n')
            f.write('chcp 65001 >nul\n')  # UTF-8编码
            
            # 清理所有可能的污染环境变量
            cleanup_vars = [
                'PYTHONPATH', 'PYTHONSTARTUP', 'PYTHONHOME', 
                'VIRTUAL_ENV', 'CONDA_DEFAULT_ENV', 'CONDA_PREFIX',
                'PYTHONUNBUFFERED', 'PYTHONIOENCODING',
                # 清理VS Code和调试器变量
                'VSCODE_PID', 'VSCODE_IPC_HOOK', 'VSCODE_NLS_CONFIG',
                'DEBUGPY_LAUNCHER_PORT', 'DEBUGPY_PROCESS_ID'
            ]
            for key in cleanup_vars:
                f.write(f'set {key}=\n')
            
            # 执行Python命令，输出到文件
            cmd_args = ' '.join([f'"{arg}"' if ' ' in str(arg) else str(arg) for arg in args])
            f.write(f'"{self.python_exe}" "{self.worker_script}" {cmd_args} > "{output_path}" 2>&1\n')
            
            # 创建完成标记
            f.write(f'echo done > "{done_path}"\n')
        
        try:
            # 使用 os.system() 同步执行 - 创建真正独立的进程
            # os.system() 不会传递Python的内部状态
            import time

            # 同步执行批处理文件
            return_code = os.system(f'"{batch_file}"')
            
            # 等待文件写入完成
            time.sleep(0.5)
            
            # 从文件读取输出
            
            try:
                with open(output_path, 'r', encoding='utf-8', errors='replace') as f:
                    stdout = f.read()
            except:
                stdout = ""
            
            # 构造subprocess.CompletedProcess对象兼容返回
            class FakeResult:
                def __init__(self, stdout):
                    self.returncode = 0
                    self.stdout = stdout
                    self.stderr = ""
            
            return FakeResult(stdout)
            
        finally:
            # 清理临时文件
            try:
                os.unlink(batch_file)
            except:
                pass
            try:
                os.unlink(output_path)
            except:
                pass
    
    def get_kline_data(self, stock_code, start_date=None, end_date=None,
                       indicators="OPEN,HIGH,LOW,CLOSE,VOLUME", days=30):
        """
        获取K线数据
        
        参数:
            stock_code: 股票代码，如 "000001.SZ"
            start_date: 开始日期 "YYYY-MM-DD"，默认为end_date往前days天
            end_date: 结束日期 "YYYY-MM-DD"，默认为今天
            indicators: 指标列表，逗号分隔
            days: 当start_date为None时，默认获取多少天的数据
        
        返回:
            dict: {
                "success": bool,
                "stock_code": str,
                "dates": list,
                "data": dict,  # {indicator: [values]}
                "error": str  # 失败时
            }
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        return self._call_worker("kline", stock_code, start_date, end_date, indicators)
    
    def get_realtime_quote(self, stock_codes):
        """
        获取实时行情
        
        参数:
            stock_codes: 股票代码，可以是字符串或列表
                        单个: "000001.SZ"
                        多个: ["000001.SZ", "600036.SH"] 或 "000001.SZ,600036.SH"
        
        返回:
            dict: {
                "success": bool,
                "codes": list,
                "data": dict,  # {indicator: [values]}
                "error": str  # 失败时
            }
        """
        if isinstance(stock_codes, list):
            codes_str = ",".join(stock_codes)
        else:
            codes_str = stock_codes
        
        return self._call_worker("quote", codes_str)
    
    def test_connection(self):
        """
        测试Choice连接
        
        返回:
            bool: 连接是否成功
        """
        result = self.get_kline_data("000001.SZ", days=5)
        return result.get("success", False)


# 使用示例
if __name__ == "__main__":
    print("=== 测试Choice API包装器 ===\n")
    
    choice = ChoiceAPIWrapper()
    
    # 测试连接
    print("[1] 测试连接...")
    if choice.test_connection():
        print("    ✅ 连接成功\n")
    else:
        print("    ❌ 连接失败\n")
        exit(1)
    
    # 测试获取K线数据
    print("[2] 获取 000001.SZ K线数据...")
    result = choice.get_kline_data("000001.SZ", days=5)
    
    if result["success"]:
        print(f"    ✅ 成功获取 {len(result['dates'])} 条数据")
        print(f"    日期: {result['dates'][:3]}...")
        if 'CLOSE' in result['data']:
            closes = result['data']['CLOSE']
            print(f"    收盘价: {closes[:3]}...")
    else:
        print(f"    ❌ 失败: {result['error']}")
    
    # 测试获取实时行情
    print("\n[3] 获取实时行情...")
    result = choice.get_realtime_quote(["000001.SZ", "600036.SH"])
    
    if result["success"]:
        print(f"    ✅ 成功获取 {len(result['codes'])} 只股票")
        print(f"    代码: {result['codes']}")
        if 'LASTPRICE' in result['data']:
            prices = result['data']['LASTPRICE']
            print(f"    最新价: {prices}")
    else:
        print(f"    ❌ 失败: {result['error']}")
    
    print("\n✅ 测试完成")
