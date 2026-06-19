@echo off
:: ============================================================
:: install_odbc17_RUNAS_ADMIN.bat
:: RIGHT-CLICK THIS FILE -> "Run as administrator"
:: Installs ODBC Driver 17 for SQL Server silently.
:: ============================================================

echo.
echo  Installing ODBC Driver 17 for SQL Server...
echo.

set MSI=%TEMP%\msodbcsql17.msi

:: Re-download if not present (in case TEMP was cleared)
if not exist "%MSI%" (
    echo  Downloading MSI...
    powershell -Command "Invoke-WebRequest -Uri 'https://download.microsoft.com/download/6/f/f/6ffefc73-39ab-4cc0-bb7c-4093d64c2669/en-US/17.10.6.1/x64/msodbcsql.msi' -OutFile '%MSI%' -UseBasicParsing"
)

echo  Running installer...
msiexec /i "%MSI%" /quiet /norestart IACCEPTMSODBCSQLLICENSETERMS=YES

if %ERRORLEVEL% EQU 0 (
    echo.
    echo  SUCCESS! ODBC Driver 17 installed.
    echo  Now run the migration from VS Code:
    echo.
    echo    .venv\Scripts\python CODE\migrate_to_sqlserver.py --table all
    echo.
) else (
    echo.
    echo  ERROR: msiexec returned code %ERRORLEVEL%
    echo  Try running the MSI manually: %MSI%
)

pause
