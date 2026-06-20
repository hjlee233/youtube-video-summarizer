@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TubeNote Local
echo ============================================================
echo   TubeNote Local 서버를 시작합니다
echo   잠시 후 브라우저가 자동으로 열립니다  (http://localhost:8800)
echo   종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo ============================================================
echo.

REM 8501 포트는 Windows(Hyper-V/WSL) 예약 범위라 8800 사용
uv run streamlit run app.py --server.port 8800

echo.
echo 서버가 종료되었습니다. 창을 닫으려면 아무 키나 누르세요.
pause >nul
