@echo off
cd /d "C:\Users\Andrew Taibi\OneDrive\Desktop\App Development\Bio-news-mvp"
set "PYTHONPATH=C:\Users\Andrew Taibi\OneDrive\Desktop\App Development\Bio-news-mvp"
set "BIONEWS_OUTPUTS=csv,json,html"
set "BIONEWS_WINDOW_DAYS=7"
set "BIONEWS_ONLY_NEW=1"
"C:\Users\Andrew Taibi\OneDrive\Desktop\App Development\Bio-news-mvp\.venv\Scripts\python.exe" "C:\Users\Andrew Taibi\OneDrive\Desktop\App Development\Bio-news-mvp\main.py"