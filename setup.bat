@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 사용: setup.bat [telegram^|bot^|gemini]   (기본: telegram)
set "STEP=%~1"
if "%STEP%"=="" set "STEP=telegram"
set "CMD=scripts\tg_sync.py setup"
set "TITLE=텔레그램 연결 설정"
if /i "%STEP%"=="bot" set "CMD=scripts\tg_sync.py bot-setup"
if /i "%STEP%"=="bot" set "TITLE=휴대폰 질문용 봇 연결"
if /i "%STEP%"=="gemini" set "CMD=scripts\transcribe.py setup"
if /i "%STEP%"=="gemini" set "TITLE=회의록 전사(Gemini) 설정"
title %TITLE%

if exist ".venv\Scripts\python.exe" goto :haveenv

call :findpy
if defined PYEXE goto :mkenv
echo 파이썬이 없어서 설치할게요. 2~3분 걸려요...
where winget >nul 2>nul
if errorlevel 1 goto :nopython
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :findpy
if not defined PYEXE goto :nopython

:mkenv
echo 처음 한 번만 필요한 준비를 하고 있어요. 1~2분 걸려요...
"%PYEXE%" -m venv .venv
if errorlevel 1 goto :nopython

:haveenv
".venv\Scripts\python.exe" -c "import telethon, google.genai, docx, imageio_ffmpeg" 2>nul
if not errorlevel 1 goto :run
echo 필요한 프로그램을 설치하고 있어요. 처음엔 몇 분 걸릴 수 있어요...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :pipfail

:run
".venv\Scripts\python.exe" %CMD%
echo.
pause
exit /b

:findpy
set "PYEXE="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe") do if not defined PYEXE if exist %%P set "PYEXE=%%~P"
if defined PYEXE exit /b 0
for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
if defined PYEXE exit /b 0
for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
exit /b 0

:nopython
echo.
echo [문제] 파이썬을 찾거나 설치하지 못했어요.
echo 회사 컴퓨터 보안 설정 때문일 수 있어요.
echo Claude 에게 "파이썬을 못 찾는대" 라고 알려 주세요.
pause
exit /b 1

:pipfail
echo.
echo [문제] 프로그램 설치에 실패했어요. 인터넷 연결을 확인한 뒤
echo Claude 에게 "설치에 실패했대" 라고 알려 주세요.
pause
exit /b 1
