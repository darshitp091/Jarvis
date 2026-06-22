import os
import shutil
import random
from loguru import logger

class FileManager:
    """Manages files and directories on the system for JARVIS"""

    def create_file(self, path: str, content: str = "") -> str:
        try:
            full_path = os.path.abspath(os.path.expanduser(path))
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"File created successfully: {full_path}")
            return f"Successfully created file at {path}, sir."
        except Exception as e:
            logger.error(f"Error creating file: {e}")
            return f"Failed to create file: {str(e)}"

    def rename_file(self, old_path: str, new_path: str) -> str:
        try:
            old_full = os.path.abspath(os.path.expanduser(old_path))
            new_full = os.path.abspath(os.path.expanduser(new_path))
            if not os.path.exists(old_full):
                return f"Sir, the source file at {old_path} does not exist."
            os.makedirs(os.path.dirname(new_full), exist_ok=True)
            os.rename(old_full, new_full)
            logger.info(f"File renamed from {old_full} to {new_full}")
            return f"Successfully renamed file from {old_path} to {new_path}, sir."
        except Exception as e:
            logger.error(f"Error renaming file: {e}")
            return f"Failed to rename file: {str(e)}"

    def move_file(self, src: str, dst: str) -> str:
        try:
            src_full = os.path.abspath(os.path.expanduser(src))
            dst_full = os.path.abspath(os.path.expanduser(dst))
            if not os.path.exists(src_full):
                return f"Sir, the source file at {src} does not exist."
            if os.path.isdir(dst_full):
                dst_full = os.path.join(dst_full, os.path.basename(src_full))
            os.makedirs(os.path.dirname(dst_full), exist_ok=True)
            shutil.move(src_full, dst_full)
            logger.info(f"Moved file from {src_full} to {dst_full}")
            return f"Successfully moved file from {src} to {dst}, sir."
        except Exception as e:
            logger.error(f"Error moving file: {e}")
            return f"Failed to move file: {str(e)}"

    def delete_file(self, path: str, secure_shred: bool = False) -> str:
        try:
            full_path = os.path.abspath(os.path.expanduser(path))
            if not os.path.exists(full_path):
                return f"Sir, the file at {path} does not exist."
            
            if secure_shred:
                # Overwrite file with random bytes before deleting
                size = os.path.getsize(full_path)
                if size > 0:
                    with open(full_path, "wb") as f:
                        # Write zeroes or random bytes in chunks
                        chunk_size = 65536
                        written = 0
                        while written < size:
                            chunk = bytearray(random.getrandbits(8) for _ in range(min(chunk_size, size - written)))
                            f.write(chunk)
                            written += len(chunk)
                        f.flush()
                        os.fsync(f.fileno())
                logger.info(f"File shredded: {full_path}")
            
            os.remove(full_path)
            logger.info(f"File deleted: {full_path}")
            return f"Successfully {'shredded and ' if secure_shred else ''}deleted file {path}, sir."
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return f"Failed to delete file: {str(e)}"

    def create_directory(self, path: str) -> str:
        try:
            full_path = os.path.abspath(os.path.expanduser(path))
            os.makedirs(full_path, exist_ok=True)
            logger.info(f"Directory created: {full_path}")
            return f"Successfully created directory at {path}, sir."
        except Exception as e:
            logger.error(f"Error creating directory: {e}")
            return f"Failed to create directory: {str(e)}"

    def delete_directory(self, path: str) -> str:
        try:
            full_path = os.path.abspath(os.path.expanduser(path))
            if not os.path.exists(full_path):
                return f"Sir, the directory at {path} does not exist."
            shutil.rmtree(full_path)
            logger.info(f"Directory deleted: {full_path}")
            return f"Successfully deleted directory {path}, sir."
        except Exception as e:
            logger.error(f"Error deleting directory: {e}")
            return f"Failed to delete directory: {str(e)}"

    def set_file_hidden(self, path: str, hide: bool = True) -> str:
        """Sets Windows file attribute to hidden (+h) or normal (-h)."""
        import platform
        full_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(full_path):
            return f"Sir, the file at {path} does not exist."
            
        if platform.system() == "Windows":
            try:
                import ctypes
                attrs = ctypes.windll.kernel32.GetFileAttributesW(full_path)
                if hide:
                    new_attrs = attrs | 0x2
                else:
                    new_attrs = attrs & ~0x2
                ctypes.windll.kernel32.SetFileAttributesW(full_path, new_attrs)
                return f"Successfully {'hidden' if hide else 'unhidden'} file {path}, sir."
            except Exception as e:
                return f"Failed to modify file attributes: {e}"
        else:
            dir_name = os.path.dirname(full_path)
            base_name = os.path.basename(full_path)
            if hide and not base_name.startswith("."):
                new_path = os.path.join(dir_name, "." + base_name)
                os.rename(full_path, new_path)
                return f"Successfully hidden file (renamed to .{base_name}), sir."
            elif not hide and base_name.startswith("."):
                new_path = os.path.join(dir_name, base_name[1:])
                os.rename(full_path, new_path)
                return f"Successfully unhidden file (renamed to {base_name[1:]}), sir."
            return "File is already in the requested state, sir."

    def toggle_show_hidden_files(self, show: bool = True) -> str:
        """Toggles show hidden files in Windows Explorer by editing registry settings."""
        import platform
        if platform.system() != "Windows":
            return "Toggling hidden files in Explorer is only supported on Windows, sir."
            
        try:
            import winreg
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SETVALUE)
            val = 1 if show else 2
            winreg.SetValueEx(key, "Hidden", 0, winreg.REG_DWORD, val)
            winreg.CloseKey(key)
            
            import ctypes
            ctypes.windll.user32.PostMessageW(0xFFFF, 0x001A, 0, 0)
            return f"Successfully configured Windows Explorer to {'show' if show else 'hide'} hidden files, sir."
        except Exception as e:
            return f"Failed to update Explorer settings in registry: {e}"

    def get_folder_size(self, path: str) -> str:
        """Calculates size of folder recursively."""
        full_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(full_path):
            return f"Sir, the folder at {path} does not exist."
            
        total_size = 0
        file_count = 0
        try:
            for root, dirs, files in os.walk(full_path):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        total_size += os.path.getsize(fp)
                        file_count += 1
            
            if total_size < 1024 * 1024:
                size_str = f"{total_size / 1024:.2f} KB"
            elif total_size < 1024 * 1024 * 1024:
                size_str = f"{total_size / (1024 * 1024):.2f} MB"
            else:
                size_str = f"{total_size / (1024 * 1024 * 1024):.2f} GB"
                
            return f"Folder size for {path} is {size_str} ({file_count} files), sir."
        except Exception as e:
            return f"Failed to calculate folder size: {e}"

    def sync_folders(self, src: str, dst: str) -> str:
        """Copies modified or new files recursively from source directory to target destination."""
        src_full = os.path.abspath(os.path.expanduser(src))
        dst_full = os.path.abspath(os.path.expanduser(dst))
        
        if not os.path.exists(src_full):
            return f"Sir, the source folder at {src} does not exist."
            
        try:
            copied = 0
            created_dirs = 0
            for root, dirs, files in os.walk(src_full):
                rel_path = os.path.relpath(root, src_full)
                target_dir = dst_full if rel_path == "." else os.path.join(dst_full, rel_path)
                
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir, exist_ok=True)
                    created_dirs += 1
                    
                for file in files:
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    
                    if not os.path.exists(dst_file) or os.path.getmtime(src_file) > os.path.getmtime(dst_file):
                        shutil.copy2(src_file, dst_file)
                        copied += 1
            return f"Sync complete, sir. Copied {copied} files and created {created_dirs} directories in {dst}."
        except Exception as e:
            return f"Folder synchronization failed: {e}"

    def backup_to_local_cloud(self, src: str, cloud_provider: str = "onedrive") -> str:
        """Backs up files to local sync folders of OneDrive or Google Drive."""
        provider = cloud_provider.lower().strip()
        user_home = os.path.expanduser("~")
        
        paths = {
            "onedrive": [os.path.join(user_home, "OneDrive"), os.path.join(user_home, "OneDrive - Personal")],
            "google_drive": [os.path.join(user_home, "Google Drive"), os.path.join(user_home, "GoogleDrive"), r"G:\My Drive"]
        }
        
        matched_dir = None
        for p in paths.get(provider, []):
            if os.path.exists(p):
                matched_dir = p
                break
                
        if not matched_dir:
            return f"Sir, I could not find a local synchronized directory for {cloud_provider} on this PC."
            
        backup_dest = os.path.join(matched_dir, "JARVIS_Backup", os.path.basename(src.rstrip("/\\")))
        return self.sync_folders(src, backup_dest)
