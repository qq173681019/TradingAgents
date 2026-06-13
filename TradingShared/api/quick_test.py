import sys, os
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared')

import ctypes
dll_dir = r'D:\GitHub\TradingAgents\TradingShared\libs\windows'
dll_path = os.path.join(dll_dir, 'EmQuantAPI_x64.dll')
os.add_dll_directory(dll_dir)
ctypes.CDLL(dll_path, winmode=0x00000008)

from EmQuantAPI import c
from config import CHOICE_USERNAME, CHOICE_PASSWORD

print("LOGIN TEST")
r = c.start(f'USERNAME={CHOICE_USERNAME},PASSWORD={CHOICE_PASSWORD}')
print(f"Code={r.ErrorCode}")
print(f"Msg={r.ErrorMsg}")

# Get error description
try:
    err = c.geterrstring(r.ErrorCode, 1)
    print(f"ERRSTR={err}")
except:
    print("Could not get error string")

c.stop()