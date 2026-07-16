@echo off
rem ============================================================
rem  IGLINE-PySim - Windows baslatici
rem
rem  Cift tiklayin: ilk calistirmada .venv kurulur, bagimliliklar
rem  yuklenir, web arayuzu baslar ve tarayici acilir.
rem
rem  Kullanim:
rem    run.bat                 -> web arayuzu (http://127.0.0.1:8000)
rem    run.bat 8080            -> farkli port
rem    run.bat sim [gun] [tohum] [replikasyon] -> headless kosu
rem    run.bat validate        -> Arena A.4 dogrulamasi
rem    run.bat test            -> test takimi
rem ============================================================
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title IGLINE-PySim

rem ---- Python bul (py launcher tercih) ----
set "PY="
py -3 -c "exit()" >nul 2>nul && set "PY=py -3"
if not defined PY (
    python -c "exit()" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [HATA] Python bulunamadi. https://www.python.org/downloads/ adresinden
    echo        Python 3.11+ kurun ve kurulumda "Add python.exe to PATH" isaretleyin.
    pause & exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" || (
    echo [HATA] Python 3.11 veya ustu gerekli. Mevcut surum:
    %PY% --version
    pause & exit /b 1
)

rem ---- Sanal ortam ----
if not exist ".venv\Scripts\python.exe" (
    echo [kurulum] Sanal ortam olusturuluyor ^(.venv^)...
    %PY% -m venv .venv || (echo [HATA] venv olusturulamadi & pause & exit /b 1)
)
set "VPY=.venv\Scripts\python.exe"

rem ---- Bagimliliklar (ilk calistirmada; guncellemek icin .venv\.deps_ok silin) ----
if exist ".venv\.deps_ok" goto :deps_done
:install
echo [kurulum] Bagimliliklar yukleniyor ^(ilk seferde birkac dakika surebilir^)...
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -e . --quiet || (
    echo [HATA] Bagimlilik kurulumu basarisiz. Internet baglantisini kontrol edin.
    pause & exit /b 1
)
echo ok > ".venv\.deps_ok"
:deps_done

rem ---- Komutlar ----
if /i "%~1"=="sim"      goto :sim
if /i "%~1"=="validate" goto :validate
if /i "%~1"=="test"     goto :test

rem ---- Varsayilan: web arayuzu ----
set "PORT=%~1"
if not defined PORT set "PORT=8000"
echo.
echo  IGLINE-PySim web arayuzu baslatiliyor: http://127.0.0.1:%PORT%
echo  Kapatmak icin bu pencerede Ctrl+C ya da pencereyi kapatin.
echo.
start "" cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:%PORT%"
"%VPY%" -m igline serve --host 127.0.0.1 --port %PORT%
goto :end

:sim
set "DAYS=%~2" & set "SEED=%~3" & set "REPS=%~4"
if not defined DAYS set "DAYS=10"
if not defined SEED set "SEED=42"
if not defined REPS set "REPS=1"
echo [kosu] %DAYS% gun, tohum %SEED%, %REPS% replikasyon...
"%VPY%" -m igline run --days %DAYS% --seed %SEED% --replications %REPS%
echo.
echo Ciktilar "runs\" klasorune yazildi.
pause
goto :end

:validate
echo [dogrulama] 5 replikasyon x 10 gun, Arena A.4 karsilastirmasi...
"%VPY%" -m igline validate --replications 5 --seed 42
echo.
echo Rapor: validation_report.md
pause
goto :end

:test
"%VPY%" -m pip install pytest --quiet
"%VPY%" -m pytest tests -q
pause
goto :end

:end
endlocal
