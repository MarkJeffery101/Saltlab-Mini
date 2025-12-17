#!/usr/bin/env python3
"""
Build script to create a standalone executable of the Manual Intelligence Engine
"""

import subprocess
import sys
import os

def install_pyinstaller():
    """Install PyInstaller if not already installed"""
    print("Installing PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

def build_executable():
    """Build the standalone executable"""
    print("Building standalone executable...")
    
    # Ensure manuals directory exists
    manuals_dir = "manuals"
    if not os.path.exists(manuals_dir):
        print(f"Creating {manuals_dir} directory...")
        os.makedirs(manuals_dir, exist_ok=True)
    
    # PyInstaller command
    cmd = [
        "pyinstaller",
        "--name=ManualIntelligenceEngine",
        "--onefile",  # Single executable file
        "--windowed",  # No console window (GUI only)
        "--add-data=manuals:manuals",  # Include manuals folder
        "--hidden-import=tkinter",
        "--hidden-import=openai",
        "manual_gui.py"
    ]
    
    # On Windows, use semicolon for add-data separator
    if sys.platform == "win32":
        cmd[4] = "--add-data=manuals;manuals"
    
    subprocess.check_call(cmd)
    
    print("\n" + "="*60)
    print("Build complete!")
    print("The executable can be found in the 'dist' folder")
    print("="*60)

def main():
    try:
        install_pyinstaller()
        build_executable()
    except subprocess.CalledProcessError as e:
        print(f"Error during build: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
