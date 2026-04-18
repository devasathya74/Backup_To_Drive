import os
from platforms.base import PlatformBase

class TermuxPlatform(PlatformBase):
    def get_system_excludes(self):
        # Termux specific system folders in /data/data/com.termux/files
        return [
            '/data', '/system', '/vendor', '/etc'
        ]

    def is_system_path(self, path):
        # Android storage permissions can be tricky
        return False # Primarily rely on scanner to skip inaccessible folders

    def get_auto_root(self):
        # Prefer shared storage if available, fallback to home
        if os.path.exists('/sdcard'):
            return '/sdcard'
        return '/data/data/com.termux/files/home'
