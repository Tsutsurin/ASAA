@echo off
setlocal

net use "\\10.201.198.25\tmp" /delete /y >nul 2>&1
net use "\\10.201.198.25\tmp" /user:10.201.198.25\administrator "%ASAA_SHARE_PASSWORD%" /persistent:no >nul 2>&1

if errorlevel 1 (
    exit /b 1
)

cd /d C:\ASAA

ASAA.exe --rescan

set "EXIT_CODE=%ERRORLEVEL%"

exit /b %EXIT_CODE%