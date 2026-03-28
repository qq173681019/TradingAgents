Set WshShell = CreateObject("WScript.Shell")
Set oShellLink = WshShell.CreateShortcut(WshShell.SpecialFolders("Desktop") & "\生成推荐_修复版.lnk")
oShellLink.TargetPath = "C:\Users\admin\Documents\GitHub\TradingAgents\TradingAgent\生成推荐_修复版.bat"
oShellLink.WorkingDirectory = "C:\Users\admin\Documents\GitHub\TradingAgents\TradingAgent"
oShellLink.Description = "生成推荐（修复版）"
oShellLink.Save
WScript.Echo "桌面快捷方式创建成功！"
