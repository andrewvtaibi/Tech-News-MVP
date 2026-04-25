# Industry News — Company Reports and Information Engine

> **Non-Commercial Use Only.**
> This tool is provided free of charge strictly for personal,
> educational, and non-commercial purposes.
> Any commercial use is expressly prohibited and constitutes
> an immediate termination of all rights granted under the
> [license](LICENSE).

Search any single or batch of companies and instantly get recent
headlines, official press releases, and interactive stock
charts — all in one place, completely free.

From the creator: I have CSV files containing lists of companies
I batch search daily or weekly covering industry sectors that
interest me for various reasons (professional, personal finance, 
market research, etc). 

---

## Download and Install

> **No coding or technical setup required.**
> Download one file, double-click it, and the app opens in
> your browser.

### Windows

1. Go to the
   [**Releases page**](../../releases/latest)
   of this repository.
2. Under **Assets**, download **`IndustryNews-Setup-vX.X.X.exe`**.
3. Double-click the downloaded file and follow the installer
   (Next → Next → Install).
4. The app opens in your browser automatically when installation
   finishes. A desktop shortcut is created for future use.

> **"Windows protected your PC" warning?**
> This appears for any app that isn't commercially signed.
> Click **More info** → **Run anyway**. The app is safe.

---
Mac version removed because attempts have shown that it cannot be effectively
used without significant changes and an apple developer license (sorry)

---

## What You Can Do

| Feature | How to use it |
|---|---|
| Search by company name | Type `Pfizer` in the search bar, press Enter |
| Search by ticker symbol | Type `PFE` in the search bar, press Enter |
| Switch timeframe | Click **Past Week** or **Past Month** |
| Switch content type | Click **Headlines**, **Press releases**, or **Stock price** |
| Batch search | Upload a CSV file with one company or ticker per row |

### Headlines
Recent news articles sourced from Google News.
Each result links to the original article.

### Press Releases
Official company statements from PR Newswire, GlobeNewswire,
and BusinessWire only — no third-party editorial content.

### Stock Price
An interactive TradingView chart for the ticker symbol.
Requires an internet connection to load.

### CSV Batch Search
Create a plain `.csv` file with one company name or ticker
per row (no header row needed):

```
MSFT
AMZN
LMT
Pfizer
```

Upload it using the yellow card in the top-right corner of
the app. Results are returned for each entry, collapsible
by company.

**Limits:** 50 rows maximum, 1 MB file size, UTF-8 encoding.

---

## Troubleshooting

| Symptom | What to check |
|---|---|
| Browser says "site cannot be reached" | The launcher window may have been closed — reopen the app |
| No results returned | Check your internet connection; try **Past Month** for less active companies |
| Press releases are empty | Some companies publish infrequently — try **Past Month** |
| Stock chart blank | Try the exact ticker symbol (e.g. `MSFT`, `LMT`) — the chart needs internet |
| Windows SmartScreen warning | Click **More info** → **Run anyway** |
| Mac Gatekeeper warning | Right-click the app → **Open** → **Open** |

### Finding the log file (advanced)

If the app fails to start entirely, a log file records the
exact error.

- **Windows:** open
  `C:\Users\YourName\AppData\Local\Programs\Industry News\logs\launch.log`
  in Notepad
- **Mac:** in Finder press **Cmd+Shift+G**, paste
  `/Applications/IndustryNews.app/Contents/MacOS/logs/`
  and open `launch.log`

---

## Stopping the App

Close the launcher window, or press `Ctrl+C` inside it.
The browser tab stays open but shows "connection refused"
until the app is restarted.

---
---

## For Developers

Everything below this line is for people who want to run the
app from source code, contribute, or build their own
installers.

---

### Running from Source

#### Prerequisites
- Python 3.10 or later
- Git

#### Windows — First-Time Setup

```
git clone https://github.com/andrewvtaibi/Industry-News-MVP.git
cd Industry-News-MVP
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then launch with:

```
"Launch Industry News.bat"
```

#### Mac — First-Time Setup

```bash
git clone https://github.com/YOUR_USERNAME/Industry-News-MVP.git
cd Industry-News-MVP
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x launch_macos.sh
./launch_macos.sh
```

---

### Running the Tests

**Windows:**
```
.venv\Scripts\python.exe -m pytest tests\ -m "not integration" -v
```

**Mac / Linux:**
```
.venv/bin/python3 -m pytest tests/ -m "not integration" -v
```

Expected output: **124 passed** (unit tests, no network required).

To also run live network tests (requires internet):

**Windows:**
```
.venv\Scripts\python.exe -m pytest tests\test_integration.py -v
```

**Mac / Linux:**
```
.venv/bin/python3 -m pytest tests/test_integration.py -v
```

Expected output: **10 passed**.

---

### Automated Builds via GitHub Actions

Pushing a version tag triggers the build pipeline automatically.
GitHub's cloud machines build both installers — no Mac hardware
needed.

```bash
git tag v1.0.1
git push origin v1.0.1
```

GitHub then:
1. Builds `IndustryNews-Setup-v1.0.1.exe` on a Windows runner
2. Builds `IndustryNews-v1.0.1.dmg` on a macOS runner
3. Attaches both files to a new GitHub Release

Users download directly from the **Releases** page — no
terminal or technical knowledge required.

---

### Building Installers Locally

#### Windows installer (requires Inno Setup 6)

```
pip install pyinstaller
pyinstaller industry_news.spec
iscc installer\industry_news.iss
```

Output: `installer\Output\IndustryNews-Setup.exe`

#### macOS DMG (requires a Mac)

```bash
pip install pyinstaller
pyinstaller industry_news_mac.spec
brew install create-dmg
create-dmg \
  --volname "Industry News" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "IndustryNews.app" 175 190 \
  --hide-extension "IndustryNews.app" \
  --app-drop-link 425 185 \
  "IndustryNews.dmg" \
  "dist/IndustryNews.app"
```

Output: `IndustryNews.dmg`

---

### Project Structure

```
Industry-News-MVP/
  Launch Industry News.bat  <- Windows launcher (source run)
  launch_macos.sh           <- Mac launcher (source run)
  launch.py                 <- cross-platform launcher logic
  industry_news.spec        <- PyInstaller spec (Windows)
  industry_news_mac.spec    <- PyInstaller spec (macOS)
  installer/
    industry_news.iss       <- Inno Setup script (Windows .exe)
    Output/                 <- built Windows installer
  .github/
    workflows/
      build-release.yml     <- automated build + release pipeline
  server/                   <- FastAPI backend
  static/                   <- HTML / CSS / JS frontend
  data/tickers.json         <- ticker symbol lookup table
  tests/                    <- automated test suite
  logs/launch.log           <- startup log (check here on errors)
  app/                      <- RSS fetch utilities
```

---

### Security Notes

- All user input is sanitized before use (XSS and injection
  protected).
- Rate limiting: 30 searches per minute per IP address.
- CSV uploads: validated for size, row count, and encoding.
- No user data is stored or transmitted beyond fetching public
  RSS feeds.
- Error messages never expose internal server details.

---

## License

This project is licensed under the
[PolyForm Noncommercial License 1.0.0](LICENSE).

Free for personal, educational, and non-commercial use.
**Commercial use of any kind is prohibited.**
