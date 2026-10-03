@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_tag_visual_review.ps1"
if errorlevel 1 pause
