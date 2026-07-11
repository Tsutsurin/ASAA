@echo off

net use "\\10.201.198.25\tmp" /delete /y >nul 2>&1

net use "\\10.201.198.25\tmp" /user:10.201.198.25\administrator "%ASAA_SHARE_PASSWORD%" /persistent:no

cd /d C:\ASAA

ASAA.exe