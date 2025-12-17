# Phase 1: Backend Data Model - Implementation Guide

## Overview

Phase 1 establishes a stable, auditable backend data model that supports regulatory compliance, unit management, and emergency procedures. This phase migrates from JSON to SQLite + FAISS for improved performance and scalability.

## Key Features

### 1. SQLite Database Schema

The new database structure includes:

#### **documents** table
- `manual_id` (PRIMARY KEY): Unique identifier for the document
- `doc_type`: Document classification (manual, standard, legislation, guidance, client_spec)
- `compliance_standard`: e.g., "IMCA D014 Rev 2"
- `effective_date`: When this version became active
- `superseded_by`: Link to newer versions
- `mandatory_review_date`: Compliance deadlines
- `file_path`: Original file location
- `ingested_at`: Timestamp of ingestion

#### **chunks** table
- `id` (PRIMARY KEY): Unique chunk identifier (e.g., "C123")
- `manual_id` (FOREIGN KEY): Reference to parent document
- `text`: Chunk text content
- `heading`: Section heading
- `path`: Hierarchical path to section
- `heading_num`: Heading number (e.g., "1.5.2")
- `level`: Heading depth level
- `topic_id`: Stable topic identifier (auto-generated)
- `is_emergency_procedure`: Boolean flag
- `emergency_category`: bailout, equipment_failure, medical, weather, decompression
- `units`: JSON array of detected units
- `conflict_type`: For future conflict detection

#### **topics** table
- `topic_id` (PRIMARY KEY): Unique topic identifier
- `description`: Optional topic description
- `first_seen`: Timestamp when first registered

#### **audit_log** table
- `id` (PRIMARY KEY): Auto-increment ID
- `timestamp`: Event timestamp
- `user`: User who performed action (currently "system")
- `action`: Action type
- `details`: Action details

### 2. FAISS Vector Index

Embeddings are now stored in a separate FAISS index for fast similarity search:
- `embeddings.faiss`: FAISS index file
- `embeddings.faiss.ids`: Chunk ID mapping

### 3. Metadata Fields

#### Document Type Auto-Detection
Documents are automatically classified based on filename and content patterns:
- **manual**: Operational procedures
- **standard**: Industry standards (e.g., IMCA documents)
- **legislation**: Regulatory requirements
- **guidance**: Best practices and guidance documents
- **client_spec**: Client-specific specifications

#### Topic ID Generation
Topic IDs are automatically generated from heading text:
- Deterministic and stable
- Rule-based (no ML)
- Example: "1.5 Bailout Gas Requirements" → "bailout_gas_requirements"

#### Emergency Procedure Detection
Emergency procedures are automatically tagged based on keywords:
- Keywords: "bailout", "emergency", "rescue", "abort", etc.
- Categories: bailout, equipment_failure, medical, weather, decompression
- Both `is_emergency_procedure` flag and `emergency_category` field

#### Unit Extraction
Units are automatically extracted from text using regex patterns:
- Supported units: meters, feet, bar, psi, litres, cubic_feet
- Stored with value, unit name, and context
- Example: "50 bar" → `{"value": "50", "unit": "bar", "context": "..."}`

### 4. Audit Logging

All significant operations are logged to the audit_log table:
- Document ingestion
- Metadata updates
- Database migrations
- Future: User actions, approvals, conflict resolutions

## New CLI Commands

### list-metadata
Show document type and compliance information for all documents.

```bash
python manual_core.py list-metadata
```

### set-doc-type
Update the document type for a specific manual.

```bash
python manual_core.py set-doc-type "Manual - Diving Operations" manual
```

### list-topics
Show all unique topic IDs with chunk counts.

```bash
python manual_core.py list-topics
```

### list-emergency
List all emergency procedures with their categories.

```bash
python manual_core.py list-emergency
```

### show-compliance
Show compliance status and review dates for documents with compliance metadata.

```bash
python manual_core.py show-compliance
```

### detect-conflicts
Detect and report potential conflicts in the database (same topic_id with different values or units).

```bash
python manual_core.py detect-conflicts
```

This command will:
- Scan all chunks for conflicts
- Report numeric value conflicts (same unit, different values)
- Report unit mismatches (same measurement type, different units)
- Optionally flag conflicts in the database for review

## Migration from JSON to SQLite

### Running the Migration

If you have an existing `db.json`, migrate it to the new format:

```bash
python migrate_db.py
```

The migration script will:
1. Load your existing db.json
2. Create the new SQLite database
3. Migrate all chunks with enhanced metadata
4. Auto-detect document types
5. Generate topic IDs
6. Detect emergency procedures
7. Extract units from text
8. Build FAISS index
9. Log the migration event
10. Verify the migration

### What Gets Preserved

- All chunk text and embeddings
- All document metadata
- Heading hierarchies
- Manual IDs

### What Gets Enhanced

- Auto-generated topic IDs for all chunks
- Document type classification
- Emergency procedure detection
- Unit extraction from numeric content
- Audit trail of migration

### Backward Compatibility

The system maintains backward compatibility:
- Original `db.json` is preserved (not deleted)
- Legacy JSON format continues to be updated alongside SQLite
- Functions check for SQLite database and fall back to JSON if needed

## Usage Examples

### Ingesting Documents

The ingest process now automatically:
- Detects document types
- Generates topic IDs
- Detects emergency procedures
- Extracts units
- Stores in both SQLite and JSON (for compatibility)
- Builds FAISS index
- Logs audit events

```bash
# Ingest all documents in manuals/ directory
python manual_core.py ingest
```

### Querying Metadata

```bash
# List all documents with metadata
python manual_core.py list-metadata

# Update a document's type
python manual_core.py set-doc-type "Annexe A - Air Diving Operations and Emergency Procedures" standard

# List all topics
python manual_core.py list-topics

# Show emergency procedures
python manual_core.py list-emergency

# View compliance information
python manual_core.py show-compliance
```

### Existing Commands Still Work

All existing commands continue to work as before:

```bash
# List manuals
python manual_core.py list

# Ask questions
python manual_core.py ask "What are the bailout gas requirements?"

# Gap analysis
python manual_core.py gap --standard-id "Annexe A" --manual-id "Manual - Diving Operations"
```

## Database Schema Diagram

```
┌─────────────────────────────────┐
│        documents                │
├─────────────────────────────────┤
│ manual_id (PK)                  │
│ doc_type                        │
│ compliance_standard             │
│ effective_date                  │
│ superseded_by                   │
│ mandatory_review_date           │
│ file_path                       │
│ ingested_at                     │
└─────────────────────────────────┘
           │
           │ 1:N
           ▼
┌─────────────────────────────────┐
│         chunks                  │
├─────────────────────────────────┤
│ id (PK)                         │
│ manual_id (FK)                  │
│ text                            │
│ heading                         │
│ path                            │
│ heading_num                     │
│ level                           │
│ topic_id                        │
│ is_emergency_procedure          │
│ emergency_category              │
│ units (JSON)                    │
│ conflict_type                   │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│         topics                  │
├─────────────────────────────────┤
│ topic_id (PK)                   │
│ description                     │
│ first_seen                      │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│       audit_log                 │
├─────────────────────────────────┤
│ id (PK, AUTO)                   │
│ timestamp                       │
│ user                            │
│ action                          │
│ details                         │
└─────────────────────────────────┘
```

## API Reference

### Helper Functions

#### `generate_topic_id(heading_text: str) -> str`
Generates a stable topic ID from heading text.

```python
topic_id = generate_topic_id("1.5 Bailout Gas Requirements")
# Returns: "bailout_gas_requirements"
```

#### `detect_emergency_procedure(text: str, heading: str) -> Tuple[bool, Optional[str]]`
Detects if text/heading indicates an emergency procedure.

```python
is_emergency, category = detect_emergency_procedure(text, heading)
# Returns: (True, "bailout") or (False, None)
```

#### `extract_units(text: str) -> List[Dict[str, str]]`
Extracts units from text.

```python
units = extract_units("The depth is 30 metres with 50 bar pressure")
# Returns: [{"value": "30", "unit": "meters", "context": "..."},
#           {"value": "50", "unit": "bar", "context": "..."}]
```

#### `detect_doc_type(filename: str, text: str = "") -> str`
Auto-detects document type.

```python
doc_type = detect_doc_type("Manual - Diving Operations.txt")
# Returns: "manual"
```

### Database Functions

#### `init_sqlite_db()`
Initialize the SQLite database with schema.

#### `get_db_connection() -> sqlite3.Connection`
Get a database connection.

#### `log_audit_event(action: str, details: str, user: str = "system")`
Log an audit event.

#### `use_sqlite() -> bool`
Check if SQLite database exists and should be used.

## Testing

The implementation includes comprehensive testing for:
- Topic ID generation (deterministic)
- Emergency detection (keyword matching)
- Unit extraction (regex patterns)
- Document type detection
- Database schema creation
- Audit logging
- Migration script

Run tests manually:

```bash
# Test helper functions
python3 << EOF
from manual_core import generate_topic_id, detect_emergency_procedure, extract_units
# ... test code ...
EOF

# Test database initialization
python3 << EOF
from manual_core import init_sqlite_db, get_db_connection
# ... test code ...
EOF
```

## Future Phases

Phase 1 provides the foundation for:
- **Phase 1.5**: Conflict detection and flagging
- **Phase 2**: Approval workflows and human-in-the-loop
- **Phase 3**: Advanced audit and comparison features
- **Phase 4**: UI enhancements

## Technical Notes

### Performance Considerations

- FAISS provides O(log n) similarity search (vs O(n) for naive approach)
- SQLite indexes on manual_id, topic_id for fast filtering
- Batch embedding generation (16 chunks at a time)
- Normalized vectors for cosine similarity

### Limitations

- Emergency detection is keyword-based (not semantic)
- Topic IDs are generated from headings only (not content)
- Unit extraction uses fixed regex patterns
- No conflict resolution yet (Phase 1.5)

### Dependencies

```
openai>=1.0.0       # For embeddings and chat
faiss-cpu>=1.7.4    # For vector similarity search
numpy>=1.24.0       # For array operations
```

## Troubleshooting

### "SQLite database not found"
Run `python manual_core.py ingest` to create the database, or use `python migrate_db.py` if you have existing data.

### "FAISS not available"
Install with: `pip install faiss-cpu`. The system will fall back to slower similarity search if FAISS is not available.

### Migration Issues
If migration fails:
1. Your original `db.json` is preserved
2. Delete `manual_data.db` and `embeddings.faiss*`
3. Report the error
4. Re-run with `python migrate_db.py`

## Support

For issues or questions about Phase 1:
1. Check this README
2. Review the audit log: `SELECT * FROM audit_log`
3. Verify schema: `.schema` in sqlite3 CLI
4. Check GitHub issues

## Contributing

When extending Phase 1:
1. Update schema with migrations
2. Add audit logging for new actions
3. Update this README
4. Add tests for new functionality
5. Maintain backward compatibility
