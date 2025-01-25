import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime
import sys
from typing import Set, Dict
import hashlib
import threading
from static_site_generator_machine import Preprocessor  # importing from your previous script

class BuildEvent:
    """Represents a build event with debouncing support"""
    def __init__(self):
        self.last_trigger = 0
        self.is_building = False
        self.needs_rebuild = False
        self.lock = threading.Lock()

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, source_dir: str, build_dir: str, debounce_seconds: float = 0.5):
        self.source_dir = os.path.abspath(source_dir)
        self.build_dir = os.path.abspath(build_dir)
        self.debounce_seconds = debounce_seconds
        self.build_event = BuildEvent()
        self.file_hashes: Dict[str, str] = {}
        self.preprocessor = Preprocessor()
        
        # Initialize file hashes
        self._update_file_hashes()
        
    def _update_file_hashes(self) -> None:
        """Update the hash of all files in the source directory"""
        new_hashes = {}
        for root, _, files in os.walk(self.source_dir):
            if self.build_dir in root:
                continue
            for file in files:
                if file.endswith('.py'):  # Skip Python files
                    continue
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'rb') as f:
                        content = f.read()
                        new_hashes[filepath] = hashlib.md5(content).hexdigest()
                except Exception as e:
                    print(f"Error hashing file {filepath}: {e}")
        self.file_hashes = new_hashes

    def _has_file_changed(self, filepath: str) -> bool:
        """Check if a file has actually changed by comparing its hash"""
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
                new_hash = hashlib.md5(content).hexdigest()
                old_hash = self.file_hashes.get(filepath)
                return new_hash != old_hash
        except Exception:
            return True  # If we can't read the file, assume it changed

    def _should_ignore(self, filepath: str) -> bool:
        """Check if the file should be ignored"""
        # Ignore build directory and Python files
        return (self.build_dir in filepath or 
                filepath.endswith('.py') or 
                filepath.endswith('.pyc') or
                '__pycache__' in filepath or
                '.git' in filepath)

    def _trigger_build(self) -> None:
        """Trigger a build with debouncing"""
        with self.build_event.lock:
            current_time = time.time()
            
            # If we're currently building, mark for rebuild
            if self.build_event.is_building:
                self.build_event.needs_rebuild = True
                return
            
            # Check if we need to debounce
            if current_time - self.build_event.last_trigger < self.debounce_seconds:
                self.build_event.needs_rebuild = True
                return
            
            self.build_event.is_building = True
            self.build_event.last_trigger = current_time
            
        self._execute_build()

    def _execute_build(self) -> None:
        """Execute the build process"""
        try:
            print("\n" + "="*50)
            print(f"Building site at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print("="*50)
            
            self.preprocessor.generate_site(self.source_dir)
            self._update_file_hashes()
            
            print(f"Build completed successfully!")
            
        except Exception as e:
            print(f"Build failed: {str(e)}")
            
        finally:
            with self.build_event.lock:
                self.build_event.is_building = False
                if self.build_event.needs_rebuild:
                    self.build_event.needs_rebuild = False
                    # Trigger another build if changes occurred during build
                    threading.Thread(target=self._trigger_build).start()

    def on_modified(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
            
        if self._has_file_changed(event.src_path):
            print(f"\nFile changed: {os.path.relpath(event.src_path, self.source_dir)}")
            self._trigger_build()

    def on_created(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
            
        print(f"\nFile created: {os.path.relpath(event.src_path, self.source_dir)}")
        self._trigger_build()

    def on_deleted(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
            
        print(f"\nFile deleted: {os.path.relpath(event.src_path, self.source_dir)}")
        self._trigger_build()

    def on_moved(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
            
        print(f"\nFile moved/renamed: {os.path.relpath(event.src_path, self.source_dir)} -> {os.path.relpath(event.dest_path, self.source_dir)}")
        self._trigger_build()

class SiteWatcher:
    def __init__(self, source_dir: str = ".", build_dir: str = "build"):
        self.source_dir = os.path.abspath(source_dir)
        self.build_dir = os.path.abspath(build_dir)
        self.observer = Observer()
        
    def start(self):
        """Start watching the source directory"""
        event_handler = FileChangeHandler(self.source_dir, self.build_dir)
        self.observer.schedule(event_handler, self.source_dir, recursive=True)
        
        print(f"Site Watcher Started")
        print(f"{'='*50}")
        print(f"Watching directory: {self.source_dir}")
        print(f"Build directory: {self.build_dir}")
        print(f"UTC Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"User: {os.getenv('USER', 'unknown')}")
        print(f"{'='*50}")
        
        # Do initial build
        event_handler._trigger_build()
        
        try:
            self.observer.start()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping watcher...")
            self.observer.stop()
            self.observer.join()
            print("Watcher stopped.")
            
        except Exception as e:
            print(f"Error: {str(e)}")
            self.observer.stop()
            self.observer.join()
            sys.exit(1)

def main():
    watcher = SiteWatcher()
    watcher.start()

if __name__ == "__main__":
    main()