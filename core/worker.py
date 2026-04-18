import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.logger import get_logger

class BackupWorker:
    def __init__(self, auth_manager, scanner, uploader, state_manager, progress_manager, config, stop_event=None):
        self.auth_manager = auth_manager
        self.scanner = scanner
        self.uploader = uploader
        self.state_manager = state_manager
        self.progress_manager = progress_manager
        self.config = config
        self.stop_event = stop_event
        self.logger = get_logger()
        self.max_workers = config['performance'].get('max_workers', 5)
        self.folder_id_cache = {}
        self._cache_lock = threading.Lock()

    def run(self):
        import psutil
        import time

        source_path = self.config['backup']['source_path']
        root_folder_id = self.config['backup'].get('root_folder_id', 'root')
        
        self.logger.info(f"Starting backup workers (max_workers={self.max_workers})")

        # Differential Scanning: Skip already uploaded files during walk
        skip_map = self.state_manager.get_uploaded_metadata_map()
        
        # Bounded processing: prevent memory overflow
        semaphore = threading.Semaphore(self.max_workers + 2)
        
        def task_wrapper(file_path):
            try:
                self._process_file(file_path, source_path, root_folder_id)
            finally:
                semaphore.release()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for file_path in self.scanner.scan(source_path, skip_map=skip_map):
                # Smooth Stop Check
                if self.stop_event and self.stop_event.is_set():
                    self.logger.info("Smooth stop active: No more files will be queued.")
                    break

                # --- OVERLOAD PROTECTION ---
                try:
                    cpu_usage = psutil.cpu_percent()
                    mem_usage = psutil.virtual_memory().percent
                    
                    if cpu_usage > 90 or mem_usage > 90:
                        self.logger.warning(f"CRITICAL LOAD: CPU {cpu_usage}% | RAM {mem_usage}%. Throttling...")
                        time.sleep(5)
                        continue

                    elif cpu_usage > 80 or mem_usage > 85:
                        self.logger.info(f"High Load detected (CPU: {cpu_usage}%, RAM: {mem_usage}%). Throttling submission...")
                        time.sleep(2)
                except (PermissionError, OSError):
                    # Fallback for Termux/Android where /proc access is restricted
                    pass

                # Acquire semaphore before submitting (blocks if queue is full)
                semaphore.acquire()
                executor.submit(task_wrapper, file_path)

        if self.stop_event and self.stop_event.is_set():
            self.logger.info("Cleanup of active tasks finished. Exiting smoothly.")


    def _process_file(self, file_path, source_path, root_folder_id):
        file_name = os.path.basename(file_path)
        stats = os.stat(file_path)
        
        try:
            # Build folder structure on Drive
            rel_path = os.path.relpath(os.path.dirname(file_path), source_path)
            parent_id = self._recursive_get_folder(rel_path, root_folder_id)

            if not parent_id:
                self.logger.error(f"Failed to resolve parent folder for {file_path}")
                self.progress_manager.update_file_status("error", file_path)
                return

            # Perform upload
            self.logger.info(f"Uploading {file_name}...")
            response = self.uploader.upload_file(file_path, parent_id)
            
            if response and 'id' in response:
                # Update state with hash if available
                self.state_manager.update_file(
                    path=file_path,
                    size=stats.st_size,
                    mtime=stats.st_mtime,
                    md5=response.get('md5Checksum'),
                    drive_id=response['id'],
                    status='uploaded'
                )
                self.progress_manager.update_file_status("uploaded", file_path, stats.st_size)
            else:
                self.progress_manager.update_file_status("error", file_path)
                
        except Exception as e:
            self.logger.error(f"Failed to process {file_name}: {e}")
            self.progress_manager.update_file_status("error", file_path)

    def _recursive_get_folder(self, rel_path, root_id):
        if not rel_path or rel_path == '.':
            return root_id
        
        with self._cache_lock:
            if rel_path in self.folder_id_cache:
                return self.folder_id_cache[rel_path]

        parts = rel_path.split(os.sep)
        current_parent = root_id
        current_path = ""

        for part in parts:
            if not part: continue
            current_path = os.path.join(current_path, part) if current_path else part
            
            with self._cache_lock:
                if current_path in self.folder_id_cache:
                    current_parent = self.folder_id_cache[current_path]
                    continue
            
            # Create/get folder (this part is fine to be outside the lock 
            # as long as we put the result back with a lock)
            folder_id = self.uploader.get_or_create_folder(part, current_parent)
            
            with self._cache_lock:
                self.folder_id_cache[current_path] = folder_id
            
            current_parent = folder_id
        
        return current_parent
