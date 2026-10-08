# MuRig — Automated Developer Environment Setup

A cross-platform desktop GUI tool built with Python + PySide6 that automates the download, extraction and environment-variable configuration of common developer toolchains. Save yourself from tedious manual installation.

> Project: **MuRig**
> Author: [**沐编程**](https://nav.qqmu.com)
> Platforms: Windows 10/11, macOS 12+, Ubuntu 20.04+
> License: MIT License

---

## 1. Features

- 🖥️ **Cross-platform.** Detects Windows / macOS / Linux (and x64 / arm64) at runtime and picks the correct distribution.
- 🗂️ **Categories & global search.** Components are organized into six categories — **Java / Python / Frontend / Databases / Big Data / AI**. Click a category chip to filter, or type a software name, alias (e.g. `es`, `cache`) or category name (e.g. `database`) into the search box for fuzzy matching; chips and keywords can be combined.
- 📦 **One-click provisioning.** 29 preloaded components — the whole pipeline (download → unpack/build → configure) is automated:
    - **Java:** JDK (Adoptium Temurin — 21 / 17 / 11 / 8), Apache Maven, Apache Tomcat
    - **Python:** Python (3.12 / 3.11 / 3.10 / 3.9), Miniconda
    - **Frontend:** Node.js (20 / 18 / 16), Git
    - **Databases:** MySQL, MariaDB (12.3 / 11.4 LTS / 10.11 LTS), SQL Server 2025 Express (Windows online bootstrapper, guided), PostgreSQL (EDB binaries on Win/macOS; source auto-build on Linux), Redis (source auto-`make` on macOS/Linux; community Windows port), Elasticsearch (8.15 / 7.17), openGauss (Linux only), DaMeng DM8 (ISO extracted, GUI installer guided), OceanBase (Linux only; RPM unpacked in pure Python), TiDB (Linux only, x86_64/arm64), KingbaseES (Linux only; portable server tar with built-in license; Referer header sent automatically), YashanDB (Linux only; yasboot init)
    - **Big Data:** Hadoop, ZooKeeper, Hive, HBase, Spark, Flink, Kafka
    - **AI:** Ollama (local LLM runtime), Claude Code (portable npm install — Node.js required), CC-Switch (portable zip / .app / AppImage)
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
│  MuRig By 沐编程                         About — ▢ × │
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
git clone https://github.com/yourname/murig.git
cd murig

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

1. (Optional) Filter cards: click a category chip (e.g. **Big Data**) or type a name/alias/category keyword (e.g. `redis`, `es`, `database`) in the search box.
2. Pick a version from the drop-down.
3. Click **"Install"**:
    - the archive is streamed and the progress bar updates continuously;
    - it is extracted to `~/.env-tools/<component>/<component>-<version>/` (source packages like Redis are compiled automatically);
    - the corresponding `XXX_HOME` variable is written and the executable's directory is appended to `PATH`.
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

**Q4. `.tar.xz` / `.tar` / `.rpm` / AppImage archives?**
`.tar.xz` is supported (MySQL Linux distribution uses it). KingbaseES portable builds carry a `.tar` suffix but are in fact gzip-compressed; the extractor opens them with `tarfile` mode `r:*`, which sniffs the real format by magic bytes (genuine uncompressed tar works too). RPM packages (e.g. OceanBase) are unpacked with a built-in pure-Python parser (xz/lzma + cpio), so no system `rpm2cpio` is needed. AppImages (e.g. CC-Switch on Linux) are downloaded as-is and marked executable — a system with FUSE support is required to run them.

**Q5. Which Chinese/domestic databases are supported?**
- **DaMeng DM8:** official packages are zip-wrapped ISO images; the tool extracts the ISO, then instructs you to mount it and run the vendor installer (a system-level, interactive step).
- **openGauss / OceanBase / TiDB / KingbaseES / YashanDB (Linux only):** downloaded and unpacked automatically; instance initialization is documented in the post-install notes (KingbaseES sends a `Referer` header to pass the vendor's OSS hotlink protection).
- **Not bundled (no anonymous direct download — apply on the vendor site):** IBM DB2 (Fix Central requires an IBMid), HighGo (name/phone/SMS/email), Vastbase (name/phone/SMS/company/MAC, 90-day MAC-bound license), GBase (login + enterprise real-name verification), Oscar/神通 (login-only download page with no public files).

**Q6. Claude Code install fails: `npm` not found?**
Install Node.js first (available as a component in this tool), then click Install on the Claude Code card again.

**Q7. `setx` truncation on Windows?**
The tool bypasses `setx`'s 1024-char limit by writing to the registry with `winreg`.

---

## 7. Notes & caveats

- Official download URLs may change over time. If a link 404s, update the URL for that version in `main.py`.
- Some components (e.g. MySQL) require additional post-install steps such as `mysqld --initialize`. This tool only covers **download + extraction + env-var configuration**.
- Prefer a virtual environment to avoid polluting your system Python.

---

## 8. Project layout

```
murig/
├─ main.py             # entry point (UI + logic)
├─ requirements.txt    # dependency list
├─ README.md           # Chinese documentation
├─ README_EN.md        # English documentation (this file)
└─ assets/             # (optional) icons and other resources
```

---

## 9. License

This project is released under the **MIT License**. Copyright © 2026 [**沐编程**](https://nav.qqmu.com).

See the [LICENSE](LICENSE) file in the repository root for the full text, or visit <https://opensource.org/licenses/MIT>.
