@echo off
REM Windows launcher for Manual Intelligence Engine

echo ================================================
echo Manual Intelligence Engine
echo ================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from https://www.python.org/
    pause
    exit /b 1
)

REM Check if requirements are installed
python -m pip check >nul 2>&1
if errorlevel 1 (
    echo Installing/updating dependencies...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

REM Check for API key
if "%OPENAI_API_KEY%"=="" (
    echo.
    echo WARNING: OPENAI_API_KEY environment variable not set!
    echo.
    echo Please set your OpenAI API key:
    echo   set OPENAI_API_KEY=your-api-key-here
    echo.
    echo Or add it to your system environment variables.
    echo.
    pause
)

REM Run the application
echo Starting Manual Intelligence Engine...
echo.
python run.py

if errorlevel 1 (
    echo.
    echo ERROR: Application failed to start
    pause
    exit /b 1
)
