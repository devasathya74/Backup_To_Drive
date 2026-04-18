import os
from core.logger import get_logger

class FileScanner:
    def __init__(self, platform, config, stop_event=None):
        self.platform = platform
        self.config = config
        self.stop_event = stop_event
        self.logger = get_logger()
        self.excluded_extensions = set(config['backup'].get('excluded_extensions', []))
        self.skip_hidden = config['backup'].get('skip_hidden', True)

    def count_files(self, root_path, skip_map=None):
        """Quickly counts files to be processed, ignoring skips."""
        count = 0
        for _ in self.scan(root_path, skip_map=skip_map):
            count += 1
        return count

    def scan(self, root_path, skip_map=None):
        """Generator that yields file paths one by one, optionally skipping known files."""
        self.logger.info(f"Starting scan of {root_path}")
        skip_map = skip_map or {}
        
        system_excludes = [e.lower() for e in self.platform.get_system_excludes()]

        def on_walk_error(error):
            self.logger.warning(f"Scan error (Skipping folder): {error}")

        for root, dirs, files in os.walk(root_path, topdown=True, onerror=on_walk_error):
            if self.stop_event and self.stop_event.is_set():
                break
            
            # Filter directories in-place to prevent further descent
            original_dirs = list(dirs)
            try:
                dirs[:] = [
                    d for d in dirs 
                    if d.lower() not in system_excludes 
                    and not (self.skip_hidden and self.platform.should_skip_dir(d, os.path.join(root, d)))
                    and not os.path.islink(os.path.join(root, d))
                ]
            except PermissionError:
                dirs[:] = [] # Clear if we can't search this branch
                continue
            
            # Log skipped directories for transparency
            skipped = set(original_dirs) - set(dirs)
            if skipped:
                self.logger.debug(f"Skipping directories: {skipped}")

            for file in files:
                file_path = os.path.join(root, file)
                
                # Check extension
                root_name, ext = os.path.splitext(file)
                ext = ext.lower()[1:]
                if f".{ext}" in self.excluded_extensions:
                    continue
                
                # Check if hidden
                if self.skip_hidden and self.platform.should_skip_file(file):
                    continue

                # Check if system path
                if self.platform.is_system_path(file_path):
                    continue

                # Handle permission errors during yield
                try:
                    if not os.access(file_path, os.R_OK):
                        self.logger.warning(f"Permission denied: {file_path}")
                        continue
                    
                    # Differential Scan Check: Skip if metadata matches exactly
                    if file_path in skip_map:
                        stored_size, stored_mtime = skip_map[file_path]
                        try:
                            stats = os.stat(file_path)
                            if stats.st_size == stored_size and stats.st_mtime == stored_mtime:
                                continue # INSTANT SKIP - no yielding, no counting
                        except (PermissionError, FileNotFoundError):
                            continue

                    yield file_path
                except Exception as e:
                    self.logger.error(f"Error accessing {file_path}: {e}")
