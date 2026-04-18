import sys
import os
import threading
from tqdm import tqdm
from colorama import Fore, Style, init

init(autoreset=True)

class ProgressManager:
    def __init__(self, total_files):
        self.total_files = total_files
        self._lock = threading.Lock()
        
        # requested format: path | n/total | speed | elapsed < remaining | %
        custom_format = '{desc} | {n_fmt}/{total_fmt} | {rate_fmt} | {elapsed} < {remaining} | {percentage:3.0f}%'
        
        self.main_bar = tqdm(
            total=total_files,
            unit="file",
            desc="Initializing...",
            position=0,
            leave=True,
            bar_format=custom_format,
            dynamic_ncols=True
        )
        
        self.stats = {
            "uploaded": 0,
            "skipped": 0,
            "error": 0,
            "bytes_uploaded": 0
        }

    def _get_display_path(self, file_path):
        """Returns a string like folder/subfolder/.../filename with limited length."""
        try:
            # Get relative to root or just handle segments
            parts = file_path.replace('\\', '/').split('/')
            if len(parts) > 5:
                # Show first, then ... , then last 3
                display = f"{parts[0]}/.../{'/'.join(parts[-3:])}"
            else:
                display = "/".join(parts)
            
            # Pad or truncate to fixed width for alignment
            return f"{display:<50}"[:50]
        except Exception:
            return f"{os.path.basename(file_path):<50}"[:50]

    def update_file_status(self, status, file_path, bytes_size=0):
        display_path = self._get_display_path(file_path)
        file_name = os.path.basename(file_path)
        
        with self._lock:
            # Update bar description
            self.main_bar.set_description(f"{Fore.CYAN}{display_path}")

            if status == "uploaded":
                self.stats["uploaded"] += 1
                self.stats["bytes_uploaded"] += bytes_size
                tqdm.write(f"{Fore.GREEN}[OK]{Style.RESET_ALL} {file_name}")
            elif status == "skipped":
                self.stats["skipped"] += 1
                tqdm.write(f"{Fore.YELLOW}[SKIP]{Style.RESET_ALL} {file_name}")
            elif status == "error":
                self.stats["error"] += 1
                tqdm.write(f"{Fore.RED}[ERR]{Style.RESET_ALL}  {file_name}")
            elif status == "deleted":
                self.stats["deleted"] += 1
            
            self.main_bar.update(1)

    def get_stats(self):
        return self.stats

    def close(self):
        self.main_bar.close()
