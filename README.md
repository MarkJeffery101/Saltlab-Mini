# Manual Intelligence Engine

A desktop application for analyzing and querying technical manuals using AI-powered embeddings and semantic search.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

> **🔒 SECURITY NOTE**: This repository was repaired to remove a hardcoded API key. If you're using an older version, please see [SECURITY.md](SECURITY.md) for important information about rotating your API key.

> **✨ NEW: Phase 1 Backend Model** - Enhanced with SQLite + FAISS, compliance metadata, emergency procedures, and unit awareness. See [PHASE1_README.md](PHASE1_README.md) for details.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your OpenAI API key
export OPENAI_API_KEY='your-api-key-here'

# 3. Run the application
python run.py
```

## Features

### Core Features
- **Ingest Manuals**: Process and embed technical documents (.txt, .md files)
- **Ask Questions**: Query your manuals with natural language questions
- **Gap Analysis**: Compare standards against operational manuals
- **Manage Manuals**: List, delete, export, and preview ingested manuals

### Phase 1: Enhanced Backend (NEW)
- **SQLite + FAISS Storage**: Fast, scalable database with vector similarity search
- **Document Classification**: Auto-detect document types (manual, standard, legislation, etc.)
- **Topic Identification**: Automatic topic ID generation for cross-document tracking
- **Emergency Procedures**: Auto-detect and tag emergency procedures
- **Unit Awareness**: Extract and track units (meters, bar, psi, etc.)
- **Compliance Metadata**: Track standards, effective dates, review deadlines
- **Audit Logging**: Complete audit trail of all operations
- **Migration Tool**: Easy migration from legacy JSON format

See [PHASE1_README.md](PHASE1_README.md) for complete Phase 1 documentation.

## Prerequisites

- Python 3.8 or higher
- OpenAI API key

## Installation

### Option 1: Run from Source

1. Clone the repository:
```bash
git clone https://github.com/MarkJeffery101/Saltlab-Mini.git
cd Saltlab-Mini
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your OpenAI API key:
   - Set the `OPENAI_API_KEY` environment variable:
     ```bash
     # Linux/Mac
     export OPENAI_API_KEY='your-api-key-here'
     
     # Windows
     set OPENAI_API_KEY=your-api-key-here
     ```

4. Run the GUI application:
```bash
# Easy way (automatic dependency check):
# Linux/Mac:
./run.sh

# Windows:
run.bat

# Or manually:
python run.py
# Or directly:
python manual_gui.py
```

### Option 2: Build Standalone Executable

1. Follow steps 1-3 from Option 1

2. Build the standalone executable:
```bash
python build_standalone.py
```

3. The executable will be created in the `dist` folder:
   - Windows: `ManualIntelligenceEngine.exe`
   - macOS: `ManualIntelligenceEngine`
   - Linux: `ManualIntelligenceEngine`

4. You can distribute this executable without requiring Python installation

## Usage

### GUI Application

#### 1. Ingest Manuals Tab
- Place your `.txt` or `.md` manual files in the `manuals` folder
- Click "Open Folder" to quickly access the manuals directory
- Click "Ingest Manuals" to process all files

#### 2. Ask Questions Tab
- Enter your question in the text field
- Optionally filter by manual name using the "Include" field
- Adjust "Top K" to control how many relevant chunks are retrieved
- Click "Ask Question" to get AI-powered answers

#### 3. Gap Analysis Tab
- Enter the Standard ID and Manual ID
- Configure analysis parameters:
  - **Max Clauses**: Number of standard chunks to analyze
  - **Top N**: Number of manual chunks to compare per standard
  - **Min Similarity**: Threshold for automatic "Not Covered" classification
  - **Start Index**: Skip to a specific clause
- Optionally export results to CSV or HTML
- Click "Run Gap Analysis"

#### 4. Manage Manuals Tab
- **List**: View all ingested manuals and their chunk counts
- **Delete**: Remove a manual from the database (optionally delete the file too)
- **Export**: Export a manual to a single text file

### Command Line Interface

You can also use the command line interface:

```bash
# Ingest manuals
python manual_core.py ingest

# List ingested manuals
python manual_core.py list

# Ask a question
python manual_core.py ask "What are the safety procedures for diving?"

# Show a specific chunk
python manual_core.py show C18

# Preview a manual
python manual_core.py preview --manual-id "Manual - Diving Operations"

# Run gap analysis
python manual_core.py gap --standard-id "Annexe A - Air Diving Operations and Emergency Procedures" \
                          --manual-id "Manual - Diving Operations" \
                          --max-clauses 5 \
                          --out-csv results.csv \
                          --out-html results.html

# Delete a manual
python manual_core.py delete "Manual Name" --delete-file

# Export a manual
python manual_core.py export "Manual Name" --out-path exported.txt

# Phase 1: Enhanced metadata commands
# List document metadata
python manual_core.py list-metadata

# Set document type
python manual_core.py set-doc-type "Manual - Diving Operations" manual

# List all topics
python manual_core.py list-topics

# Show emergency procedures
python manual_core.py list-emergency

# Show compliance information
python manual_core.py show-compliance

# Detect conflicts
python manual_core.py detect-conflicts
```

### Migration from Legacy JSON

If you have an existing `db.json`, migrate to the new SQLite format:

```bash
python migrate_db.py
```

This will preserve your data while adding enhanced metadata and FAISS indexing.

## Configuration

The application uses the following default settings (can be modified in `manual_core.py`):

- **MANUALS_DIR**: `manuals` - Directory for manual files
- **DB_PATH**: `db.json` - Legacy database file (for backward compatibility)
- **SQLITE_DB_PATH**: `manual_data.db` - SQLite database (Phase 1)
- **FAISS_INDEX_PATH**: `embeddings.faiss` - FAISS vector index (Phase 1)
- **REPORTS_DIR**: `reports` - Output directory for reports
- **EMBED_MODEL**: `text-embedding-3-small` - OpenAI embedding model
- **CHAT_MODEL**: `gpt-4o-mini` - OpenAI chat model for Q&A

## Project Structure

```
Saltlab-Mini/
├── manual_core.py          # Core engine (CLI) - REPAIRED
├── manual_gui.py           # Desktop GUI application - NEW
├── run.py                  # Easy launcher script - NEW
├── build_standalone.py     # Build script for executable - NEW
├── requirements.txt        # Python dependencies - NEW
├── README.md              # This file - NEW
├── manuals/               # Place your manual files here
├── db.json                # Embedding database (auto-generated)
└── reports/               # Output directory (auto-generated)
```

## What Was Fixed/Added

This repository has been **repaired and enhanced** with the following changes:

### Security Fixes 🔒
- ✅ **REMOVED hardcoded API key** from source code (see [SECURITY.md](SECURITY.md))
- ✅ **Implemented environment variable** authentication for OpenAI API
- ✅ **Enhanced .gitignore** to prevent accidental credential commits

### Repairs
- ✅ Added missing `requirements.txt` with all dependencies (OpenAI SDK)
- ✅ Fixed OpenAI client initialization to handle missing API keys gracefully
- ✅ Added proper error messages and warnings for missing configuration

### New Features
- ✅ **Desktop GUI Application** - User-friendly interface with tabbed navigation
- ✅ **Standalone Executable Builder** - Create distributable apps with PyInstaller
- ✅ **Comprehensive Documentation** - Full README with examples and troubleshooting
- ✅ **Easy Launcher Scripts** - `run.py`, `run.sh`, `run.bat` with API key validation

The original CLI functionality (`manual_core.py`) remains intact and fully functional.

## How It Works

1. **Ingestion**: Documents are cleaned, chunked by hierarchical headings, and embedded using OpenAI's embedding model
2. **Retrieval**: Questions are embedded and compared to chunk embeddings using cosine similarity
3. **Generation**: Top-K most relevant chunks are passed to GPT-4 to generate answers
4. **Gap Analysis**: Standard requirements are compared against manual content to identify coverage gaps

## Troubleshooting

### "No module named 'openai'"
- Install dependencies: `pip install -r requirements.txt`

### "API key not found"
- Set the `OPENAI_API_KEY` environment variable
- Or create a `.env` file with your API key

### No manuals found
- Place `.txt` or `.md` files in the `manuals` folder
- Make sure the files are readable and contain text

### GUI not opening
- Ensure tkinter is installed (usually comes with Python)
- On Linux: `sudo apt-get install python3-tk`

## License

This project is provided as-is for internal use.

## Support

For issues or questions, please contact the repository maintainer.
