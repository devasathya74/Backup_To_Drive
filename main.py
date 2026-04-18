import json
import os
import sys
import argparse
import signal
import platform
import threading
from core.logger import setup_logger
from core.auth import AuthManager
from core.state import StateManager
from core.scanner import FileScanner
from core.uploader import Uploader
from core.progress import ProgressManager
from core.worker import BackupWorker
from core.sync import CloudSyncManager
from platforms.windows import WindowsPlatform
from platforms.linux import LinuxPlatform
from platforms.termux import TermuxPlatform

# Global stop event for smooth shutdown
STOP_EVENT = threading.Event()

def get_platform():
    system = platform.system().lower()
    if system == 'windows':
        return WindowsPlatform()
    elif system == 'linux':
        if 'TERMUX_VERSION' in os.environ:
            return TermuxPlatform()
        return LinuxPlatform()
    elif system == 'android':
        return TermuxPlatform()
    else:
        raise NotImplementedError(f"Platform {system} not supported yet.")

def load_config(config_path):
    with open(config_path, 'r') as f:
        return json.load(f)

def setup_signal_handlers():
    def handler(sig, frame):
        if not STOP_EVENT.is_set():
            print("\n🛑 Shutdown signal received. Finishing active tasks and stopping...")
            STOP_EVENT.set()
        else:
            print("\n⚠️ Force quitting...")
            sys.exit(1)
    
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

def main():
    parser = argparse.ArgumentParser(description="Google Drive Backup Engine")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument("--dry-run", action="store_true", help="Run without uploading or deleting")
    args = parser.parse_args()

    setup_signal_handlers()

    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    try:
        config = load_config(args.config)
        if args.dry_run:
            config['backup']['dry_run'] = True

        logger = setup_logger(
            log_dir=config['logging'].get('log_dir', 'logs'),
            log_level=config['logging'].get('log_level', 'INFO')
        )
        
        source_path = config['backup'].get('source_path', '.')
        plat = get_platform()
        
        # PROACTIVE: On Android, if default root is chosen, force shared storage
        # This prevents backing up the app's internal home folder by accident.
        if isinstance(plat, TermuxPlatform) and source_path in ['.', './']:
            source_path = "AUTO_ROOT"

        if source_path == "AUTO_ROOT":
            source_path = plat.get_auto_root()
            logger.info(f"Resolved AUTO_ROOT to: {source_path}")
        
        config['backup']['source_path'] = os.path.abspath(source_path)
        
        # Initialize components
        auth = AuthManager(config)
        
        # --- CLOUD STATE SYNC (BOOTSTRAP) ---
        sync_mgr = CloudSyncManager(auth, config)
        sync_mgr.initialize()
        
        # Display Historical Summary
        summary = sync_mgr.get_last_session_summary()
        if summary:
            from colorama import Fore, Style
            ls = summary.get("last_session", {})
            ts = ls.get("timestamp", "Never")
            is_new = ts == "Never"
            
            print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════╗")
            print(f"║ {Fore.YELLOW}  BACKUP SESSION HISTORICAL SUMMARY                      {Fore.CYAN}║")
            print(f"╠══════════════════════════════════════════════════════════╣")
            print(f"║ {Fore.WHITE}  Total Sessions: {Fore.YELLOW}{summary.get('total_sessions', 0):<3} sessions performed         {Fore.CYAN}║")
            print(f"║ {Fore.WHITE}  Last run ended: {Fore.YELLOW}{ts[:10]} @ {ts[11:19] if not is_new else ''}            {Fore.CYAN}║")
            print(f"║ {Fore.WHITE}  Last Uploads:   {Fore.GREEN}{ls.get('uploads', 0):<8} {Fore.WHITE}  Last Errors: {Fore.RED}{ls.get('errors',0):<8} {Fore.CYAN}║")
            print(f"╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")

        state = StateManager()
        scanner = FileScanner(plat, config, STOP_EVENT)
        uploader = Uploader(auth, state, config)

        # Resolve Device Folder
        hostname = platform.node() or "Unknown-Device"
        device_folder_name = f"Backup_{hostname}"
        root_id = config['backup'].get('root_folder_id', 'root')
        device_root_id = uploader.get_or_create_folder(device_folder_name, root_id)
        
        if not device_root_id:
            raise RuntimeError(f"Could not resolve device folder {device_folder_name}")
        
        config['backup']['root_folder_id'] = device_root_id

        # Differential Scan: Pre-fetch and count
        logger.info("Syncing metadata with database for instant startup...")
        skip_map = state.get_uploaded_metadata_map()
        
        from tqdm import tqdm
        logger.info("Scanning for new/changed files...")
        total_files = 0
        with tqdm(unit=' files', desc="🔍 Searching", colour='yellow', leave=False) as pbar:
            for _ in scanner.scan(config['backup']['source_path'], skip_map=skip_map):
                total_files += 1
                pbar.update(1)
        
        logger.info(f"Total new/changed files to process: {total_files}")
        progress = ProgressManager(total_files)

        # Run Backup Worker
        worker = BackupWorker(auth, scanner, uploader, state, progress, config, STOP_EVENT)
        import time
        start_time = time.time()
        worker.run()
        elapsed_time = time.time() - start_time

        # Finalize Sync
        total_cumulative = state.get_total_backed_up_count()
        state.close()
        from core.logger import get_log_content
        final_stats = progress.get_stats()
        sync_mgr.finalize(
            log_content=get_log_content(),
            stats={"uploads": final_stats["uploaded"], "errors": final_stats["error"]}
        )

        progress.close()
        
        from colorama import Fore, Style
        # Success Box
        print(f"\n{Fore.GREEN}╔══════════════════════════════════════════════════════════╗")
        print(f"║ {Fore.WHITE}🎉  BACKUP PROCESS COMPLETED SUCCESSFULLY!                {Fore.GREEN}║")
        print(f"╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
        
        # Detailed Report Box
        mins, secs = divmod(int(elapsed_time), 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        
        print(f"{Fore.CYAN}╔══════════════════════════════════════════════════════════╗")
        print(f"║ {Fore.YELLOW}  SESSION PERFORMANCE REPORT                             {Fore.CYAN}║")
        print(f"╠══════════════════════════════════════════════════════════╣")
        print(f"║ {Fore.WHITE}  Session Duration:  {Fore.YELLOW}{time_str:<10}                     {Fore.CYAN}║")
        print(f"║ {Fore.WHITE}  Session Uploads:   {Fore.GREEN}{final_stats['uploaded']:<10}                     {Fore.CYAN}║")
        print(f"║ {Fore.WHITE}  Total Backed Up:   {Fore.CYAN}{total_cumulative:<10} (Cumulative)        ║")
        print(f"║ {Fore.WHITE}  Session Errors:    {Fore.RED}{final_stats['error']:<10}                     {Fore.CYAN}║")
        print(f"╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")
        
        logger.info("Backup process completed successfully.")

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        if 'logger' in locals():
            logger.critical(f"FATAL ERROR: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
