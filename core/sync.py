import os
import platform
import shutil
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import json
from datetime import datetime
from tqdm import tqdm
from core.logger import get_logger

class CloudSyncManager:
    def __init__(self, auth_manager, config):
        self.auth_manager = auth_manager
        self.config = config
        self.logger = get_logger()
        self.hostname = platform.node() or "unknown-device"
        self.system_folder_name = f".backup_metadata_{self.hostname}"
        self.system_folder_id = None
        self.db_filename = "backup_state.db"
        self.log_filename = "upload.log"
        self.summary_filename = "summary.json"
        self.summary = {"total_sessions": 0, "last_session": {"timestamp": "Never", "uploads": 0, "errors": 0}}

    def initialize(self):
        """Initial check and download of remote state."""
        self.logger.info("Initializing Cloud State Sync...")
        
        # 1. Resolve/Create system folder
        root_id = self.config['backup'].get('root_folder_id', 'root')
        self.system_folder_id = self._get_or_create_system_folder(self.system_folder_name, root_id)
        
        if not self.system_folder_id:
            self.logger.warning("Could not resolve cloud system folder. Sync disabled.")
            return

        # 2. Load summary metadata from cloud
        self._load_summary()

        # 3. Try to download remote DB if local doesn't exist or is older
        local_db_path = self.db_filename
        remote_db_id = self._find_remote_file(self.db_filename)
        
        if remote_db_id:
            if not os.path.exists(local_db_path):
                self.logger.info("Local database not found. Downloading from cloud...")
                self._download_file(remote_db_id, local_db_path)
            else:
                self.logger.info("Cloud database found. Local will be synced on completion.")
        else:
            self.logger.info("No remote database found. A new one will be created and uploaded later.")

    def get_last_session_summary(self):
        """Returns the pre-loaded summary from cloud."""
        return self.summary

    def _load_summary(self):
        """Downloads and parses the summary.json metadata from Drive."""
        import json
        remote_id = self._find_remote_file(self.summary_filename)
        if not remote_id:
            return

        service = self.auth_manager.get_service()
        try:
            request = service.files().get_media(fileId=remote_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            data = json.loads(fh.getvalue().decode('utf-8'))
            self.summary.update(data)
            self.logger.info(f"Loaded Cloud Summary: Session #{self.summary['total_sessions']}")
        except Exception as e:
            self.logger.warning(f"Could not load cloud summary: {e}")

    def _get_or_create_system_folder(self, folder_name, parent_id):
        service = self.auth_manager.get_service()
        query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        try:
            results = service.files().list(q=query, fields="files(id)").execute()
            files = results.get('files', [])
            if files:
                return files[0]['id']
            
            metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = service.files().create(body=metadata, fields='id').execute()
            return folder.get('id')
        except Exception as e:
            self.logger.error(f"Error resolving system folder {folder_name}: {e}")
            return None

    def finalize(self, log_content=None, stats=None):
        """Upload current DB, logs, and updated summary metadata."""
        if not self.system_folder_id:
            return

        self.logger.info("Finalizing Cloud State Sync: Uploading Metadata, DB and Logs...")
        
        # 1. Update and Upload Summary
        if stats:
            self.summary["total_sessions"] += 1
            self.summary["last_session"] = {
                "timestamp": datetime.now().isoformat(),
                "uploads": stats.get("uploads", 0),
                "errors": stats.get("errors", 0)
            }
            import json
            self._upload_string(json.dumps(self.summary), self.summary_filename, "Backup Session Summary Metadata")

        # 2. Upload Database (Always update remote)
        local_db_path = self.db_filename
        if os.path.exists(local_db_path):
            self._upload_or_update(local_db_path, f"System State: {self.db_filename}")

        # 3. Upload Memory Logs
        if log_content:
            self._upload_string(log_content, self.log_filename, f"System Log: {self.log_filename}")

    def _upload_string(self, content, filename, description):
        """Uploads a string content directly to cloud."""
        remote_id = self._find_remote_file(filename)
        service = self.auth_manager.get_service()
        
        from googleapiclient.http import MediaIoBaseUpload
        fh = io.BytesIO(content.encode('utf-8'))
        media = MediaIoBaseUpload(fh, mimetype='text/plain', resumable=True)
        
        try:
            if remote_id:
                service.files().update(fileId=remote_id, media_body=media).execute()
            else:
                file_metadata = {'name': filename, 'parents': [self.system_folder_id], 'description': description}
                service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            self.logger.info(f"Synced in-memory {filename} to cloud.")
        except Exception as e:
            self.logger.error(f"Failed to sync {filename} to cloud: {e}")

    def _find_remote_file(self, filename):
        service = self.auth_manager.get_service()
        query = f"name = '{filename}' and '{self.system_folder_id}' in parents and trashed = false"
        try:
            results = service.files().list(q=query, fields="files(id)").execute()
            files = results.get('files', [])
            return files[0]['id'] if files else None
        except Exception as e:
            self.logger.error(f"Error searching remote file {filename}: {e}")
            return None

    def _download_file(self, file_id, local_path):
        service = self.auth_manager.get_service()
        request = service.files().get_media(fileId=file_id)
        
        # Get metadata for size
        meta = service.files().get(fileId=file_id, fields='size').execute()
        total_size = int(meta.get('size', 0))
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        
        with tqdm(total=total_size, unit='B', unit_scale=True, desc=f"☁️  Downloading {os.path.basename(local_path)}", colour='cyan', leave=False) as pbar:
            try:
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        pbar.update(int(status.resumable_progress - pbar.n))
                
                with open(local_path, 'wb') as f:
                    f.write(fh.getvalue())
                self.logger.info(f"Successfully downloaded {local_path} from cloud.")
            except Exception as e:
                self.logger.error(f"Failed to download {file_id}: {e}")

    def _upload_or_update(self, local_path, description):
        filename = os.path.basename(local_path)
        remote_id = self._find_remote_file(filename)
        
        service = self.auth_manager.get_service()
        file_size = os.path.getsize(local_path)
        media = MediaFileUpload(local_path, mimetype='application/octet-stream', resumable=True)
        
        with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"☁️  Syncing {filename}", colour='green', leave=False) as pbar:
            try:
                if remote_id:
                    request = service.files().update(fileId=remote_id, media_body=media)
                else:
                    file_metadata = {'name': filename, 'parents': [self.system_folder_id], 'description': description}
                    request = service.files().create(body=file_metadata, media_body=media, fields='id')
                
                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        pbar.update(int(status.resumable_progress - pbar.n))
                
                self.logger.info(f"Synced {filename} to cloud.")
            except Exception as e:
                self.logger.error(f"Failed to sync {filename} to cloud: {e}")
