import os
from platforms.base import PlatformBase

class WindowsPlatform(PlatformBase):
    def get_system_excludes(self):
        # Full directory names to skip (case-insensitive)
        return [
            '$recycle.bin', 'system volume information', 'msdownld.tmp',
            'program files', 'program files (x86)', 'windows', 'appdata',
            'programdata', 'recovery', 'config.msi', 'local settings',
            'application data', 'cookies', 'nethood', 'printhood', 
            'recent', 'sendto', 'start menu', 'templates',
            'node_modules', '.git', '.vscode', '.idea', 'tencent', 'baidu'
        ]

    def should_skip_dir(self, dir_name, full_path=None):
        """Aggressive filtering for Windows directories."""
        name_lower = dir_name.lower()
        
        # 1. Standard hidden check
        if name_lower.startswith('.') and name_lower != '.':
            return True
            
        # 2. Keyword-based junk filtering (matches if keyword is anywhere in the name)
        junk_patterns = {'cache', 'log', 'temp', 'tmp', 'userdata'}
        if any(pattern in name_lower for pattern in junk_patterns):
            return True
            
        return False

    def is_system_path(self, path):
        # Check for junk keywords in the entire path, not just the filename
        path_lower = path.lower()
        junk_keywords = {
            '\\cache\\', '\\logs\\', '\\temp\\', '\\tmp\\', 
            '\\.gradle\\', '\\.npm\\', '\\.cache\\', '\\userdata\\'
        }
        
        if any(keyword in path_lower for keyword in junk_keywords):
            return True

        # Handle special Windows files
        name = os.path.basename(path).lower()
        system_files = {
            'pagefile.sys', 'hiberfil.sys', 'swapfile.sys', 'thumbs.db',
            'desktop.ini', 'ntuser.dat', 'usrclass.dat', 'ntuser.dat.log1',
            'ntuser.dat.log2', 'sys'
        }
        
        # Exclude extensions likely to be junk
        junk_exts = {'.tmp', '.log', '.bak', '.old', '.cache'}
        _, ext = os.path.splitext(name)
        
        return (
            name in system_files or 
            name.startswith('~$') or 
            ext in junk_exts or
            '.log.' in name # Match rolling logs like app.log.1
        )

    def get_auto_root(self):
        # Detect drive letter of the current script's location
        drive = os.path.splitdrive(os.path.abspath('.'))[0]
        source_path = drive + os.sep
        
        # If C: drive, restrict to Users folder
        if drive.upper() == 'C:':
            source_path = os.path.join(source_path, 'Users')
        
        return source_path
