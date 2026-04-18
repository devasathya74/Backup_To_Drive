import os
import pickle
import threading
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from core.logger import get_logger

class AuthManager:
    def __init__(self, config):
        self.config = config
        self.logger = get_logger()
        self._thread_local = threading.local()
        self._creds = None
        self._lock = threading.Lock()
        self.scopes = ['https://www.googleapis.com/auth/drive']

    def get_service(self):
        # Ensure credentials exist (shared across threads)
        with self._lock:
            if self._creds is None:
                self._creds = self._authenticate()
                
                # Perform a one-time account verification
                temp_service = build('drive', 'v3', credentials=self._creds, cache_discovery=False)
                try:
                    about = temp_service.about().get(fields="user(emailAddress)").execute()
                    email = about.get('user', {}).get('emailAddress', 'Unknown')
                    self.logger.info(f"Authenticated as: {email}", extra={"props": {"email": email}})
                except Exception as e:
                    self.logger.error(f"Failed to verify account: {e}")

        # Return or create thread-specific service
        if not hasattr(self._thread_local, "service"):
            self.logger.debug(f"Creating new Drive service for thread {threading.get_ident()}")
            self._thread_local.service = build('drive', 'v3', credentials=self._creds, cache_discovery=False)
        
        return self._thread_local.service

    def _authenticate(self):
        mode = self.config['auth']['mode']
        
        if mode == "service_account":
            return self._auth_service_account()
        elif mode == "oauth":
            return self._auth_oauth()
        else:
            self.logger.warning(f"Unknown auth mode '{mode}', falling back to OAuth")
            return self._auth_oauth()

    def _auth_service_account(self):
        path = self.config['auth']['service_account_path']
        if not os.path.exists(path):
            self.logger.error(f"Service account file not found at {path}")
            raise FileNotFoundError(f"Service account file not found: {path}")
        
        return service_account.Credentials.from_service_account_file(
            path, scopes=self.scopes
        )

    def _auth_oauth(self):
        creds = None
        token_path = self.config['auth']['token_path']
        creds_path = self.config['auth']['oauth_credentials_path']

        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(creds_path):
                    self.logger.error(f"OAuth credentials file not found at {creds_path}")
                    raise FileNotFoundError(f"OAuth credentials file not found: {creds_path}")
                
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, self.scopes)
                
                try:
                    # Try to open browser automatically
                    creds = flow.run_local_server(port=0)
                except Exception:
                    # Fallback for Termux/SSH/Headless: provide URL manually
                    self.logger.warning("Could not open browser automatically. Switching to manual mode...")
                    print(f"\n{'-'*60}")
                    print("HEADLESS AUTHENTICATION REQUIRED")
                    print(f"{'-'*60}")
                    print("1. Copy the URL below and paste it into your device's browser.")
                    print("2. Log in and allow permissions.")
                    print("3. After completion, this script will continue automatically.")
                    print(f"{'-'*60}\n")
                    
                    creds = flow.run_local_server(port=0, open_browser=False)

            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)

        return creds
