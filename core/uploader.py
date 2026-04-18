import os
import hashlib
from concurrent.futures import ProcessPoolExecutor
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from core.logger import get_logger

# Shared Process Pool for CPU-bound tasks (Hashing)
import psutil
try:
    _cpu_count = psutil.cpu_count(logical=False) or 1
except (PermissionError, OSError):
    _cpu_count = 1

_HASHING_POOL = ProcessPoolExecutor(max_workers=max(1, _cpu_count))

def compute_file_md5(file_path):
    """Stand-alone function for process-based hashing."""
    hash_md5 = hashlib.md5()
    # Use larger buffer (128KB) for faster I/O
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(128 * 1024), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

class Uploader:
    def __init__(self, auth_manager, state_manager, config):
        self.auth_manager = auth_manager
        self.state_manager = state_manager
        self.config = config
        self.logger = get_logger()
        self.chunk_size = config['performance'].get('chunk_size_mb', 5) * 1024 * 1024
        self.dry_run = config['backup'].get('dry_run', True)

    def _calculate_md5(self, file_path):
        """Calculates MD5 hash of a file using the shared process pool."""
        future = _HASHING_POOL.submit(compute_file_md5, file_path)
        return future.result()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((HttpError, ConnectionError, TimeoutError)),
        reraise=True
    )
    def upload_file(self, local_path, parent_id):
        """Uploads a file using resumable upload logic with verification."""
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would upload {local_path}")
            return {"id": "dry_run_id_" + os.path.basename(local_path), "md5Checksum": "dry_run_md5"}

        service = self.auth_manager.get_service()
        file_name = os.path.basename(local_path)
        stats = os.stat(local_path)
        
        file_metadata = {
            'name': file_name,
            'parents': [parent_id]
        }
        
        media = MediaFileUpload(
            local_path,
            mimetype=None,
            chunksize=self.chunk_size,
            resumable=True
        )

        try:
            # Check if we have an existing session (simplified for now as google-api-client 
            # handles internal retries, but we could extend this with manual session URLs)
            request = service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id, size, md5Checksum'
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    # Log internal progress for large files
                    self.logger.debug(f"Uploading {file_name}: {int(status.progress() * 100)}%")

            # VERIFICATION
            if response:
                remote_size = int(response.get('size', 0))
                remote_md5 = response.get('md5Checksum')
                
                # Mandatory Size Match
                if remote_size != stats.st_size:
                    raise ValueError(f"Size mismatch for {file_name}: expected {stats.st_size}, got {remote_size}")

                # Optional Hash Check
                if self.config['backup'].get('verify_hash', True):
                    local_md5 = self._calculate_md5(local_path)
                    if remote_md5 and remote_md5 != local_md5:
                        raise ValueError(f"MD5 mismatch for {file_name}: expected {local_md5}, got {remote_md5}")
                    response['md5Checksum'] = local_md5 # Ensure it's in response for state updating

            return response
        except Exception as e:
            self.logger.error(f"Error uploading {file_name}: {e}")
            raise

    def get_or_create_folder(self, folder_name, parent_id='root'):
        if self.dry_run:
            return "dry_run_folder_id_" + folder_name

        service = self.auth_manager.get_service()
        query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        
        try:
            results = service.files().list(q=query, fields="files(id)").execute()
            files = results.get('files', [])
            
            if files:
                return files[0]['id']
            
            # Create folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            return folder.get('id')
        except Exception as e:
            self.logger.error(f"Error getting/creating folder {folder_name}: {e}")
            return None
