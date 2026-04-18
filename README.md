# 🚀 Production-Grade Google Drive Backup Engine

A modular, fault-tolerant, and cross-platform backup system designed to mirror local storage to Google Drive with safety and efficiency.

## 🛠 Features
- **Hybrid Auth**: Service Account (automated) + OAuth 2.0 (manual).
- **True Mirroring**: Maintains exact folder structures.
- **Generator-based Scanning**: Handles 100K+ files with minimal memory usage.
- **Resumable Uploads**: Robust chunk-based uploads with exponential backoff.
- **State Management**: SQLite-backed tracking for crash resume support.
- **Cross-Platform**: Tailored skip logic for Windows, Linux, and Termux (Android).
- **Safe Cleanup**: Automated local file deletion after verified upload (optional).

## 📂 Project Structure
```text
backup_engine/
├── core/
│   ├── auth.py      - Service Account & OAuth flows
│   ├── scanner.py   - Generator-based walker
│   ├── uploader.py  - Chunked resumable uploads
│   ├── worker.py    - Thread-pool orchestrator
│   ├── cleanup.py   - Safe local file deletion
│   ├── logger.py    - Structured JSON logs
│   ├── state.py     - SQLite state management
│   └── progress.py  - Centralized progress manager
├── platforms/
│   ├── windows.py   - NTFS & System folder handling
│   ├── linux.py     - Proc/Sys/Dev exclusions
│   └── termux.py    - Android storage handling
├── config.json      - System configuration
├── main.py          - CLI Entry point
└── requirements.txt - Dependencies
```

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Authentication
- **Service Account**: Place your `service_account.json` in the root folder.
- **OAuth 2.0**: Place your `credentials.json` (Desktop Client) in the root folder.
- Update `config.json` to select your `auth_mode`.

### 3. Run the Engine
**Dry Run (Recommended first):**
```bash
python main.py --dry-run
```

**Production Run:**
```bash
python main.py
```

## ⚙️ Configuration (`config.json`)
- `source_path`: The local directory to back up.
- `root_folder_id`: The target folder ID on Drive (default is 'root').
- `max_workers`: Number of parallel upload threads (default: 5).
- `delete_after_upload`: Set to `true` to delete local files after successful upload.
- `dry_run`: If true, no files are uploaded or deleted.

## 🖥 Platform Specifics
- **Windows**: Automatically skips `$RECYCLE.BIN`, `System Volume Information`, etc.
- **Linux**: Skips `/proc`, `/sys`, `/dev`, etc.
- **Termux**: Designed to handle Android-specific storage paths without permission errors.
