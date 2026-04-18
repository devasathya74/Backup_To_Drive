import os
from platforms.base import PlatformBase

class LinuxPlatform(PlatformBase):
    def get_system_excludes(self):
        return [
            '/proc', '/sys', '/dev', '/run', '/tmp', '/var/tmp',
            '/lost+found', '/mnt', '/media'
        ]

        for system_dir in self.get_system_excludes():
            if abs_path.startswith(system_dir):
                return True
        return False

    def get_auto_root(self):
        return '/'
