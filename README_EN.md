# MuRig — Automated Developer Environment Setup

<p align="center">
  <img src="assets/murig.png" alt="MuRig main window" width="760"/>
</p>

<p align="center">
  A cross-platform desktop GUI tool built with <b>Python + PySide6</b> that automates the<br/>
  <b>download → extraction → environment-variable configuration</b> of common developer toolchains.
</p>

> Project: **MuRig** · Author: [**沐编程**](https://nav.qqmu.com) · Platforms: Windows 10/11, macOS 12+, Ubuntu 20.04+ · License: MIT

---

## 1. Download & run (recommended)

**No Python, no source — just double-click.** Grab the build for your system from the **[Releases page](https://github.com/vfaner/murig/releases/latest)**:

| System | File | Notes |
|--------|------|-------|
|  Windows | `murig.exe` | double-click, no installer |
| 🍎 macOS (Apple Silicon) | `murig-macos-arm64.zip` | unzip, open `murig.app` |
| 🍎 macOS (Intel) | `murig-macos-x64.zip` | unzip, open `murig.app` |
| 🐧 Linux (x64) | `murig-linux-x64` | `chmod +x` then run |

First launch: macOS may block the unsigned app — click **"Open Anyway"** under *System Settings → Privacy & Security*, or run `xattr -cr murig.app`. On Windows, SmartScreen → **"More info → Run anyway"**.

---

## 2. Features

- 🖥️ **Cross-platform.** Detects Windows / macOS / Linux and x64 / arm64 at runtime, picks the correct official distribution.
- 📦 **One-click provisioning.** 29 components — language runtimes, build tools, relational & Chinese-domestic databases, the big-data stack and AI CLIs — downloaded, extracted (or compiled) and wired into your environment automatically.
- 🗂️ **Categories & search.** Six category chips; the search box fuzzy-matches names, aliases (`es`, `cache`) and category names (`database`).
- 🌐 **Live versions.** Version lists are fetched from official APIs/archives at startup and can be filtered by typing; on failure the built-in list is used, so the tool works offline.
- 🔍 **Smart detection.** Checks `XXX_HOME` → `PATH` → well-known install paths; configured components show ✓ and are never re-written.
- 🛠️ **Env-var management.** Windows: `winreg` registry writes (bypasses the `setx` 1024-char limit). macOS/Linux: idempotent marked blocks in your shell rc files.
- 📁 **Configurable workspace.** Global / per-category / per-component install directories — see [Workspace](#7-workspace-install-directories).
- 🎨 **Modern UI.** Frameless window, rounded cards, gradient progress bars, colour-coded log.
- 🧠 **Preferences memory.** Remembers the last selected version per component.

---

## 3. Supported components

> Tables in the Chinese README list default versions; at startup every list is refreshed from the official source. Big-data components require JDK — install it first.

- **Java:** JDK (Adoptium Temurin), Apache Maven, Apache Tomcat
- **Python:** Python, Miniconda (silent installer)
- **Frontend:** Node.js, Git
- **Databases:** MySQL, MariaDB, SQL Server 2025 Express (Windows bootstrapper, guided), PostgreSQL (source build on Linux), Redis (source `make` on macOS/Linux), Elasticsearch, openGauss, DaMeng DM8 (ISO extracted, guided), OceanBase (pure-Python RPM unpack), TiDB, KingbaseES (portable server tar), YashanDB — the last five are Linux-only
- **Big Data:** Hadoop, ZooKeeper, Hive, HBase, Spark, Flink, Kafka
- **AI:** Ollama, Claude Code (portable npm install, needs Node.js), CC-Switch

Databases with no anonymous direct download are not bundled (apply on the vendor site): IBM DB2, HighGo, Vastbase, GBase, Oscar.

---

## 4. Screenshots

<p align="center">
  <img src="assets/murig_db_version.png" alt="version drop-down" width="760"/><br/>
  <sub>Version drop-down: lists are fetched live from official sources and filter as you type</sub>
</p>

<p align="center">
  <img src="assets/murig_about.png" alt="about dialog" width="760"/><br/>
  <sub>About dialog: contact channels and product navigation</sub>
</p>

---

## 5. Run from source

```bash
git clone https://github.com/vfaner/murig.git
cd murig
pip install -r requirements.txt   # PySide6 + requests
python main.py
```

- Python 3.9+; the working directory (default `~/.env-tools/`) is created on first launch and can be moved in the Workspace dialog.
- Redis on macOS/Linux and PostgreSQL on Linux need `make` + a C compiler; Claude Code needs Node.js first.

Layout: `<workspace>/<component>/downloads/` for archives, `<workspace>/<component>/<component>-<version>/` for the extracted tool.

---

## 6. Usage

1. (Optional) Filter with a category chip or the search box.
2. Pick a version — click, or type to filter (`21`, `3.12`, `LTS`).
3. **Install**: streamed download (cancellable) → extraction (source packages compile automatically) → `XXX_HOME` written and `bin` appended to `PATH`.
4. **Configure Only**: run just the env-var step for an already-downloaded component.
5. Watch the colour-coded log for every step.

Apply variables: open a new terminal on Windows; `source ~/.zshrc` (or reopen the terminal) on macOS/Linux. Verify with `java -version`, `mvn -v`, `python --version`, `node -v`, `mysql --version`.

---

## 7. Workspace (install directories)

Everything installs under the built-in default `~/.env-tools/` (the C: drive on Windows). The title-bar **"Workspace"** button opens a dialog; locations resolve in this priority order:

1. **Per component** — the folder-icon button on a card (right-click it to clear);
2. **Per category** — one directory per category chip;
3. **Global default** — one directory for everything;
4. otherwise the built-in `~/.env-tools/`.

<p align="center">
  <img src="assets/murig_work.png" alt="workspace dialog" width="760"/>
</p>

- Settings live in `~/.murig/config.json`; the legacy `~/.env-tools/config.json` is migrated on first launch.
- **Already-installed components stay where they are** — their env vars keep pointing at the old path.
- Download caches follow the current workspace, so undownloaded components are fetched again after a change.
- Every card shows its effective target as "Install to: …".

---

## 8. Customize & package

- **Add components / versions:** edit `build_components()` in `main.py`; lists are offline defaults, overwritten by the live fetch at startup.
- **Faster mirrors:** swap URL prefixes for Huawei Cloud, Tsinghua TUNA or Alibaba mirrors.
- **Local build:** `pip install pyinstaller && pyinstaller murig.spec --noconfirm --clean`.
- **Releases:** pushing a tag (e.g. `git tag v1.2.0 && git push origin v1.2.0`) makes GitHub Actions build Windows / macOS (arm64 + x64) / Linux artifacts and publish them.

---

## 9. FAQ

**Version fetch fails / download stuck?** The built-in version list is used as fallback, so nothing breaks; cancel and retry a stuck download, or switch mirrors.

**Env-var write fails / will old values be overwritten?** Windows writes user-scope variables, usually without admin rights — rerun as administrator if needed. Re-installing overwrites `XXX_HOME` with the newest path; `PATH` entries are appended once, never duplicated.

**Is MySQL usable right after extraction?** No — run `mysqld --initialize` yourself. The tool covers download + extraction + env vars only.

**Archive formats?** `.zip`, `.tar.gz`, `.tar.xz`, magic-byte-sniffed `.tar` (KingbaseES is gzip in disguise), RPM (pure-Python unpack for OceanBase) and AppImage (needs FUSE).

**Claude Code: `npm` not found?** Install Node.js from the Frontend category first.

---

## 10. License

MIT License. Copyright © 2026 [**沐编程**](https://nav.qqmu.com). See [LICENSE](LICENSE).

---

<p align="center">
  Made with ❤️ by <b><a href="https://nav.qqmu.com">沐编程</a></b>
</p>
