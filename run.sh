#!/bin/bash
# Linux/Mac launcher for Manual Intelligence Engine

echo "================================================"
echo "Manual Intelligence Engine"
echo "================================================"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

# Check if requirements are installed
if ! python3 -m pip check &> /dev/null; then
    echo "Installing/updating dependencies..."
    python3 -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install dependencies"
        exit 1
    fi
fi

# Check for API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo
    echo "WARNING: OPENAI_API_KEY environment variable not set!"
    echo
    echo "Please set your OpenAI API key:"
    echo "  export OPENAI_API_KEY='your-api-key-here'"
    echo
    echo "Or add it to your ~/.bashrc or ~/.zshrc file"
    echo
fi

# Run the application
echo "Starting Manual Intelligence Engine..."
echo
python3 run.py

if [ $? -ne 0 ]; then
    echo
    echo "ERROR: Application failed to start"
    exit 1
fi
