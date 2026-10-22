@echo off
chcp 65001 >nul
dir /s /b "D:\nbs可视化" > "D:\nbs可视化\_file_listing.txt" 2>&1
echo DONE >> "D:\nbs可视化\_file_listing.txt"
