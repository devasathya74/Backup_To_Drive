import os
from platforms.base import PlatformBase

class TermuxPlatform(PlatformBase):
    def get_system_excludes(self):
        # Termux and Android specific system folders
        return [
            '/data', '/system', '/vendor', '/etc', '/proc', '/sys', '/dev',
            '/sdcard/Android', '/storage/emulated/0/Android',
            '.thumbnails', 'cache', '.cache', 'DCIM/.thumbnails'
        ]

    def is_system_path(self, path):
        abs_path = os.path.abspath(path)
        for system_dir in self.get_system_excludes():
            if abs_path.startswith(system_dir):
                return True
        # Skip folders containing .nomedia (Android standard)
        if os.path.exists(os.path.join(abs_path, '.nomedia')):
            return True
        return False

    def get_auto_root(self):
        # Android shared storage is usually here
        sh_storage = '/storage/emulated/0'
        if os.path.exists(sh_storage):
            return sh_storage
        if os.path.exists('/sdcard'):
            return '/sdcard'
        return os.path.expanduser('~')
