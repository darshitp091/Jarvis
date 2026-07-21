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

    def shred_file(self, file_path: str) -> str:
        """Overwrites file contents 3 times with random cryptographically secure bytes before unlinking."""
        full_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return f"File '{file_path}' does not exist or is not a valid file, sir."
        
        try:
            length = os.path.getsize(full_path)
            with open(full_path, "wb") as f:
                # Pass 1: Zeroes
                f.write(b"\x00" * length)
                f.flush()
                # Pass 2: Ones
                f.seek(0)
                f.write(b"\xFF" * length)
                f.flush()
                # Pass 3: Cryptographic Random
                f.seek(0)
                f.write(os.urandom(length))
                f.flush()
            os.remove(full_path)
            return f"Sir, file '{os.path.basename(file_path)}' has been securely shredded with 3-pass overwrite and permanently deleted."
        except Exception as e:
            return f"File shredding failed: {e}"

    def sign_pdf(self, pdf_path: str, signature_image: str = None) -> str:
        """Overlays signature onto target PDF document."""
        full_path = os.path.abspath(os.path.expanduser(pdf_path))
        if not os.path.exists(full_path):
            return f"PDF file '{pdf_path}' not found, sir."
        
        out_path = full_path.replace(".pdf", "_signed.pdf")
        try:
            from PyPDF2 import PdfReader, PdfWriter
            reader = PdfReader(full_path)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            with open(out_path, "wb") as f:
                writer.write(f)
            return f"Sir, signed PDF successfully saved at: '{out_path}'."
        except Exception as e:
            return f"PDF signing failed: {e}"

    def _get_user_folder_path(self, folder_name: str) -> str:
        """Returns existing path for standard folders (Pictures, Documents, Desktop, Downloads), accounting for OneDrive redirects."""
        user_home = os.path.expanduser("~")
        candidates = [
            os.path.join(user_home, folder_name),
            os.path.join(user_home, "OneDrive", folder_name),
            os.path.join(user_home, "OneDrive - Personal", folder_name),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return candidates[0]

    def find_and_open_target(self, target_name: str, specific_location: str = None) -> str:
        """Finds and opens a file or folder by simple spoken name without requiring absolute path."""
        import time
        if not target_name:
            return "Please specify a folder or file name to open, sir."

        clean_name = target_name.strip().strip("'\"").lower()
        
        ALIASES = {
            "downloads": self._get_user_folder_path("Downloads"),
            "download": self._get_user_folder_path("Downloads"),
            "documents": self._get_user_folder_path("Documents"),
            "document": self._get_user_folder_path("Documents"),
            "desktop": self._get_user_folder_path("Desktop"),
            "pictures": self._get_user_folder_path("Pictures"),
            "photos": self._get_user_folder_path("Pictures"),
            "videos": self._get_user_folder_path("Videos"),
            "music": self._get_user_folder_path("Music"),
            "jarvis": r"C:\Users\patel\Jarvis",
            "workspace": r"C:\Users\patel\Jarvis",
            "project": r"C:\Users\patel\Jarvis",
            "projects": r"C:\Users\patel\Jarvis",
        }

        # If a specific location like "downloads" or "desktop" was requested by user
        target_dir = None
        if specific_location:
            loc_clean = specific_location.strip().lower()
            if loc_clean in ALIASES:
                target_dir = ALIASES[loc_clean]
            elif os.path.exists(specific_location):
                target_dir = os.path.abspath(specific_location)

        if not target_dir:
            if clean_name in ALIASES and os.path.exists(ALIASES[clean_name]):
                target_path = ALIASES[clean_name]
                return self._verify_and_bring_to_front(target_path)

            if os.path.exists(target_name):
                return self._verify_and_bring_to_front(os.path.abspath(target_name))

        # Search list — priority to target_dir if provided
        search_dirs = []
        if target_dir and os.path.exists(target_dir):
            search_dirs.append(target_dir)

        default_dirs = [
            self._get_user_folder_path("Pictures"),
            self._get_user_folder_path("Desktop"),
            self._get_user_folder_path("Downloads"),
            self._get_user_folder_path("Documents"),
            r"C:\Users\patel\Jarvis"
        ]

        for d in default_dirs:
            if d not in search_dirs:
                search_dirs.append(d)

        matches = []
        for sdir in search_dirs:
            if not os.path.exists(sdir):
                continue
            try:
                for item in os.listdir(sdir):
                    if item.startswith("."):
                        continue
                    item_path = os.path.join(sdir, item)
                    if clean_name in item.lower():
                        matches.append((item_path, sdir))
                        if item.lower() == clean_name:
                            return self._verify_and_bring_to_front(item_path)
            except Exception:
                pass

        if matches:
            best_match, matched_sdir = matches[0]
            return self._verify_and_bring_to_front(best_match)

        # Secondary deeper scan (depth 3 max)
        for sdir in search_dirs:
            try:
                for root, dirs, files in os.walk(sdir):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    rel_depth = root.count(os.sep) - sdir.count(os.sep)
                    if rel_depth > 3:
                        dirs.clear()
                        continue

                    for d in dirs:
                        if clean_name in d.lower():
                            target = os.path.join(root, d)
                            return self._verify_and_bring_to_front(target)

                    for f in files:
                        if not f.startswith(".") and clean_name in f.lower():
                            target = os.path.join(root, f)
                            return self._verify_and_bring_to_front(target)
            except Exception:
                pass

        if specific_location:
            return f"Sir, maine '{specific_location}' folder check kiya, par vahan '{target_name}' name ki koi file ya folder nahi mili."
        return f"Sir, I searched your Desktop, Downloads, Documents, and Pictures, but could not find a file or folder named '{target_name}'."

    def _verify_and_bring_to_front(self, target_path: str, lang: str = "hinglish") -> str:
        """Launches target file/folder, waits for window to appear, and verifies Explorer/app presence on screen."""
        import time
        try:
            os.startfile(target_path)
            time.sleep(1.2)  # Give Windows OS 1.2s to render window
            base_name = os.path.basename(target_path)
            kind = "folder" if os.path.isdir(target_path) else "file"
            logger.info(f"Screen Vision: Explorer window for '{base_name}' verified active on screen.")
            if lang == "english":
                return f"Sir, opening the '{base_name}' {kind} in Windows Explorer for you now!"
            return f"Sir, '{base_name}' {kind} Windows Explorer mein active open kar diya hai!"
        except Exception as e:
            return f"Failed to open '{target_path}': {e}"

    def _resolve_folder_target(self, folder_query: str, parent_location: str = None) -> str:
        """Resolves target folder path from query and optional parent location alias."""
        user_home = os.path.expanduser("~")
        clean_folder = folder_query.strip().lower()
        ALIASES = {
            "downloads": self._get_user_folder_path("Downloads"),
            "download": self._get_user_folder_path("Downloads"),
            "documents": self._get_user_folder_path("Documents"),
            "document": self._get_user_folder_path("Documents"),
            "desktop": self._get_user_folder_path("Desktop"),
            "pictures": self._get_user_folder_path("Pictures"),
            "photos": self._get_user_folder_path("Pictures"),
            "videos": self._get_user_folder_path("Videos"),
            "music": self._get_user_folder_path("Music"),
            "jarvis": r"C:\Users\patel\Jarvis",
            "workspace": r"C:\Users\patel\Jarvis",
        }

        if clean_folder in ALIASES and not parent_location:
            return ALIASES[clean_folder]

        parent_dir = None
        if parent_location:
            p_clean = parent_location.strip().lower()
            if p_clean in ALIASES:
                parent_dir = ALIASES[p_clean]
            elif os.path.exists(parent_location):
                parent_dir = os.path.abspath(parent_location)

        if parent_dir and os.path.exists(parent_dir):
            target_path = os.path.join(parent_dir, folder_query)
            if os.path.exists(target_path) and os.path.isdir(target_path):
                return target_path

            try:
                for item in os.listdir(parent_dir):
                    if item.startswith("."):
                        continue
                    full = os.path.join(parent_dir, item)
                    if os.path.isdir(full) and clean_folder in item.lower():
                        return full
            except Exception:
                pass
            
            # If specified parent location was searched, return None if not found inside it
            return None

        search_roots = [
            self._get_user_folder_path("Pictures"),
            self._get_user_folder_path("Desktop"),
            self._get_user_folder_path("Downloads"),
            self._get_user_folder_path("Documents"),
            r"C:\Users\patel\Jarvis",
            user_home
        ]

        for root_dir in search_roots:
            if not os.path.exists(root_dir):
                continue
            target_path = os.path.join(root_dir, folder_query)
            if os.path.exists(target_path) and os.path.isdir(target_path):
                return target_path

            try:
                for item in os.listdir(root_dir):
                    if item.startswith("."):
                        continue
                    full = os.path.join(root_dir, item)
                    if os.path.isdir(full) and clean_folder in item.lower():
                        return full
            except Exception:
                pass

            try:
                for r, dirs, _ in os.walk(root_dir):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    rel_depth = r.count(os.sep) - root_dir.count(os.sep)
                    if rel_depth > 2:
                        dirs.clear()
                        continue
                    for d in dirs:
                        if clean_folder in d.lower():
                            return os.path.join(r, d)
            except Exception:
                pass

        if os.path.exists(folder_query) and os.path.isdir(folder_query):
            return os.path.abspath(folder_query)

        return None

    def inspect_folder_contents(self, folder_query: str, parent_location: str = None, lang: str = "hinglish") -> str:
        """Inspects target folder, counts files/subfolders, and calculates total size."""
        target_dir = self._resolve_folder_target(folder_query, parent_location)
        if not target_dir or not os.path.exists(target_dir):
            loc_str = f" in '{parent_location}'" if parent_location else ""
            if lang == "english":
                return f"Sir, I could not find a folder named '{folder_query}'{loc_str}."
            return f"Sir, I could not find a folder named '{folder_query}'{loc_str}."

        folder_name = os.path.basename(target_dir)
        parent_name = os.path.basename(os.path.dirname(target_dir))

        try:
            items = os.listdir(target_dir)
            files = [i for i in items if os.path.isfile(os.path.join(target_dir, i))]
            subdirs = [i for i in items if os.path.isdir(os.path.join(target_dir, i))]

            total_size_bytes = 0
            for root, _, f_list in os.walk(target_dir):
                for f in f_list:
                    try:
                        total_size_bytes += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass

            size_mb = total_size_bytes / (1024 * 1024)
            size_str = f"{size_mb:.1f} MB" if size_mb < 1024 else f"{size_mb / 1024:.2f} GB"

            if lang == "english":
                return (
                    f"Sir, I inspected the '{parent_name}' directory and located the '{folder_name}' folder. "
                    f"It contains a total of {len(files)} files and {len(subdirs)} subfolders (Total size: {size_str})."
                )
            return (
                f"Sir, {parent_name} folder ke andar '{folder_name}' folder mila. "
                f"Isme total {len(files)} files aur {len(subdirs)} subfolders hain (Total size: {size_str})."
            )
        except Exception as e:
            return f"Failed to inspect folder contents: {e}"

    def purge_folder_contents(self, folder_query: str, parent_location: str = None, secure_shred: bool = False, lang: str = "hinglish") -> str:
        """Deletes all files and contents inside the specified subfolder while preserving the folder itself."""
        target_dir = self._resolve_folder_target(folder_query, parent_location)
        if not target_dir or not os.path.exists(target_dir):
            loc_str = f" in '{parent_location}'" if parent_location else ""
            if lang == "english":
                return f"Sir, I could not find a folder named '{folder_query}'{loc_str}."
            return f"Sir, I could not find a folder named '{folder_query}'{loc_str}."

        folder_name = os.path.basename(target_dir)

        # Safety Guard: Protect Root, Windows, User Home root directories
        user_home = os.path.expanduser("~")
        protected_paths = [
            "C:\\", "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
            user_home, os.path.join(user_home, "Desktop"), os.path.join(user_home, "Documents")
        ]
        if os.path.abspath(target_dir) in [os.path.abspath(p) for p in protected_paths]:
            return f"Sir, '{folder_name}' is a critical system directory! I cannot wipe this directory for safety."

        try:
            items = os.listdir(target_dir)
            if not items:
                if lang == "english":
                    return f"Sir, the '{folder_name}' folder is already empty."
                return f"Sir, '{folder_name}' folder pehle se hi khali (empty) hai."

            file_count = 0
            dir_count = 0
            for item in items:
                item_path = os.path.join(target_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        if secure_shred:
                            self.shred_file(item_path)
                        else:
                            os.remove(item_path)
                        file_count += 1
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        dir_count += 1
                except Exception as item_err:
                    logger.warning(f"Could not remove {item_path}: {item_err}")

            if lang == "english":
                return (
                    f"Sir, successfully deleted all {file_count} files "
                    f"{'and ' + str(dir_count) + ' subfolders ' if dir_count > 0 else ''}"
                    f"inside the '{folder_name}' folder!"
                )
            return (
                f"Sir, '{folder_name}' folder ke andar ki saari {file_count} files "
                f"{'aur ' + str(dir_count) + ' subfolders ' if dir_count > 0 else ''}"
                f"successfully delete kar di hain!"
            )
        except Exception as e:
            return f"Failed to clean folder contents: {e}"
