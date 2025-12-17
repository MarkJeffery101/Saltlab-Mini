#!/usr/bin/env python3
"""
Launcher script for Manual Intelligence Engine

SECURITY NOTE: Never hardcode your API key in this or any other file.
Always use environment variables or secure configuration management.
"""

import sys
import os

def main():
    # Check if OpenAI API key is set
    if not os.environ.get('OPENAI_API_KEY'):
        print("\n" + "="*60)
        print("WARNING: OPENAI_API_KEY environment variable not set!")
        print("="*60)
        print("\nPlease set your OpenAI API key before using this application:")
        print("  - Linux/Mac: export OPENAI_API_KEY='your-key-here'")
        print("  - Windows: set OPENAI_API_KEY=your-key-here")
        print("\n⚠️  NEVER hardcode your API key in source files!")
        print("="*60 + "\n")
        
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)
    
    # Import and run the GUI
    try:
        from manual_gui import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"Error: Could not import required modules: {e}")
        print("Please install dependencies: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
