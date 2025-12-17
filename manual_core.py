# ============================================================
#  manual_core.py  (STABLE BUILD – hierarchy + noise filtering)
#  Compact Manual Intelligence Engine v2 - Phase 1 Enhanced
# ============================================================

import os
import json
import math
import argparse
import csv
import re
import sys
import sqlite3
import pickle
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from openai import OpenAI

# FAISS for vector similarity search
try:
    import faiss
except ImportError:
    faiss = None
    print("Warning: FAISS not installed. Vector search will use fallback method.", file=sys.stderr)

# Initialize OpenAI client
# The API key should be set via OPENAI_API_KEY environment variable
# or in a .env file
try:
    client = OpenAI()
except Exception as e:
    # Client will be None if API key is not set
    # Functions that need it will show appropriate error messages
    client = None
    print(f"Warning: OpenAI client initialization skipped: {e}", file=sys.stderr)

# -----------------------------------------
# CONFIG
# -----------------------------------------
MANUALS_DIR = "manuals"
DB_PATH = "db.json"  # Legacy support
SQLITE_DB_PATH = "manual_data.db"
FAISS_INDEX_PATH = "embeddings.faiss"
REPORTS_DIR = "reports"

EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL  = "gpt-4o-mini"

# -----------------------------------------
# METADATA CONSTANTS - COMPREHENSIVE TAGGING RULESET
# -----------------------------------------

# Document types (backward compatibility)
DOC_TYPES = ["manual", "standard", "legislation", "guidance", "client_spec"]

# Comprehensive tagging ruleset for diving operations manual intelligence
TAGGING_RULESET = {

    # ------------------------------------------------------------------
    # 1) Document-level classification
    # ------------------------------------------------------------------
    "document_types": {
        "manual": [
            "diving operations manual",
            "daughter craft diving manual",
            "procedure",
            "operations manual",
            "tup manual",
        ],
        "standard": [
            "imca",
            "norsok",
            "dmac",
            "iogp",
            "as2299",
            "iso",
            "standard",
        ],
        "guidance": [
            "guidance",
            "recommended practice",
            "code of practice",
        ],
        "legislation": [
            "act",
            "regulation",
            "law",
            "statutory",
        ],
        "client_spec": [
            "client specification",
            "company standard",
            "project specification",
        ],
    },

    # ------------------------------------------------------------------
    # 2) Diving mode / operational context
    # ------------------------------------------------------------------
    "diving_modes": {
        "air": [
            "air diving",
            "surface supplied air",
        ],
        "nitrox": [
            "nitrox",
            "surface supplied nitrox",
            "enriched air",
        ],
        "surdo2": [
            "surface decompression",
            "surdo2",
            "decompression on oxygen",
        ],
        "tup": [
            "transfer under pressure",
            "tup",
        ],
        "saturation": [
            "saturation diving",
            "sat diving",
        ],
        "dp": [
            "dynamic positioning",
            "dp vessel",
        ],
    },

    # ------------------------------------------------------------------
    # 3) Physiology & gas hazards
    # ------------------------------------------------------------------
    "physiology": {
        "oxygen": [
            "oxygen",
            "ppo2",
            "hyperoxia",
            "cns",
            "otu",
            "esot",
        ],
        "carbon_dioxide": [
            "carbon dioxide",
            "co2",
            "hypercapnia",
        ],
        "nitrogen": [
            "nitrogen",
            "nitrogen narcosis",
            "narcosis",
        ],
        "hypoxia": [
            "hypoxia",
            "low oxygen",
        ],
        "barotrauma": [
            "barotrauma",
            "lung overexpansion",
        ],
        "dcs": [
            "decompression sickness",
            "dcs",
            "the bends",
        ],
        "age": [
            "arterial gas embolism",
            "age",
        ],
    },

    # ------------------------------------------------------------------
    # 4) Emergency & abnormal operations
    # ------------------------------------------------------------------
    "emergencies": {
        "bailout": [
            "bailout",
            "emergency gas",
            "loss of primary gas",
        ],
        "medical": [
            "medical emergency",
            "injury",
            "illness",
            "first aid",
            "drabc",
        ],
        "equipment_failure": [
            "equipment failure",
            "system failure",
            "loss of power",
            "malfunction",
        ],
        "abort": [
            "abort",
            "terminate dive",
            "stop work",
        ],
        "weather": [
            "weather abort",
            "environmental conditions",
            "sea state",
        ],
        "rescue": [
            "rescue",
            "diver recovery",
        ],
    },

    # ------------------------------------------------------------------
    # 5) Systems & equipment
    # ------------------------------------------------------------------
    "systems": {
        "chamber": [
            "ddc",
            "deck decompression chamber",
            "chamber",
            "medical lock",
            "inner lock",
            "outer lock",
        ],
        "lars": [
            "lars",
            "launch and recovery system",
        ],
        "umbilical": [
            "umbilical",
            "diver umbilical",
        ],
        "bailout": [
            "bail-out bottle",
            "bailout bottle",
        ],
        "breathing_interface": [
            "bib",
            "helmet",
            "mask",
        ],
        "gas_supply": [
            "compressor",
            "air quad",
            "oxygen bank",
            "gas storage",
        ],
    },

    # ------------------------------------------------------------------
    # 6) Normative / requirement language
    # ------------------------------------------------------------------
    "normative_language": {
        "mandatory": [
            "shall",
            "must",
            "required",
            "mandatory",
        ],
        "recommended": [
            "should",
            "recommended",
        ],
        "prohibited": [
            "shall not",
            "must not",
            "not permitted",
        ],
    },

    # ------------------------------------------------------------------
    # 7) Conflict-sensitive qualifiers
    # ------------------------------------------------------------------
    "conflict_qualifiers": {
        "min_limit": [
            "minimum",
            "at least",
            "not less than",
        ],
        "max_limit": [
            "maximum",
            "no more than",
            "not greater than",
        ],
        "limit": [
            "limit",
            "threshold",
        ],
    },

    # ------------------------------------------------------------------
    # 8) Unit patterns & normalization
    # ------------------------------------------------------------------
    "unit_patterns": {
        r"(\d+(?:\.\d+)?)\s*(m|metres?|meters?)": "meters",
        r"(\d+(?:\.\d+)?)\s*(ft|feet)": "feet",
        r"(\d+(?:\.\d+)?)\s*(bar)": "bar",
        r"(\d+(?:\.\d+)?)\s*(psi)": "psi",
        r"(\d+(?:\.\d+)?)\s*(ata|atm)": "ata",
        r"(\d+(?:\.\d+)?)\s*(l|litres?|liters?)": "litres",
        r"(\d+(?:\.\d+)?)\s*(cf|cu\.?\s*ft)": "cubic_feet",
    },

    # ------------------------------------------------------------------
    # 9) Boilerplate / noise filters (ingestion hygiene)
    # ------------------------------------------------------------------
    "boilerplate_patterns": [
        r"^\s*document\s+no\s*:",
        r"^\s*rev\.?\s*no\s*:",
        r"^\s*date\s+issued\s*:",
        r"^\s*disclaimer\s*:",
        r"^\s*document\s+(owner|originator|approver)\s*:",
        r"^\s*page\s*:\s*\d+\s*of\s*\d+",
    ],
}

# -----------------------------------------
# NOISE / CLEANING
# -----------------------------------------

NOISE_LINE_RE = re.compile(
    r"(?:^|\b)("
    r"procedures|global\s+standard|document\s*no|document\s+no|"
    r"rev\.?\s*no|revision|date\s*issued|issue\s*date|"
    r"document\s+owner|document\s+originator|document\s+approver|"
    r"disclaimer|uncontrolled\s+copy|page\s*:\s*\d+\s*of\s*\d+"
    r")\b",
    re.IGNORECASE,
)

def is_noise_line(line: str) -> bool:
    """
    Returns True if a line is clearly a repeating header/footer/admin line.
    Uses SEARCH (not MATCH) to catch cases where multiple footer fields
    are merged into one long line.
    
    Phase 1.5: Enhanced with TAGGING_RULESET boilerplate patterns.
    """
    s = (line or "").strip()
    if not s:
        return False

    # normalize whitespace to make matching robust
    s_norm = re.sub(r"\s+", " ", s)

    # Check original noise patterns
    if NOISE_LINE_RE.search(s_norm):
        return True
    
    # Phase 1.5: Check boilerplate patterns from TAGGING_RULESET
    if is_boilerplate_line(s):
        return True

    # common repeating name/footer blocks (multiple names on one line)
    # e.g. "Mike Paton   Mike Paton   John Rossier"
    name_line = s_norm.lower()
    if re.fullmatch(r"(mike paton|john rossier)( (mike paton|john rossier))*", name_line):
        return True

    return False


def clean_text_for_chunking(text: str) -> str:
    """
    Light cleanup BEFORE chunking:
    - removes obvious header/footer/noise lines
    - collapses huge blank runs (keeps max 2 blanks)
    """
    lines = (text or "").splitlines()
    out: List[str] = []
    blank_run = 0

    for line in lines:
        s = line.rstrip()

        if is_noise_line(s):
            continue

        if not s.strip():
            blank_run += 1
            if blank_run <= 2:
                out.append("")
            continue

        blank_run = 0
        out.append(s)

    return "\n".join(out).strip()


def strip_noise_lines(text: str) -> str:
    """
    Stronger cleanup used for deciding if a chunk is "real" content.
    Removes repeated headers/footers/names but keeps structure.
    """
    lines = (text or "").splitlines()
    kept: List[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            kept.append("")
            continue
        if is_noise_line(s):
            continue
        kept.append(ln.rstrip())

    out: List[str] = []
    blank = 0
    for ln in kept:
        if not ln.strip():
            blank += 1
            if blank <= 2:
                out.append("")
        else:
            blank = 0
            out.append(ln)

    return "\n".join(out).strip()


def is_toc_like_text(text: str) -> bool:
    """
    Detects TOC/index-ish chunks that you do NOT want embedded.
    """
    if not text:
        return False
    low = text.lower()
    if "table of contents" in low:
        return True

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False

    tocish = 0
    for ln in lines:
        if re.search(r"\.{5,}\s*\d+\s*$", ln):
            tocish += 1

    return (tocish / max(1, len(lines))) >= 0.25


def has_real_content(text: str, min_chars: int = 40) -> bool:
    t = strip_noise_lines(text)
    # remove bullets/symbols and squash whitespace
    t2 = re.sub(r"[\s•xX\-\*]+", " ", t).strip()
    return len(t2) >= min_chars


def drop_bad_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Removes chunks that are blank, TOC-like, or only noise after stripping.
    """
    out: List[Dict[str, Any]] = []
    for r in records:
        t = (r.get("text") or "").strip()
        if not t:
            continue
        if is_toc_like_text(t):
            continue
        if not has_real_content(t, min_chars=40):
            continue
        out.append(r)
    return out

# -----------------------------------------
# Ensure dirs exist
# -----------------------------------------
def ensure_dirs():
    os.makedirs(MANUALS_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

# -----------------------------------------
# Load/save database
# -----------------------------------------
def load_db() -> Dict[str, Any]:
    if not os.path.isfile(DB_PATH):
        return {"chunks": []}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db: Dict[str, Any]):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

# -----------------------------------------
# SQLite Database Layer (Phase 1)
# -----------------------------------------

def init_sqlite_db():
    """Initialize SQLite database with schema."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    
    # Documents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            manual_id TEXT PRIMARY KEY,
            doc_type TEXT,
            compliance_standard TEXT,
            effective_date TEXT,
            superseded_by TEXT,
            mandatory_review_date TEXT,
            file_path TEXT,
            ingested_at TEXT
        )
    ''')
    
    # Chunks table (Phase 1 + Phase 1.5 enhanced)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            manual_id TEXT,
            text TEXT,
            heading TEXT,
            path TEXT,
            heading_num TEXT,
            level INTEGER,
            topic_id TEXT,
            is_emergency_procedure INTEGER DEFAULT 0,
            emergency_category TEXT,
            units TEXT,
            conflict_type TEXT,
            
            -- Phase 1.5: Enhanced tagging
            diving_modes TEXT,           -- JSON array of detected diving modes
            physiology_tags TEXT,        -- JSON array of physiology/gas hazards
            systems_tags TEXT,           -- JSON array of systems/equipment
            normative_language TEXT,     -- mandatory, recommended, or prohibited
            conflict_qualifiers TEXT,    -- JSON array of detected qualifiers (min/max limits)
            
            FOREIGN KEY (manual_id) REFERENCES documents(manual_id)
        )
    ''')
    
    # Topics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS topics (
            topic_id TEXT PRIMARY KEY,
            description TEXT,
            first_seen TEXT
        )
    ''')
    
    # Audit log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user TEXT,
            action TEXT,
            details TEXT
        )
    ''')
    
    # Phase 1.5: Conflict Resolutions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conflict_resolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict_id TEXT UNIQUE,
            chunk1_id TEXT,
            chunk2_id TEXT,
            topic_id TEXT,
            conflict_type TEXT,
            detected_at TEXT,
            
            resolution_status TEXT DEFAULT 'pending',
            resolution_type TEXT,
            resolved_by TEXT,
            resolved_at TEXT,
            resolution_notes TEXT,
            
            detail TEXT,
            context1 TEXT,
            context2 TEXT,
            
            original_unit TEXT,
            converted_unit TEXT,
            conversion_factor REAL,
            
            FOREIGN KEY (chunk1_id) REFERENCES chunks(id),
            FOREIGN KEY (chunk2_id) REFERENCES chunks(id)
        )
    ''')
    
    # Phase 1.5: Approval Workflow table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approval_workflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict_resolution_id INTEGER,
            approval_level INTEGER,
            approver TEXT,
            approval_status TEXT DEFAULT 'pending',
            approved_at TEXT,
            comments TEXT,
            
            FOREIGN KEY (conflict_resolution_id) REFERENCES conflict_resolutions(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get SQLite database connection."""
    return sqlite3.connect(SQLITE_DB_PATH)

def log_audit_event(action: str, details: str, user: str = "system"):
    """Log an audit event."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        timestamp = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO audit_log (timestamp, user, action, details) VALUES (?, ?, ?, ?)",
            (timestamp, user, action, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to log audit event: {e}", file=sys.stderr)

def use_sqlite() -> bool:
    """Check if SQLite database exists and should be used."""
    return os.path.exists(SQLITE_DB_PATH)

# -----------------------------------------
# File → text
# -----------------------------------------
def read_manual_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

# -----------------------------------------
# Embeddings
# -----------------------------------------
def embed_texts(texts: List[str]) -> List[List[float]]:
    if client is None:
        raise RuntimeError("OpenAI client not initialized. Please set OPENAI_API_KEY environment variable.")
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

# -----------------------------------------
# Cosine similarity
# -----------------------------------------
def vnorm(v):
    return math.sqrt(sum(x*x for x in v))

def cosine(a, b):
    na, nb = vnorm(a), vnorm(b)
    if na == 0 or nb == 0:
        return 0.0
    return sum(x*y for x, y in zip(a, b)) / (na * nb)

# -----------------------------------------
# Phase 1 Metadata Helpers
# -----------------------------------------

def generate_topic_id(heading_text: str) -> str:
    """
    Generate stable topic_id from heading text.
    Rules:
    - Lowercase
    - Replace spaces with underscores
    - Remove special characters
    - Keep only alphanumeric and underscores
    - Max 100 chars
    
    Example: "1.5 Bailout Gas Requirements" -> "bailout_gas_requirements"
    """
    if not heading_text:
        return ""
    
    # Remove heading numbers (e.g., "1.5 ", "2.3.4 ")
    text = re.sub(r'^[\d\.]+\s*', '', heading_text)
    
    # Lowercase and replace spaces with underscores
    text = text.lower().replace(' ', '_')
    
    # Remove special characters, keep only alphanumeric and underscores
    text = re.sub(r'[^a-z0-9_]', '', text)
    
    # Collapse multiple underscores
    text = re.sub(r'_+', '_', text)
    
    # Trim underscores from ends
    text = text.strip('_')
    
    # Limit length
    if len(text) > 100:
        text = text[:100].rsplit('_', 1)[0]  # Cut at last word boundary
    
    return text

def detect_emergency_procedure(text: str, heading: str = "") -> Tuple[bool, Optional[str]]:
    """
    Detect if text/heading indicates an emergency procedure.
    Returns: (is_emergency, emergency_category)
    Uses comprehensive TAGGING_RULESET for improved detection.
    """
    combined = (heading + " " + text[:500]).lower()
    
    # Check emergency categories from TAGGING_RULESET
    for category, keywords in TAGGING_RULESET["emergencies"].items():
        for keyword in keywords:
            if keyword.lower() in combined:
                return (True, category)
    
    return (False, None)

def extract_units(text: str) -> List[Dict[str, str]]:
    """
    Extract units from text using regex patterns from TAGGING_RULESET.
    Returns list of dicts with 'value', 'unit', and 'context'.
    """
    units = []
    
    for pattern, unit_name in TAGGING_RULESET["unit_patterns"].items():
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            value = match.group(1)
            # Get context (20 chars before and after)
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            context = text[start:end].strip()
            
            units.append({
                'value': value,
                'unit': unit_name,
                'context': context
            })
    
    return units

def detect_doc_type(filename: str, text: str = "") -> str:
    """
    Auto-detect document type from filename or content using TAGGING_RULESET.
    Returns one of: manual, standard, legislation, guidance, client_spec
    
    Checks in order of specificity to avoid generic matches.
    """
    fname_lower = filename.lower()
    text_sample = text[:1000].lower() if text else ""
    combined = fname_lower + " " + text_sample
    
    # Check document types in order of specificity (most specific first)
    # This prevents generic keywords from matching too early
    priority_order = ["client_spec", "legislation", "standard", "guidance", "manual"]
    
    for doc_type in priority_order:
        if doc_type in TAGGING_RULESET["document_types"]:
            for keyword in TAGGING_RULESET["document_types"][doc_type]:
                if keyword.lower() in combined:
                    return doc_type
    
    # Default
    return 'manual'

# -----------------------------------------
# Phase 1.5: Enhanced Tagging Functions
# -----------------------------------------

def detect_diving_modes(text: str, heading: str = "") -> List[str]:
    """
    Detect diving modes from text and heading using TAGGING_RULESET.
    Returns list of detected modes: air, nitrox, surdo2, tup, saturation, dp
    """
    combined = (heading + " " + text[:1000]).lower()
    detected_modes = []
    
    for mode, keywords in TAGGING_RULESET["diving_modes"].items():
        for keyword in keywords:
            if keyword.lower() in combined:
                if mode not in detected_modes:
                    detected_modes.append(mode)
                break
    
    return detected_modes

def detect_physiology_tags(text: str, heading: str = "") -> List[str]:
    """
    Detect physiology and gas hazard tags using TAGGING_RULESET.
    Returns list of detected tags: oxygen, carbon_dioxide, nitrogen, hypoxia, barotrauma, dcs, age
    """
    combined = (heading + " " + text[:1000]).lower()
    detected_tags = []
    
    for tag, keywords in TAGGING_RULESET["physiology"].items():
        for keyword in keywords:
            if keyword.lower() in combined:
                if tag not in detected_tags:
                    detected_tags.append(tag)
                break
    
    return detected_tags

def detect_systems_tags(text: str, heading: str = "") -> List[str]:
    """
    Detect systems and equipment tags using TAGGING_RULESET.
    Returns list of detected tags: chamber, lars, umbilical, bailout, breathing_interface, gas_supply
    """
    combined = (heading + " " + text[:1000]).lower()
    detected_tags = []
    
    for tag, keywords in TAGGING_RULESET["systems"].items():
        for keyword in keywords:
            if keyword.lower() in combined:
                if tag not in detected_tags:
                    detected_tags.append(tag)
                break
    
    return detected_tags

def detect_normative_language(text: str) -> Optional[str]:
    """
    Detect normative language (requirement strength) using TAGGING_RULESET.
    Returns: 'mandatory', 'recommended', 'prohibited', or None
    
    Priority: prohibited > mandatory > recommended (most restrictive first)
    """
    text_lower = text.lower()
    
    # Check in order of restrictiveness
    for norm_type in ['prohibited', 'mandatory', 'recommended']:
        keywords = TAGGING_RULESET["normative_language"][norm_type]
        for keyword in keywords:
            if keyword.lower() in text_lower:
                return norm_type
    
    return None

def detect_conflict_qualifiers(text: str) -> List[Dict[str, str]]:
    """
    Detect conflict-sensitive qualifiers (min/max limits) using TAGGING_RULESET.
    Returns list of dicts with 'type' and 'context'.
    """
    qualifiers = []
    text_lower = text.lower()
    
    for qualifier_type, keywords in TAGGING_RULESET["conflict_qualifiers"].items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                # Find position and extract context
                idx = text_lower.find(keyword.lower())
                start = max(0, idx - 30)
                end = min(len(text), idx + len(keyword) + 30)
                context = text[start:end].strip()
                
                qualifiers.append({
                    'type': qualifier_type,
                    'keyword': keyword,
                    'context': context
                })
    
    return qualifiers

def is_boilerplate_line(line: str) -> bool:
    """
    Check if a line matches boilerplate patterns from TAGGING_RULESET.
    Used for improved noise filtering during ingestion.
    """
    line_stripped = line.strip()
    if not line_stripped:
        return False
    
    for pattern in TAGGING_RULESET["boilerplate_patterns"]:
        if re.match(pattern, line_stripped, re.IGNORECASE):
            return True
    
    return False

# -----------------------------------------
# Phase 1.5: Unit Conversion System
# -----------------------------------------

# Unit conversion factors
UNIT_CONVERSIONS = {
    # Distance conversions
    ("meters", "feet"): 3.28084,
    ("feet", "meters"): 0.3048,
    
    # Pressure conversions
    ("bar", "psi"): 14.5038,
    ("psi", "bar"): 0.0689476,
    ("bar", "ata"): 1.01972,
    ("ata", "bar"): 0.980665,
    ("psi", "ata"): 0.068046,
    ("ata", "psi"): 14.6959,
    
    # Volume conversions
    ("litres", "cubic_feet"): 0.0353147,
    ("cubic_feet", "litres"): 28.3168,
}

# Conversion tolerances for fuzzy matching
CONVERSION_TOLERANCE = {
    "meters": 0.01,      # 1cm tolerance
    "feet": 0.1,         # ~3cm tolerance
    "bar": 0.1,          # 0.1 bar tolerance
    "psi": 1.0,          # 1 psi tolerance
    "ata": 0.1,          # 0.1 ata tolerance
    "litres": 0.1,       # 0.1L tolerance
    "cubic_feet": 0.01,  # 0.01 cf tolerance
}

def convert_unit(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """
    Convert a value from one unit to another.
    Returns None if conversion not supported.
    """
    if from_unit == to_unit:
        return value
    
    key = (from_unit, to_unit)
    if key in UNIT_CONVERSIONS:
        return value * UNIT_CONVERSIONS[key]
    
    return None

def units_match_within_tolerance(val1: float, unit1: str, val2: float, unit2: str) -> bool:
    """
    Check if two values with different units are equivalent within tolerance.
    Example: 30 meters ≈ 98.4 feet (within 0.1ft tolerance)
    """
    # Convert val1 to unit2
    converted = convert_unit(val1, unit1, unit2)
    if converted is None:
        return False
    
    tolerance = CONVERSION_TOLERANCE.get(unit2, 0)
    return abs(converted - val2) <= tolerance

# -----------------------------------------
# Phase 1 Conflict Detection (Foundation)
# -----------------------------------------

def extract_numeric_values(text: str) -> List[Dict[str, Any]]:
    """
    Extract numeric values with context for conflict detection.
    Returns list of dicts with 'value', 'unit', 'context'.
    """
    numerics = []
    
    # Find numbers with optional units
    pattern = r'(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?'
    matches = re.finditer(pattern, text)
    
    for match in matches:
        value = match.group(1)
        unit = match.group(2) if match.group(2) else None
        
        # Get context
        start = max(0, match.start() - 30)
        end = min(len(text), match.end() + 30)
        context = text[start:end].strip()
        
        numerics.append({
            'value': float(value) if '.' in value else int(value),
            'unit': unit,
            'context': context
        })
    
    return numerics

def detect_conflicts(chunks: List[Dict[str, Any]], topic_id: str) -> List[Dict[str, Any]]:
    """
    Detect potential conflicts for chunks with the same topic_id.
    Returns list of conflicts found.
    """
    conflicts = []
    
    # Filter chunks with matching topic_id
    topic_chunks = [c for c in chunks if c.get('topic_id') == topic_id]
    
    if len(topic_chunks) < 2:
        return conflicts
    
    # Check for numeric conflicts
    for i, chunk1 in enumerate(topic_chunks):
        text1 = chunk1.get('text', '')
        nums1 = extract_numeric_values(text1)
        units1 = chunk1.get('units', [])
        
        for chunk2 in topic_chunks[i+1:]:
            text2 = chunk2.get('text', '')
            nums2 = extract_numeric_values(text2)
            units2 = chunk2.get('units', [])
            
            # Check for different numeric values
            if nums1 and nums2:
                # Simple heuristic: if same unit but different values, flag
                for n1 in nums1:
                    for n2 in nums2:
                        if n1['unit'] == n2['unit'] and n1['value'] != n2['value']:
                            conflicts.append({
                                'type': 'numeric',
                                'topic_id': topic_id,
                                'chunk1_id': chunk1.get('id'),
                                'chunk2_id': chunk2.get('id'),
                                'detail': f"Different values for {n1['unit']}: {n1['value']} vs {n2['value']}",
                                'context1': n1['context'],
                                'context2': n2['context']
                            })
            
            # Check for unit mismatches
            if units1 and units2:
                units1_set = {(u['unit'], u['value']) for u in units1 if isinstance(u, dict)}
                units2_set = {(u['unit'], u['value']) for u in units2 if isinstance(u, dict)}
                
                # Check if same measurement type but different units
                units1_types = {u['unit'] for u in units1 if isinstance(u, dict)}
                units2_types = {u['unit'] for u in units2 if isinstance(u, dict)}
                
                # Example: meters vs feet for same topic
                distance_units = {'meters', 'feet'}
                pressure_units = {'bar', 'psi'}
                
                # Check distance units
                units1_distance = units1_types & distance_units
                units2_distance = units2_types & distance_units
                if units1_distance and units2_distance and units1_distance != units2_distance:
                    conflicts.append({
                        'type': 'unit_mismatch',
                        'topic_id': topic_id,
                        'chunk1_id': chunk1.get('id'),
                        'chunk2_id': chunk2.get('id'),
                        'detail': f"Different distance units: {units1_distance} vs {units2_distance}",
                    })
                
                # Check pressure units
                units1_pressure = units1_types & pressure_units
                units2_pressure = units2_types & pressure_units
                if units1_pressure and units2_pressure and units1_pressure != units2_pressure:
                    conflicts.append({
                        'type': 'unit_mismatch',
                        'topic_id': topic_id,
                        'chunk1_id': chunk1.get('id'),
                        'chunk2_id': chunk2.get('id'),
                        'detail': f"Different pressure units: {units1_pressure} vs {units2_pressure}",
                    })
    
    return conflicts

def flag_conflicts_in_db(chunks: List[Dict[str, Any]]):
    """
    Scan for conflicts and flag them in the database.
    This is a foundation for Phase 1.5 conflict resolution.
    """
    if not use_sqlite():
        return
    
    # Get unique topic_ids
    topic_ids = set(c.get('topic_id') for c in chunks if c.get('topic_id'))
    
    total_conflicts = 0
    
    for topic_id in topic_ids:
        conflicts = detect_conflicts(chunks, topic_id)
        
        if conflicts:
            # Store conflicts in database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            for conflict in conflicts:
                # Update both chunks with conflict flag
                for chunk_id in [conflict.get('chunk1_id'), conflict.get('chunk2_id')]:
                    if chunk_id:
                        cursor.execute(
                            'UPDATE chunks SET conflict_type = ? WHERE id = ?',
                            (conflict['type'], chunk_id)
                        )
                
                # Log conflict detection
                log_audit_event(
                    'conflict_detected',
                    f"{conflict['type']} conflict in topic {topic_id}: {conflict['detail']}"
                )
            
            conn.commit()
            conn.close()
            
            total_conflicts += len(conflicts)
    
    return total_conflicts

# -----------------------------------------
# Phase 1.5: Conflict Resolution Functions
# -----------------------------------------

def create_conflict_resolution(
    chunk1_id: str,
    chunk2_id: str,
    topic_id: str,
    conflict_type: str,
    detail: str,
    context1: str = "",
    context2: str = ""
) -> str:
    """
    Create a new conflict resolution entry in the database.
    Returns: conflict_id (e.g., "CONF_001")
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Generate unique conflict ID
    cursor.execute("SELECT COUNT(*) FROM conflict_resolutions")
    count = cursor.fetchone()[0]
    conflict_id = f"CONF_{count+1:03d}"
    
    cursor.execute('''
        INSERT INTO conflict_resolutions (
            conflict_id, chunk1_id, chunk2_id, topic_id, conflict_type,
            detected_at, resolution_status, detail, context1, context2
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
    ''', (
        conflict_id, chunk1_id, chunk2_id, topic_id, conflict_type,
        datetime.utcnow().isoformat(), detail, context1, context2
    ))
    
    conn.commit()
    conn.close()
    
    # Log audit event
    log_audit_event('conflict_created', f"Created {conflict_id}: {conflict_type} in {topic_id}")
    
    return conflict_id

def resolve_conflict(
    conflict_id: str,
    resolution_type: str,
    resolved_by: str,
    resolution_notes: str,
    **kwargs
) -> bool:
    """
    Resolve a conflict with the specified resolution type.
    
    Args:
        conflict_id: Unique conflict identifier
        resolution_type: accept_chunk1, accept_chunk2, merge, dismiss, convert_units, manual_override
        resolved_by: Username of resolver
        resolution_notes: Explanation of resolution
        **kwargs: Additional resolution-specific parameters
    
    Returns: True if resolution successful
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify conflict exists and is pending
    cursor.execute(
        "SELECT resolution_status FROM conflict_resolutions WHERE conflict_id = ?",
        (conflict_id,)
    )
    row = cursor.fetchone()
    
    if not row:
        print(f"Error: Conflict {conflict_id} not found")
        conn.close()
        return False
    
    if row[0] != 'pending':
        print(f"Error: Conflict {conflict_id} already {row[0]}")
        conn.close()
        return False
    
    # Apply resolution type-specific logic
    if resolution_type == 'convert_units':
        # Apply unit conversion
        original_unit = kwargs.get('original_unit')
        converted_unit = kwargs.get('converted_unit')
        conversion_factor = UNIT_CONVERSIONS.get((original_unit, converted_unit))
        
        cursor.execute('''
            UPDATE conflict_resolutions
            SET resolution_status = 'resolved',
                resolution_type = ?,
                resolved_by = ?,
                resolved_at = ?,
                resolution_notes = ?,
                original_unit = ?,
                converted_unit = ?,
                conversion_factor = ?
            WHERE conflict_id = ?
        ''', (
            resolution_type, resolved_by, datetime.utcnow().isoformat(),
            resolution_notes, original_unit, converted_unit, conversion_factor,
            conflict_id
        ))
    else:
        # Standard resolution
        cursor.execute('''
            UPDATE conflict_resolutions
            SET resolution_status = 'resolved',
                resolution_type = ?,
                resolved_by = ?,
                resolved_at = ?,
                resolution_notes = ?
            WHERE conflict_id = ?
        ''', (resolution_type, resolved_by, datetime.utcnow().isoformat(), 
              resolution_notes, conflict_id))
    
    conn.commit()
    conn.close()
    
    # Log audit event
    log_audit_event(
        'conflict_resolved',
        f"{conflict_id} resolved as {resolution_type} by {resolved_by}"
    )
    
    return True

def request_approval(
    conflict_id: str,
    approval_level: int,
    approver: str
) -> bool:
    """
    Request approval for a conflict resolution.
    
    Args:
        conflict_id: Unique conflict identifier
        approval_level: 1=supervisor, 2=manager, 3=compliance_officer
        approver: Username of approver
    
    Returns: True if request created successfully
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get conflict_resolution_id
    cursor.execute(
        "SELECT id, resolution_status FROM conflict_resolutions WHERE conflict_id = ?",
        (conflict_id,)
    )
    row = cursor.fetchone()
    
    if not row:
        print(f"Error: Conflict {conflict_id} not found")
        conn.close()
        return False
    
    resolution_id, status = row
    
    if status != 'resolved':
        print(f"Error: Conflict must be resolved before requesting approval")
        conn.close()
        return False
    
    # Create approval request
    cursor.execute('''
        INSERT INTO approval_workflow (
            conflict_resolution_id, approval_level, approver,
            approval_status
        ) VALUES (?, ?, ?, 'pending')
    ''', (resolution_id, approval_level, approver))
    
    conn.commit()
    conn.close()
    
    # Log audit event
    log_audit_event(
        'approval_requested',
        f"Approval requested for {conflict_id} from {approver} (level {approval_level})"
    )
    
    return True

def approve_resolution(conflict_id: str, approver: str, comments: str = "") -> bool:
    """Approve a conflict resolution."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get resolution_id
    cursor.execute(
        "SELECT id FROM conflict_resolutions WHERE conflict_id = ?",
        (conflict_id,)
    )
    row = cursor.fetchone()
    if not row:
        print(f"Error: Conflict {conflict_id} not found")
        conn.close()
        return False
    
    resolution_id = row[0]
    
    # Update approval status
    cursor.execute('''
        UPDATE approval_workflow
        SET approval_status = 'approved',
            approved_at = ?,
            comments = ?
        WHERE conflict_resolution_id = ? AND approver = ? AND approval_status = 'pending'
    ''', (datetime.utcnow().isoformat(), comments, resolution_id, approver))
    
    if cursor.rowcount == 0:
        print(f"Error: No pending approval found for {approver}")
        conn.close()
        return False
    
    conn.commit()
    conn.close()
    
    log_audit_event('conflict_approved', f"{conflict_id} approved by {approver}")
    return True

def reject_resolution(conflict_id: str, approver: str, comments: str = "") -> bool:
    """Reject a conflict resolution."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get resolution_id
    cursor.execute(
        "SELECT id FROM conflict_resolutions WHERE conflict_id = ?",
        (conflict_id,)
    )
    row = cursor.fetchone()
    if not row:
        print(f"Error: Conflict {conflict_id} not found")
        conn.close()
        return False
    
    resolution_id = row[0]
    
    # Update approval status
    cursor.execute('''
        UPDATE approval_workflow
        SET approval_status = 'rejected',
            approved_at = ?,
            comments = ?
        WHERE conflict_resolution_id = ? AND approver = ? AND approval_status = 'pending'
    ''', (datetime.utcnow().isoformat(), comments, resolution_id, approver))
    
    if cursor.rowcount == 0:
        print(f"Error: No pending approval found for {approver}")
        conn.close()
        return False
    
    conn.commit()
    conn.close()
    
    log_audit_event('conflict_rejected', f"{conflict_id} rejected by {approver}")
    return True

# -----------------------------------------
# Heading + hierarchy chunking
# -----------------------------------------

def is_tableish(line: str) -> bool:
    t = (line or "").strip()
    if not t:
        return False

    # TOC dotted leaders are NOT tables
    if re.search(r"\.{5,}\s*\d+\s*$", t):
        return False

    # IMPORTANT: do NOT treat headings as tables just because of spacing
    if re.match(r"^\d+(\.\d+)*\s+[A-Za-z]", t):
        return False

    if "|" in t:
        return True

    # require multiple column gaps
    if len(re.findall(r"\S\s{3,}\S", t)) >= 2:
        return True

    # mostly numeric rows
    if len(re.findall(r"\b\d+(\.\d+)?\b", t)) >= 3 and not re.search(r"[A-Za-z]", t):
        return True

    return False


def is_heading_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if len(s) < 3 or len(s) > 140:
        return False

    # TOC dotted-leader lines are NOT headings
    if re.search(r"\.{5,}\s*\d+\s*$", s):
        return False

    # hierarchical numbered headings
    if re.match(r"^\d+(\.\d+)+\s+\S", s):
        return True

    # ALL CAPS-ish headings
    letters = [c for c in s if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio >= 0.75 and not s.endswith("."):
            return True

    # "1 INTRODUCTION" style
    m = re.match(r"^(\d+)\s+(.*)$", s)
    if m:
        rest = m.group(2).strip()
        if not rest:
            return False
        if re.search(r"\s{3,}", line):  # table/list row
            return False
        if rest.endswith(".") or re.search(r"[,:;]", rest):
            return False
        if any(c.isalpha() for c in rest):
            return True

    return False


def parse_heading(line: str) -> Optional[Tuple[str, str]]:
    """
    Returns (num, title) if line looks like a numbered heading.
    Key rule: title MUST contain at least one letter
    -> prevents "1 5" / "1 10" being treated as headings.
    """
    s = (line or "").strip()
    m = re.match(r"^(\d+(?:\.\d+)*)\s+(.*\S)\s*$", s)
    if not m:
        return None
    num = m.group(1)
    title = m.group(2).strip()
    if not re.search(r"[A-Za-z]", title):
        return None
    return num, title


def heading_level(num: str) -> int:
    return num.count(".") + 1


def heading_hierarchy_chunks(text: str, max_chars: int = 1400) -> List[Dict[str, Any]]:
    lines = text.splitlines()

    chunks: List[Dict[str, Any]] = []
    current_lines: List[str] = []
    current_len = 0

    stack: List[tuple[str, str]] = []
    current_heading = ""
    seen_heading = False

    def stack_path() -> str:
        return " > ".join(f"{n} {t}".strip() for n, t in stack)

    def flush():
        nonlocal current_lines, current_len
        if current_lines:
            body = "\n".join(current_lines).strip()
            if body:
                # Generate topic_id from current heading
                topic_id = generate_topic_id(current_heading)
                
                # Detect emergency procedures
                is_emergency, emergency_cat = detect_emergency_procedure(body, current_heading)
                
                # Extract units
                units = extract_units(body)
                
                # Phase 1.5: Enhanced tagging
                diving_modes = detect_diving_modes(body, current_heading)
                physiology_tags = detect_physiology_tags(body, current_heading)
                systems_tags = detect_systems_tags(body, current_heading)
                normative_language = detect_normative_language(body)
                conflict_qualifiers = detect_conflict_qualifiers(body)
                
                chunks.append({
                    "path": stack_path(), 
                    "heading": current_heading, 
                    "text": body,
                    "topic_id": topic_id,
                    "is_emergency_procedure": is_emergency,
                    "emergency_category": emergency_cat,
                    "units": units,
                    # Phase 1.5 additions
                    "diving_modes": diving_modes,
                    "physiology_tags": physiology_tags,
                    "systems_tags": systems_tags,
                    "normative_language": normative_language,
                    "conflict_qualifiers": conflict_qualifiers,
                })
        current_lines = []
        current_len = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if "table of contents" in stripped.lower():
            continue
        if re.search(r"\.{5,}\s*\d+\s*$", stripped):
            continue

        is_head = is_heading_line(line) and not is_tableish(line)
        parsed = parse_heading(stripped) if is_head else None

        if parsed:
            num, title = parsed
            level = heading_level(num)

            if not seen_heading:
                seen_heading = True
            else:
                flush()

            while stack and heading_level(stack[-1][0]) >= level:
                stack.pop()

            stack.append((num, title))
            current_heading = f"{num} {title}".strip()

            # KEY: do NOT include the heading line in chunk text
            continue

        if not seen_heading:
            continue

        current_lines.append(line.rstrip())
        current_len += len(line) + 1

        if current_len >= max_chars:
            flush()

    flush()
    return chunks






def chunk_records(text: str, max_chars: int = 1400, use_hierarchy: bool = True) -> List[Dict[str, Any]]:
    if use_hierarchy:
        recs = heading_hierarchy_chunks(text, max_chars=max_chars)
        out: List[Dict[str, Any]] = []
        for r in recs:
            heading = (r.get("heading") or "").strip()
            num = ""
            lvl = 0
            p = parse_heading(heading)
            if p:
                num, _t = p
                lvl = heading_level(num)

            out.append({
                "text": r.get("text", ""),
                "heading": heading,
                "path": (r.get("path") or "").strip(),
                "heading_num": num,
                "level": lvl,
                "topic_id": r.get("topic_id", ""),
                "is_emergency_procedure": r.get("is_emergency_procedure", False),
                "emergency_category": r.get("emergency_category"),
                "units": r.get("units", []),
                # Phase 1.5 additions
                "diving_modes": r.get("diving_modes", []),
                "physiology_tags": r.get("physiology_tags", []),
                "systems_tags": r.get("systems_tags", []),
                "normative_language": r.get("normative_language"),
                "conflict_qualifiers": r.get("conflict_qualifiers", []),
            })
        return out

    # (not used in your case, but kept safe)
    return [{"text": t} for t in (text or "").split("\n\n") if t.strip()]

# -----------------------------------------
# Delete / export / list / show
# -----------------------------------------
def delete_manual(manual_id: str, delete_file: bool = False) -> None:
    db = load_db()
    chunks = db.get("chunks", [])

    before = len(chunks)
    remaining = [c for c in chunks if c["manual_id"] != manual_id]
    removed = before - len(remaining)

    if removed == 0:
        print(f"No chunks found for manual_id='{manual_id}'. Nothing deleted.")
        return

    db["chunks"] = remaining
    save_db(db)

    print(f"Removed {removed} chunks for manual_id='{manual_id}'.")
    print(f"DB now has {len(remaining)} chunks total.")

    if delete_file:
        candidates = [
            os.path.join(MANUALS_DIR, manual_id + ".txt"),
            os.path.join(MANUALS_DIR, manual_id + ".md"),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"Also deleted file: {path}")
                except OSError as e:
                    print(f"Could not delete file {path}: {e}")


def export_manual(manual_id: str, out_path: Optional[str] = None) -> None:
    db = load_db()
    chunks = [c for c in db.get("chunks", []) if c["manual_id"] == manual_id]
    if not chunks:
        print(f"No chunks found for manual_id='{manual_id}'. Nothing to export.")
        return

    if out_path is None:
        safe_name = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in manual_id)
        out_path = f"{safe_name}_export.txt"

    text = "\n\n".join(c["text"] for c in chunks)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"Exported {len(chunks)} chunks for manual_id='{manual_id}'")
    print(f"Written to: {out_path}")


def list_manuals() -> None:
    db = load_db()
    chunks = db.get("chunks", [])
    if not chunks:
        print("Database is empty. Run 'ingest' first.")
        return

    counts: Dict[str, int] = {}
    for rec in chunks:
        counts[rec["manual_id"]] = counts.get(rec["manual_id"], 0) + 1

    print("\nManuals:\n")
    for mid, count in sorted(counts.items(), key=lambda x: x[0].lower()):
        print(f" • {mid}: {count} chunks")
    print(f"\nTotal: {len(chunks)}")


def show_chunk(chunk_id: str) -> None:
    db = load_db()
    chunks = db.get("chunks", [])
    for rec in chunks:
        if rec["id"] == chunk_id:
            print(f"\nmanual_id: {rec['manual_id']}")
            print(f"chunk_id : {rec['id']}")
            print(f"heading : {rec.get('heading','')}")
            print(f"path    : {rec.get('path','')}")
            print("\n---------- TEXT ----------\n")
            print(rec["text"])
            print("\n--------------------------\n")
            return
    print(f"Chunk with id '{chunk_id}' not found.")


# -----------------------------------------
# INGEST (Phase 1 Enhanced)
# -----------------------------------------
def ingest(use_hierarchy: bool = True, max_chars: int = 1400, doc_type: Optional[str] = None):
    """
    Ingest manuals with enhanced metadata support.
    Phase-1 clean behavior:
      • Manual-scoped chunk IDs
      • Re-ingest replaces previous version cleanly
    """

    ensure_dirs()

    # Initialize SQLite if not exists
    if not os.path.exists(SQLITE_DB_PATH):
        print("Initializing SQLite database...")
        init_sqlite_db()

    use_sqlite_db = use_sqlite()

    # Legacy JSON DB (kept for now)
    db = {"chunks": []}

    files = [f for f in os.listdir(MANUALS_DIR) if f.lower().endswith((".txt", ".md"))]
    if not files:
        print("No .txt/.md files inside /manuals.")
        return

    print("FILES FOUND:")
    for f in files:
        print(" •", f)

    all_embeddings = []
    all_chunk_ids = []

    for fname in files:
        manual_id = os.path.splitext(fname)[0]
        path = os.path.join(MANUALS_DIR, fname)

        text = read_manual_file(path)
        detected_doc_type = doc_type or detect_doc_type(fname, text)
        text = clean_text_for_chunking(text)

        records = chunk_records(text, max_chars=max_chars, use_hierarchy=use_hierarchy)
        records = drop_bad_records(records)

        print(f"[{manual_id}] → {len(records)} chunks (doc_type: {detected_doc_type})")

        # -----------------------------
        # RE-INGEST BEHAVIOR (SAFE)
        # -----------------------------
        if use_sqlite_db:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chunks WHERE manual_id = ?", (manual_id,))
            conn.commit()
            conn.close()

        # Manual-scoped chunk counter
        local_cid = 0

        # Store document metadata
        if use_sqlite_db:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT OR REPLACE INTO documents
                (manual_id, doc_type, file_path, ingested_at)
                VALUES (?, ?, ?, ?)
                ''',
                (manual_id, detected_doc_type, path, datetime.utcnow().isoformat())
            )
            conn.commit()
            conn.close()

        batch_size = 16
        for i in range(0, len(records), batch_size):
            subrecs = records[i:i + batch_size]
            subtexts = [r["text"] for r in subrecs]
            embs = embed_texts(subtexts)

            for r, emb in zip(subrecs, embs):
                chunk_id = f"{manual_id}::C{local_cid}"

                if use_sqlite_db:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        INSERT INTO chunks
                        (id, manual_id, text, heading, path, heading_num, level,
                         topic_id, is_emergency_procedure, emergency_category, units,
                         diving_modes, physiology_tags, systems_tags,
                         normative_language, conflict_qualifiers)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            chunk_id,
                            manual_id,
                            r["text"],
                            r.get("heading", ""),
                            r.get("path", ""),
                            r.get("heading_num", ""),
                            r.get("level", 0),
                            r.get("topic_id", ""),
                            1 if r.get("is_emergency_procedure") else 0,
                            r.get("emergency_category"),
                            json.dumps(r.get("units", [])),
                            json.dumps(r.get("diving_modes", [])),
                            json.dumps(r.get("physiology_tags", [])),
                            json.dumps(r.get("systems_tags", [])),
                            r.get("normative_language"),
                            json.dumps(r.get("conflict_qualifiers", [])),
                        )
                    )
                    conn.commit()
                    conn.close()

                db["chunks"].append({
                    "id": chunk_id,
                    "manual_id": manual_id,
                    "text": r["text"],
                    "embedding": emb,
                    "heading": r.get("heading", ""),
                    "path": r.get("path", ""),
                })

                all_embeddings.append(emb)
                all_chunk_ids.append(chunk_id)

                local_cid += 1

    if faiss and all_embeddings:
        print("Building FAISS index...")
        embeddings_array = np.array(all_embeddings, dtype="float32")
        faiss.normalize_L2(embeddings_array)
        index = faiss.IndexFlatIP(embeddings_array.shape[1])
        index.add(embeddings_array)
        faiss.write_index(index, FAISS_INDEX_PATH)
        with open(FAISS_INDEX_PATH + ".ids", "w") as f:
            json.dump(all_chunk_ids, f)

    save_db(db)
    print(f"\nIngestion complete. Total chunks: {len(db['chunks'])}")



# ============================================================
# ASK (Q&A retrieval)
# ============================================================
def ask(question: str, include: List[str] = None, top_k: int = 12):
    db = load_db()
    chunks = db.get("chunks", [])
    if not chunks:
        print("DB empty. Run: python manual_core.py ingest")
        return

    include = include or []
    q_emb = embed_texts([question])[0]

    scored = []
    for r in chunks:
        if include and not any(x.lower() in r["manual_id"].lower() for x in include):
            continue
        sim = cosine(q_emb, r["embedding"])
        scored.append((sim, r))

    scored.sort(reverse=True, key=lambda x: x[0])
    top = scored[:top_k]

    context = ""
    for i, (sim, r) in enumerate(top, 1):
        extras = []
        if r.get("heading"):
            extras.append(r["heading"])
        if r.get("path"):
            extras.append(r["path"])
        extra_txt = (" | " + " | ".join(extras)) if extras else ""
        context += (
            f"[Source {i} | {r['manual_id']} | {r['id']}{extra_txt}] (sim {sim:.3f})\n"
            f"{r['text']}\n\n"
        )

    system = (
        "You are a strict technical assistant. Use ONLY the given sources. "
        "If the answer is not explicitly in the text, say so."
    )
    user = f"QUESTION:\n{question}\n\nSOURCES:\n{context}\n\nAnswer strictly from sources."

    if client is None:
        raise RuntimeError("OpenAI client not initialized. Please set OPENAI_API_KEY environment variable.")
    
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.1
    )

    print("\n===== ANSWER =====\n")
    print(resp.choices[0].message.content)

    print("\n===== SOURCES USED =====\n")
    for i, (sim, r) in enumerate(top, 1):
        print(f"{i}. {r['manual_id']} | {r['id']} | sim={sim:.3f}")


def preview_manual(manual_id: str, start_index: int = 0, limit: int = 10) -> None:
    db = load_db()
    chunks = [c for c in db.get("chunks", []) if c["manual_id"] == manual_id]
    if not chunks:
        print(f"No chunks found for manual_id='{manual_id}'.")
        return

    total = len(chunks)
    start_index = max(0, start_index)
    end_index = min(start_index + limit, total)

    print(f"\nPreviewing manual_id='{manual_id}' chunks {start_index} to {end_index-1} of {total}:\n")
    for i in range(start_index, end_index):
        rec = chunks[i]
        txt = rec["text"].replace("\n", " ")
        preview = txt[:200] + ("..." if len(txt) > 200 else "")
        print(f"[{i}] chunk_id={rec['id']} heading={rec.get('heading','')}")
        print(f"     {preview}\n")


# ============================================================
# GAP ENGINE v2
# ============================================================
def classify_severity(coverage: str, similarity: float) -> str:
    if coverage == "Covered":
        return "None"
    if coverage == "Partially Covered":
        return "Medium"
    if coverage == "Not Covered":
        return "Critical" if similarity < 0.25 else "High"
    return "Unknown"


def analyze_gap(std_text: str, manual_context: str, standard_id: str, manual_id: str) -> str:
    system = (
        "You are performing a strict gap analysis between a STANDARD and an OPERATIONAL MANUAL. "
        "Classify as: Covered / Partially Covered / Not Covered. "
        "Be conservative. Do NOT assume coverage unless explicit."
    )
    user = (
        f"STANDARD ({standard_id}):\n{std_text}\n\n"
        f"MANUAL ({manual_id}):\n{manual_context}\n\n"
        "TASK:\n"
        "1. Summarise the requirement in one line.\n"
        "2. Classify coverage.\n"
        "3. Explain briefly.\n"
        "4. State which manual sources were used.\n"
    )

    if client is None:
        raise RuntimeError("OpenAI client not initialized. Please set OPENAI_API_KEY environment variable.")
    
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.1
    )
    return resp.choices[0].message.content


def gap(standard_id: str, manual_id: str, start_index=0, max_clauses=10,
        top_n=5, min_sim=0.40, out_csv=None, out_html=None):

    db = load_db()
    chunks = db.get("chunks", [])

    std_chunks = [c for c in chunks if c["manual_id"] == standard_id]
    man_chunks = [c for c in chunks if c["manual_id"] == manual_id]

    if not std_chunks:
        print("No standard chunks found.")
        return
    if not man_chunks:
        print("No manual chunks found.")
        return

    std_chunks = std_chunks[start_index:start_index + max_clauses]
    results = []

    for idx, std in enumerate(std_chunks, 1):
        scored = []
        for m in man_chunks:
            sim = cosine(std["embedding"], m["embedding"])
            scored.append((sim, m))
        scored.sort(reverse=True, key=lambda x: x[0])
        top = scored[:top_n]
        best_sim = top[0][0] if top else 0

        print("\n" + "="*72)
        print(f"STANDARD CHUNK {idx} | {std['id']} | best_sim={best_sim:.3f}")
        print("="*72)
        print(std["text"][:300] + "...\n")

        if best_sim < min_sim:
            coverage = "Not Covered"
            severity = classify_severity(coverage, best_sim)
            reason = f"No manual excerpts reached similarity ≥ {min_sim}. Best similarity = {best_sim:.3f}."
            results.append({
                "standard_chunk": std["id"],
                "standard_preview": std["text"][:200],
                "coverage": coverage,
                "severity": severity,
                "reason": reason,
                "manual_chunks": ""
            })
            print("AUTO CLASSIFIED: Not Covered")
            continue

        ctx = ""
        for i, (sim, m) in enumerate(top, 1):
            ctx += f"[{i} | {m['id']} | sim={sim:.3f}]\n{m['text']}\n\n"

        answer = analyze_gap(std["text"], ctx, standard_id, manual_id)
        coverage = (
            "Partially Covered" if "Partially" in answer
            else "Covered" if "Covered" in answer
            else "Not Covered"
        )
        severity = classify_severity(coverage, best_sim)

        results.append({
            "standard_chunk": std["id"],
            "standard_preview": std["text"][:200],
            "coverage": coverage,
            "severity": severity,
            "reason": answer,
            "manual_chunks": ";".join([m["id"] for _, m in top])
        })

        print(answer)

    if out_csv and results:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=results[0].keys())
            w.writeheader()
            for r in results:
                w.writerow(r)
        print(f"\nCSV written → {out_csv}")

    if out_html and results:
        html = "<html><body><h1>Gap Report</h1>"
        for r in results:
            html += (
                f"<h2>{r['standard_chunk']} — {r['coverage']} (Severity: {r['severity']})</h2>"
                f"<p><b>Requirement:</b> {r['standard_preview']}</p>"
                f"<p><b>Analysis:</b> {r['reason']}</p><hr>"
            )
        html += "</body></html>"
        with open(out_html, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML written → {out_html}")

# ============================================================
# Phase 1 CLI Commands
# ============================================================

def list_metadata():
    """List all documents with their metadata."""
    if not use_sqlite():
        print("SQLite database not found. Please run 'ingest' first.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT manual_id, doc_type, compliance_standard, effective_date, 
               superseded_by, mandatory_review_date, ingested_at
        FROM documents
        ORDER BY manual_id
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No documents found.")
        return
    
    print("\n" + "="*80)
    print("DOCUMENT METADATA")
    print("="*80)
    
    for row in rows:
        manual_id, doc_type, compliance_std, eff_date, superseded, review_date, ingested = row
        print(f"\nManual ID: {manual_id}")
        print(f"  Doc Type: {doc_type or 'N/A'}")
        print(f"  Compliance Standard: {compliance_std or 'N/A'}")
        print(f"  Effective Date: {eff_date or 'N/A'}")
        print(f"  Superseded By: {superseded or 'N/A'}")
        print(f"  Mandatory Review Date: {review_date or 'N/A'}")
        print(f"  Ingested At: {ingested or 'N/A'}")

def set_doc_type_cmd(manual_id: str, doc_type: str):
    """Update doc_type for a manual."""
    if doc_type not in DOC_TYPES:
        print(f"Error: Invalid doc_type '{doc_type}'. Must be one of: {', '.join(DOC_TYPES)}")
        return
    
    if not use_sqlite():
        print("SQLite database not found. Please run 'ingest' first.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE documents SET doc_type = ? WHERE manual_id = ?', (doc_type, manual_id))
    
    if cursor.rowcount == 0:
        print(f"Error: Manual '{manual_id}' not found.")
    else:
        print(f"Updated doc_type for '{manual_id}' to '{doc_type}'")
        log_audit_event("update_doc_type", f"Set doc_type={doc_type} for {manual_id}")
    
    conn.commit()
    conn.close()

def list_topics():
    """List all unique topic_ids."""
    if not use_sqlite():
        print("SQLite database not found. Please run 'ingest' first.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT topic_id, COUNT(*) as chunk_count
        FROM chunks
        WHERE topic_id != ''
        GROUP BY topic_id
        ORDER BY chunk_count DESC, topic_id
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No topics found.")
        return
    
    print("\n" + "="*80)
    print("TOPIC IDs")
    print("="*80)
    print(f"Total unique topics: {len(rows)}\n")
    
    for topic_id, count in rows:
        print(f"  {topic_id:60s} ({count} chunks)")

def list_emergency():
    """List all emergency procedures."""
    if not use_sqlite():
        print("SQLite database not found. Please run 'ingest' first.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, manual_id, heading, emergency_category, topic_id
        FROM chunks
        WHERE is_emergency_procedure = 1
        ORDER BY manual_id, id
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No emergency procedures found.")
        return
    
    print("\n" + "="*80)
    print("EMERGENCY PROCEDURES")
    print("="*80)
    print(f"Total: {len(rows)}\n")
    
    for chunk_id, manual_id, heading, category, topic_id in rows:
        print(f"  [{chunk_id}] {manual_id}")
        print(f"    Heading: {heading}")
        print(f"    Category: {category or 'N/A'}")
        print(f"    Topic ID: {topic_id or 'N/A'}")
        print()

def show_compliance():
    """Show compliance status and review dates."""
    if not use_sqlite():
        print("SQLite database not found. Please run 'ingest' first.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT manual_id, doc_type, compliance_standard, effective_date, 
               mandatory_review_date, superseded_by
        FROM documents
        WHERE compliance_standard IS NOT NULL OR mandatory_review_date IS NOT NULL
        ORDER BY mandatory_review_date, manual_id
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No compliance information found.")
        return
    
    print("\n" + "="*80)
    print("COMPLIANCE STATUS")
    print("="*80)
    
    for manual_id, doc_type, std, eff_date, review_date, superseded in rows:
        print(f"\n{manual_id} ({doc_type})")
        print(f"  Standard: {std}")
        print(f"  Effective: {eff_date or 'N/A'}")
        print(f"  Review Due: {review_date or 'N/A'}")
        if superseded:
            print(f"  ⚠️  Superseded by: {superseded}")

def detect_conflicts_cmd():
    """Detect and report conflicts in the database."""
    if not use_sqlite():
        print("SQLite database not found. Please run 'ingest' first.")
        return
    
    db = load_db()
    chunks = db.get("chunks", [])
    
    if not chunks:
        print("No chunks found.")
        return
    
    print("\n" + "="*80)
    print("CONFLICT DETECTION")
    print("="*80)
    print(f"Scanning {len(chunks)} chunks...\n")
    
    # Get unique topic_ids
    topic_ids = set(c.get('topic_id') for c in chunks if c.get('topic_id'))
    print(f"Found {len(topic_ids)} unique topics")
    
    all_conflicts = []
    
    for topic_id in topic_ids:
        conflicts = detect_conflicts(chunks, topic_id)
        if conflicts:
            all_conflicts.extend(conflicts)
    
    if not all_conflicts:
        print("\n✓ No conflicts detected!")
        return
    
    print(f"\n⚠️  Found {len(all_conflicts)} potential conflicts:\n")
    
    for i, conflict in enumerate(all_conflicts, 1):
        print(f"{i}. {conflict['type'].upper()} conflict")
        print(f"   Topic: {conflict['topic_id']}")
        print(f"   Chunks: {conflict['chunk1_id']} <-> {conflict['chunk2_id']}")
        print(f"   Detail: {conflict['detail']}")
        if 'context1' in conflict:
            print(f"   Context 1: {conflict['context1'][:80]}...")
            print(f"   Context 2: {conflict['context2'][:80]}...")
        print()
    
    # Ask if user wants to flag these in the database
    response = input("Flag these conflicts in the database? (yes/no): ")
    if response.lower() == 'yes':
        total = flag_conflicts_in_db(chunks)
        print(f"\n✓ Flagged {total} conflicts in database")
        print("These conflicts can be reviewed and resolved in Phase 1.5")

# -----------------------------------------
# Phase 1.5 CLI Commands
# -----------------------------------------

def review_conflicts_cmd(status: str = "pending", detail: bool = False, conflict_id: str = None):
    """List all conflicts with specified status or show details of a specific conflict."""
    if not use_sqlite():
        print("SQLite database not found. Please run 'ingest' first.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if conflict_id:
        # Show detailed view of specific conflict
        cursor.execute('''
            SELECT conflict_id, topic_id, conflict_type, detected_at, resolution_status,
                   detail, context1, context2, chunk1_id, chunk2_id
            FROM conflict_resolutions
            WHERE conflict_id = ?
        ''', (conflict_id,))
        row = cursor.fetchone()
        
        if not row:
            print(f"Conflict {conflict_id} not found.")
            conn.close()
            return
        
        cid, topic, ctype, detected, res_status, detail_text, ctx1, ctx2, ch1, ch2 = row
        
        print("\n" + "="*80)
        print(f"CONFLICT DETAILS: {cid}")
        print("="*80)
        print(f"Topic ID: {topic}")
        print(f"Type: {ctype}")
        print(f"Status: {res_status}")
        print(f"Detected: {detected}")
        print(f"\nDetail: {detail_text}")
        print(f"\nChunk 1 ({ch1}):")
        print(f"  {ctx1}")
        print(f"\nChunk 2 ({ch2}):")
        print(f"  {ctx2}")
        
    else:
        # List conflicts by status
        cursor.execute('''
            SELECT conflict_id, topic_id, conflict_type, detected_at, detail, chunk1_id, chunk2_id
            FROM conflict_resolutions
            WHERE resolution_status = ?
            ORDER BY detected_at DESC
        ''', (status,))
        
        rows = cursor.fetchall()
        
        if not rows:
            print(f"No {status} conflicts found.")
            conn.close()
            return
        
        print("\n" + "="*80)
        print(f"CONFLICT REVIEW ({status.upper()})")
        print("="*80)
        print(f"Found {len(rows)} {status} conflicts:\n")
        
        for i, row in enumerate(rows, 1):
            cid, topic, ctype, detected, detail_text, ch1, ch2 = row
            print(f"[{i}] {cid} | {ctype} conflict")
            print(f"  Topic: {topic}")
            print(f"  Chunks: {ch1} ↔ {ch2}")
            print(f"  Detail: {detail_text}")
            print(f"  Detected: {detected}")
            print()
    
    conn.close()

def resolve_conflict_cmd(conflict_id: str, action: str, reason: str, user: str = "admin"):
    """Resolve a conflict with the specified action."""
    if not use_sqlite():
        print("SQLite database not found.")
        return
    
    valid_actions = ['accept_chunk1', 'accept_chunk2', 'merge', 'dismiss', 'convert_units', 'manual_override']
    if action not in valid_actions:
        print(f"Error: Invalid action. Must be one of: {', '.join(valid_actions)}")
        return
    
    # For convert_units, we need additional info
    kwargs = {}
    if action == 'convert_units':
        orig_unit = input("Original unit: ")
        conv_unit = input("Converted unit: ")
        kwargs = {'original_unit': orig_unit, 'converted_unit': conv_unit}
    
    success = resolve_conflict(conflict_id, action, user, reason, **kwargs)
    
    if success:
        print(f"\n✓ Conflict {conflict_id} resolved as '{action}'")
        print(f"Resolution logged by {user}")
    else:
        print(f"\n✗ Failed to resolve conflict {conflict_id}")

def request_approval_cmd(conflict_id: str, level: int, approver: str):
    """Request approval for a conflict resolution."""
    if not use_sqlite():
        print("SQLite database not found.")
        return
    
    if level not in [1, 2, 3]:
        print("Error: Approval level must be 1 (supervisor), 2 (manager), or 3 (compliance officer)")
        return
    
    success = request_approval(conflict_id, level, approver)
    
    if success:
        level_name = {1: "supervisor", 2: "manager", 3: "compliance officer"}[level]
        print(f"\n✓ Approval request sent to {approver} ({level_name})")
        print(f"Conflict: {conflict_id}")
    else:
        print(f"\n✗ Failed to request approval")

def approve_resolution_cmd(conflict_id: str, approver: str, comments: str = ""):
    """Approve a conflict resolution."""
    if not use_sqlite():
        print("SQLite database not found.")
        return
    
    success = approve_resolution(conflict_id, approver, comments)
    
    if success:
        print(f"\n✓ Conflict {conflict_id} approved by {approver}")
    else:
        print(f"\n✗ Failed to approve")

def reject_resolution_cmd(conflict_id: str, approver: str, comments: str = ""):
    """Reject a conflict resolution."""
    if not use_sqlite():
        print("SQLite database not found.")
        return
    
    success = reject_resolution(conflict_id, approver, comments)
    
    if success:
        print(f"\n✓ Conflict {conflict_id} rejected by {approver}")
        print(f"Reason: {comments}")
    else:
        print(f"\n✗ Failed to reject")

def list_approvals_cmd(user: str = None):
    """List pending approvals, optionally filtered by user."""
    if not use_sqlite():
        print("SQLite database not found.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if user:
        cursor.execute('''
            SELECT aw.id, cr.conflict_id, aw.approval_level, aw.approver, aw.approval_status
            FROM approval_workflow aw
            JOIN conflict_resolutions cr ON aw.conflict_resolution_id = cr.id
            WHERE aw.approver = ? AND aw.approval_status = 'pending'
            ORDER BY aw.id DESC
        ''', (user,))
    else:
        cursor.execute('''
            SELECT aw.id, cr.conflict_id, aw.approval_level, aw.approver, aw.approval_status
            FROM approval_workflow aw
            JOIN conflict_resolutions cr ON aw.conflict_resolution_id = cr.id
            WHERE aw.approval_status = 'pending'
            ORDER BY aw.id DESC
        ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No pending approvals found.")
        return
    
    print("\n" + "="*80)
    print("PENDING APPROVALS")
    print("="*80)
    print(f"Found {len(rows)} pending approval(s):\n")
    
    level_names = {1: "Supervisor", 2: "Manager", 3: "Compliance Officer"}
    
    for approval_id, conflict_id, level, approver, status in rows:
        print(f"• {conflict_id} - awaiting {level_names.get(level, 'Unknown')} approval from {approver}")
    
    print()

def conflict_stats_cmd():
    """Show conflict resolution statistics."""
    if not use_sqlite():
        print("SQLite database not found.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total conflicts
    cursor.execute("SELECT COUNT(*) FROM conflict_resolutions")
    total = cursor.fetchone()[0]
    
    if total == 0:
        print("No conflicts found in database.")
        conn.close()
        return
    
    # By status
    cursor.execute('''
        SELECT resolution_status, COUNT(*)
        FROM conflict_resolutions
        GROUP BY resolution_status
    ''')
    by_status = dict(cursor.fetchall())
    
    # By type
    cursor.execute('''
        SELECT conflict_type, COUNT(*)
        FROM conflict_resolutions
        GROUP BY conflict_type
    ''')
    by_type = dict(cursor.fetchall())
    
    # By resolution method
    cursor.execute('''
        SELECT resolution_type, COUNT(*)
        FROM conflict_resolutions
        WHERE resolution_type IS NOT NULL
        GROUP BY resolution_type
    ''')
    by_resolution = dict(cursor.fetchall())
    
    # Pending approvals
    cursor.execute('''
        SELECT COUNT(*)
        FROM approval_workflow
        WHERE approval_status = 'pending'
    ''')
    pending_approvals = cursor.fetchone()[0]
    
    conn.close()
    
    print("\n" + "="*80)
    print("CONFLICT RESOLUTION STATISTICS")
    print("="*80)
    print(f"Total Conflicts Detected:    {total}")
    
    for status, count in by_status.items():
        pct = (count / total * 100)
        print(f"  {status.capitalize():20s}  {count:3d}  ({pct:5.1f}%)")
    
    print(f"\nBy Type:")
    for ctype, count in by_type.items():
        pct = (count / total * 100)
        print(f"  {ctype.capitalize():20s}  {count:3d}  ({pct:5.1f}%)")
    
    if by_resolution:
        resolved_total = sum(by_resolution.values())
        print(f"\nResolution Methods:")
        for method, count in by_resolution.items():
            pct = (count / resolved_total * 100) if resolved_total > 0 else 0
            print(f"  {method.replace('_', ' ').capitalize():20s}  {count:3d}  ({pct:5.1f}% of resolved)")
    
    print(f"\nPending Approvals:           {pending_approvals}")
    print("="*80)

# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Small, boring Q&A engine over local manuals.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="Ingest all manuals/*.txt,*.md into the local DB.")
    sub.add_parser("list", help="List ingested manuals and chunk counts.")

    show_p = sub.add_parser("show", help="Show a specific chunk's text.")
    show_p.add_argument("chunk_id", type=str, help="Chunk id, e.g. C18")

    ask_p = sub.add_parser("ask", help="Ask a question over the ingested manuals.")
    ask_p.add_argument("question", type=str)
    ask_p.add_argument("--include", nargs="*", default=None)
    ask_p.add_argument("--top_k", type=int, default=12)

    prev_p = sub.add_parser("preview", help="Preview chunk text for a manual_id.")
    prev_p.add_argument("--manual-id", required=True)
    prev_p.add_argument("--start-index", type=int, default=0)
    prev_p.add_argument("--limit", type=int, default=10)

    gap_p = sub.add_parser("gap", help="Basic gap analysis: standard vs manual.")
    gap_p.add_argument("--standard-id", required=True)
    gap_p.add_argument("--manual-id", required=True)
    gap_p.add_argument("--max-clauses", type=int, default=5)
    gap_p.add_argument("--top-n", type=int, default=5)
    gap_p.add_argument("--start-index", type=int, default=0)
    gap_p.add_argument("--min-sim", type=float, default=0.35)
    gap_p.add_argument("--out-csv", type=str, default=None)
    gap_p.add_argument("--out-html", type=str, default=None)

    delete_p = sub.add_parser("delete", help="Delete a manual from the DB.")
    delete_p.add_argument("manual_id")
    delete_p.add_argument("--delete-file", action="store_true")

    export_p = sub.add_parser("export", help="Export a manual into a single text file.")
    export_p.add_argument("manual_id")
    export_p.add_argument("--out-path", type=str, default=None)
    
    # Phase 1 new commands
    sub.add_parser("list-metadata", help="Show doc_type and compliance info for all documents.")
    
    set_doc_type_p = sub.add_parser("set-doc-type", help="Update doc_type for a manual.")
    set_doc_type_p.add_argument("manual_id", type=str)
    set_doc_type_p.add_argument("doc_type", type=str, choices=DOC_TYPES)
    
    sub.add_parser("list-topics", help="Show all unique topic_ids.")
    sub.add_parser("list-emergency", help="Show all emergency procedures.")
    sub.add_parser("show-compliance", help="Show compliance status and review dates.")
    sub.add_parser("detect-conflicts", help="Detect and flag potential conflicts in the database.")
    
    # Phase 1.5 new commands
    review_p = sub.add_parser("review-conflicts", help="Review conflicts by status or show conflict details.")
    review_p.add_argument("--status", type=str, default="pending", choices=["pending", "resolved", "deferred", "dismissed"])
    review_p.add_argument("--conflict-id", type=str, default=None, help="Show details of specific conflict")
    review_p.add_argument("--detail", action="store_true", help="Show detailed view")
    
    resolve_p = sub.add_parser("resolve-conflict", help="Resolve a conflict.")
    resolve_p.add_argument("conflict_id", type=str)
    resolve_p.add_argument("--action", type=str, required=True, 
                          choices=["accept_chunk1", "accept_chunk2", "merge", "dismiss", "convert_units", "manual_override"])
    resolve_p.add_argument("--reason", type=str, required=True)
    resolve_p.add_argument("--user", type=str, default="admin")
    
    req_approval_p = sub.add_parser("request-approval", help="Request approval for a conflict resolution.")
    req_approval_p.add_argument("--conflict-id", type=str, required=True)
    req_approval_p.add_argument("--level", type=int, required=True, choices=[1, 2, 3])
    req_approval_p.add_argument("--approver", type=str, required=True)
    
    approve_p = sub.add_parser("approve-resolution", help="Approve a conflict resolution.")
    approve_p.add_argument("--conflict-id", type=str, required=True)
    approve_p.add_argument("--user", type=str, required=True)
    approve_p.add_argument("--comments", type=str, default="")
    
    reject_p = sub.add_parser("reject-resolution", help="Reject a conflict resolution.")
    reject_p.add_argument("--conflict-id", type=str, required=True)
    reject_p.add_argument("--user", type=str, required=True)
    reject_p.add_argument("--comments", type=str, default="")
    
    list_approvals_p = sub.add_parser("list-approvals", help="List pending approvals.")
    list_approvals_p.add_argument("--user", type=str, default=None)
    
    sub.add_parser("conflict-stats", help="Show conflict resolution statistics.")

    args = parser.parse_args()

    if args.command == "ingest":
        ingest(use_hierarchy=True, max_chars=1400)
    elif args.command == "list":
        list_manuals()
    elif args.command == "show":
        show_chunk(args.chunk_id)
    elif args.command == "ask":
        ask(args.question, include=args.include, top_k=args.top_k)
    elif args.command == "preview":
        preview_manual(args.manual_id, start_index=args.start_index, limit=args.limit)
    elif args.command == "gap":
        gap(
            standard_id=args.standard_id,
            manual_id=args.manual_id,
            max_clauses=args.max_clauses,
            top_n=args.top_n,
            start_index=args.start_index,
            min_sim=args.min_sim,
            out_csv=args.out_csv,
            out_html=args.out_html,
        )
    elif args.command == "delete":
        delete_manual(args.manual_id, delete_file=args.delete_file)
    elif args.command == "export":
        export_manual(args.manual_id, out_path=args.out_path)
    elif args.command == "list-metadata":
        list_metadata()
    elif args.command == "set-doc-type":
        set_doc_type_cmd(args.manual_id, args.doc_type)
    elif args.command == "list-topics":
        list_topics()
    elif args.command == "list-emergency":
        list_emergency()
    elif args.command == "show-compliance":
        show_compliance()
    elif args.command == "detect-conflicts":
        detect_conflicts_cmd()
    # Phase 1.5 commands
    elif args.command == "review-conflicts":
        review_conflicts_cmd(status=args.status, detail=args.detail, conflict_id=args.conflict_id)
    elif args.command == "resolve-conflict":
        resolve_conflict_cmd(args.conflict_id, args.action, args.reason, args.user)
    elif args.command == "request-approval":
        request_approval_cmd(args.conflict_id, args.level, args.approver)
    elif args.command == "approve-resolution":
        approve_resolution_cmd(args.conflict_id, args.user, args.comments)
    elif args.command == "reject-resolution":
        reject_resolution_cmd(args.conflict_id, args.user, args.comments)
    elif args.command == "list-approvals":
        list_approvals_cmd(args.user)
    elif args.command == "conflict-stats":
        conflict_stats_cmd()

if __name__ == "__main__":
    main()




