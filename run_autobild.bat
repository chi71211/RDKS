@echo off
chcp 65001 >nul 2>&1
title AutoBild Scraper v11.0

echo ==========================================
echo   AutoBild Scraper v11.0 - Windows
echo ==========================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [Error] Python not found!
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Check required packages
echo Checking required packages...
pip show playwright >nul 2>&1
if errorlevel 1 (
    echo Installing playwright...
    pip install playwright
    playwright install chromium
)

pip show nest_asyncio >nul 2>&1
if errorlevel 1 (
    echo Installing nest_asyncio...
    pip install nest_asyncio
)

pip show pandas >nul 2>&1
if errorlevel 1 (
    echo Installing pandas...
    pip install pandas
)

echo.
echo All packages ready!
echo.

REM Menu
echo Please select operation:
echo [1] Full scrape (all brands)
echo [2] Test mode (2 brands x 2 models)
echo [3] Scrape specific brand
echo [4] Show database statistics
echo [5] Reset database
echo [6] Exit
echo.
set /p choice="Enter choice (1-6): "

if "%choice%"=="1" (
    echo.
    echo Starting full scrape...
    python autobild_win.py
)
if "%choice%"=="2" (
    echo.
    echo Starting test mode...
    python autobild_win.py --test
)
if "%choice%"=="3" (
    set /p brand="Enter brand name (e.g., VW, BMW, Mercedes): "
    echo.
    echo Starting scrape for %brand%...
    python autobild_win.py --brand %brand%
)
if "%choice%"=="4" (
    echo.
    python autobild_win.py --status
)
if "%choice%"=="5" (
    echo.
    set /p confirm="Are you sure you want to reset database? (Y/N): "
    if /i "%confirm%"=="Y" (
        python autobild_win.py --reset
    ) else (
        echo Cancelled.
    )
)
if "%choice%"=="6" (
    exit /b 0
)

echo.
echo Operation completed!
pause
