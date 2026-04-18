from abc import ABC, abstractmethod
import os

class PlatformBase(ABC):
    @abstractmethod
    def get_system_excludes(self):
        """Returns a list of system-specific directory names/paths to exclude."""
        pass

    @abstractmethod
    def is_system_path(self, path):
        """Returns True if the path is a system-protected path that should be skipped."""
        pass

    @abstractmethod
    def get_auto_root(self):
        """Returns the default root path for this platform."""
        pass

    def should_skip_dir(self, dir_name, full_path=None):
        """Default logic for skipping hidden directories."""
        return dir_name.startswith('.') and dir_name != '.'

    def should_skip_file(self, file_name):
        """Default logic for skipping hidden files."""
        return file_name.startswith('.')
