import os
from platforms.base import PlatformBase

class LinuxPlatform(PlatformBase):
    def get_system_excludes(self):
        return [
            '/proc', '/sys', '/dev', '/run', '/tmp', '/var/tmp',
            '/lost+found', '/mnt', '/media', '/boot', '/root',
            '.cache', '.local/share/Trash'
        ]

    def is_system_path(self, path):
        abs_path = os.path.abspath(path)
        for system_dir in self.get_system_excludes():
            if abs_path.startswith(system_dir):
                return True
        return False

    def get_auto_root(self):
        # Target user data by default in production
        return os.path.expanduser('~')
