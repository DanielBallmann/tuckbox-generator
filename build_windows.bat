@echo off
setlocal
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name TuckboxGenerator app.py
if errorlevel 1 exit /b %errorlevel%
if not exist portable mkdir portable
copy /Y dist\TuckboxGenerator.exe portable\TuckboxGenerator.exe >nul
copy /Y README.md portable\README.md >nul
echo Portable executable created at portable\TuckboxGenerator.exe
