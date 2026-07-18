# Env Auto Setup — by rgh

A cross-platform desktop GUI tool built with Python + PySide6 that automates the download, extraction and environment-variable configuration of common developer toolchains. Save yourself from tedious manual installation.

> Project: **env-auto-setup**
> Author: **rgh**
> Platforms: Windows 10/11, macOS 12+, Ubuntu 20.04+
> License: MIT License

---

## 1. Features

- 🖥️ **Cross-platform.** Detects Windows / macOS / Linux (and x64 / arm64) at runtime and picks the correct distribution.
- 📦 **One-click provisioning.** Preloaded with multiple versions of six popular toolchains — the whole pipeline (download → unpack → configure) is automated:
    - JDK (Adoptium Temurin — 21 / 17 / 11 / 8)
    - Apache Maven (3.9.6 / 3.9.5 / 3.8.8 / 3.6.3)
    - Apache Tomcat (10.1 / 9.0 / 8.5)
    - MySQL Server (8.0.37 / 8.0.36 / 5.7.44)
    - Python (3.12 / 3.11 / 3.10 / 3.9)
    - Node.js (20 / 18 / 16)
- 🔍 **Smart detection.** Checks whether `JAVA_HOME` and friends already exist and are valid; missing/invalid entries are flagged for reconfiguration.
- 🛠️ **Environment-variable management.**
    - Windows: writes to `HKCU\Environment` via `winreg` and refreshes with `setx`.
    - macOS / Linux: appends idempotent `export` blocks (with begin/end markers) to `.zshrc` / `.bash_profile` / `.bashrc` / `.profile`.
- 📊 **Live feedback.** Progress bar with real-time byte counts, cancel support, colour-coded log output (info / ok / warn / error).
- 🎨 **Modern UI.** Frameless custom title bar, rounded cards with drop shadows, gradient progress bars, hover/press animations.
- 🧠 **Preferences memory.** Remembers the last selected version per component.

---

## 2. Screenshot (ASCII sketch)

```
┌───────────────────────────────────────────────────────────────┐
│  Env Auto Setup By rgh                          ★ GitHub — ▢ × │
├───────────────────────────────────────────────────────────────┤
│  ┌─ JDK (Temurin) ────────────────────────────────────────┐   │
│  │  Configured: JAVA_HOME=/Users/x/.env-tools/jdk/jdk-17  │   │
│  │  Version [17 ▾]   [Install]  [Configure Only]  [Cancel]│   │
│  │  ████████████████░░░░░  85%                            │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                │
│  Log:                                                          │
│  [JDK] Downloading https://api.adoptium.net/v3/binary/...      │
│  [JDK] Extracted to /Users/x/.env-tools/jdk/jdk-17             │
│  [JDK] JAVA_HOME set                                           │
└───────────────────────────────────────────────────────────────┘
```

---

## 3. Installation & Run

### Requirements

- Python **3.9+**
- A virtual environment is recommended (venv / conda).

### Clone and install

```bash
git clone https://github.com/yourname/env-auto-setup.git
cd env-auto-setup

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Launch

```bash
python main.py
```

The working directory `~/.env-tools/` is created automatically on first launch and stores downloaded archives and extracted components.

---

## 4. Usage

1. Pick the card for the component you want.
2. Choose a version from the drop-down.
3. Click **"Install"**:
    - the archive is streamed and the progress bar updates continuously;
    - it is extracted to `~/.env-tools/<component>/<component>-<version>/`;
    - the corresponding `XXX_HOME` variable is written and the `bin` directory is appended to `PATH`.
4. Already downloaded but not configured? Click **"Configure Only"**.
5. All actions are echoed to the log panel.

### Applying variables

- **Windows:** any new console window will see the fresh user variables. Restart already-open windows.
- **macOS / Linux:**
    ```bash
    source ~/.zshrc     # or ~/.bashrc / ~/.bash_profile / ~/.profile
    ```
    or simply reopen a terminal.

### Verifying

```bash
java -version
mvn -v
python --version
node -v
mysql --version
```

---

## 5. Configuration

### Add / change component versions

Edit `build_components()` inside `main.py`. Each component owns a list of `ComponentVersion` entries. Example — adding JDK 22:

```python
for v in ("22", "21", "17", "11", "8"):
    jdk_versions.append(ComponentVersion(
        version=v,
        url_map=_adoptium_jdk_url(v),
        archive_map={"Windows": "zip", "Darwin": "tar.gz", "Linux": "tar.gz"},
    ))
```

### Switch to a faster mirror

If the official downloads are slow, replace the URL prefix with a regional mirror:

- Huawei Cloud: `https://repo.huaweicloud.com/`
- Tsinghua TUNA: `https://mirrors.tuna.tsinghua.edu.cn/`
- Alibaba: `https://mirrors.aliyun.com/`

### Change the working directory

Update the constant at the top of `main.py`:

```python
CONFIG_DIR = Path.home() / ".env-tools"
```

---

## 6. FAQ

**Q1. Download stuck at some percentage?**
Likely a slow mirror. Click **Cancel** and retry, or switch mirrors as described above.

**Q2. Env-variable write fails?**
- Windows: relaunch as Administrator if you need system-scope variables. The tool defaults to **user scope**, which usually doesn't require elevation.
- macOS / Linux: make sure your shell rc files are writable.

**Q3. Will my existing `JAVA_HOME` be overwritten?**
Yes — the most recent installation wins. The new `bin` directory is appended to `PATH` idempotently.

**Q4. `.tar.xz` archives?**
Supported (MySQL Linux distribution uses it).

**Q5. `setx` truncation on Windows?**
The tool bypasses `setx`'s 1024-char limit by writing to the registry with `winreg`.

---

## 7. Notes & caveats

- Official download URLs may change over time. If a link 404s, update the URL for that version in `main.py`.
- Some components (e.g. MySQL) require additional post-install steps such as `mysqld --initialize`. This tool only covers **download + extraction + env-var configuration**.
- Prefer a virtual environment to avoid polluting your system Python.

---

## 8. Project layout

```
env-auto-setup/
├─ main.py             # entry point (UI + logic)
├─ requirements.txt    # dependency list
├─ README.md           # Chinese documentation
├─ README_EN.md        # English documentation (this file)
└─ assets/             # (optional) icons and other resources
```

---

## 9. License

This project is released under the **MIT License**. Copyright (c) 2026 **rgh**.

```
MIT License

Copyright (c) 2026 rgh

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

See also <https://opensource.org/licenses/MIT>.
