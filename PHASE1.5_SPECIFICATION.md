# Phase 1.5: Conflict Resolution & Approval Workflows

## Overview

Phase 1.5 builds upon Phase 1's conflict detection foundation by adding human-in-the-loop resolution workflows, unit conversion helpers, and approval tracking. This phase focuses on **operationalizing conflict management** without introducing ML-based decision-making.

**Key Principle**: All resolutions must be traceable, auditable, and reversible.

## Prerequisites (Completed in Phase 1)

✅ SQLite database with conflict_type field  
✅ Conflict detection for numeric values and unit mismatches  
✅ Topic-based chunk organization  
✅ Comprehensive TAGGING_RULESET  
✅ Audit logging infrastructure

## Goals

1. **Enable manual review** of detected conflicts
2. **Track resolution decisions** with full audit trail
3. **Provide unit conversion** helpers for common mismatches
4. **Support approval workflows** for conflict resolutions
5. **Maintain explainability** - no black-box decisions

## Architecture

### Database Schema Extensions

#### 1. New `conflict_resolutions` Table

```sql
CREATE TABLE conflict_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conflict_id TEXT UNIQUE,  -- Generated ID for this specific conflict
    chunk1_id TEXT,
    chunk2_id TEXT,
    topic_id TEXT,
    conflict_type TEXT,  -- numeric, unit_mismatch, modal, structural
    detected_at TEXT,
    
    -- Resolution details
    resolution_status TEXT,  -- pending, resolved, deferred, dismissed
    resolution_type TEXT,    -- accept_chunk1, accept_chunk2, merge, manual_override, convert_units
    resolved_by TEXT,
    resolved_at TEXT,
    resolution_notes TEXT,
    
    -- Conflict details (denormalized for easier querying)
    detail TEXT,
    context1 TEXT,
    context2 TEXT,
    
    -- Unit conversion specifics (if applicable)
    original_unit TEXT,
    converted_unit TEXT,
    conversion_factor REAL,
    
    FOREIGN KEY (chunk1_id) REFERENCES chunks(id),
    FOREIGN KEY (chunk2_id) REFERENCES chunks(id)
);
```

#### 2. New `approval_workflow` Table

```sql
CREATE TABLE approval_workflow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conflict_resolution_id INTEGER,
    approval_level INTEGER,  -- 1=supervisor, 2=manager, 3=compliance_officer
    approver TEXT,
    approval_status TEXT,  -- pending, approved, rejected
    approved_at TEXT,
    comments TEXT,
    
    FOREIGN KEY (conflict_resolution_id) REFERENCES conflict_resolutions(id)
);
```

#### 3. Extend `audit_log` with Conflict Events

New audit event types:
- `conflict_created` - Conflict detected and logged
- `conflict_reviewed` - Manual review initiated
- `conflict_resolved` - Resolution decision made
- `conflict_approved` - Resolution approved
- `conflict_rejected` - Resolution rejected
- `unit_converted` - Automatic unit conversion applied

### Unit Conversion System

#### Supported Conversions

```python
UNIT_CONVERSIONS = {
    # Distance conversions
    ("meters", "feet"): 3.28084,
    ("feet", "meters"): 0.3048,
    
    # Pressure conversions
    ("bar", "psi"): 14.5038,
    ("psi", "bar"): 0.0689476,
    ("bar", "ata"): 1.01972,  # Approximate (1 bar ≈ 1.02 ata)
    ("ata", "bar"): 0.980665,
    ("psi", "ata"): 0.068046,
    ("ata", "psi"): 14.6959,
    
    # Volume conversions
    ("litres", "cubic_feet"): 0.0353147,
    ("cubic_feet", "litres"): 28.3168,
}

# Conversion tolerances (for fuzzy matching)
CONVERSION_TOLERANCE = {
    "meters": 0.01,      # 1cm tolerance
    "feet": 0.1,         # ~3cm tolerance
    "bar": 0.1,          # 0.1 bar tolerance
    "psi": 1.0,          # 1 psi tolerance
    "ata": 0.1,          # 0.1 ata tolerance
    "litres": 0.1,       # 0.1L tolerance
    "cubic_feet": 0.01,  # 0.01 cf tolerance
}
```

#### Conversion Logic

```python
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

def units_match_within_tolerance(val1: float, unit1: str, 
                                  val2: float, unit2: str) -> bool:
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
```

## CLI Commands (New)

### 1. Review Conflicts

```bash
# List all unresolved conflicts
python manual_core.py review-conflicts [--status pending]

# Show specific conflict details
python manual_core.py review-conflicts --conflict-id CONF_001 --detail
```

**Output Example:**
```
================================================================================
CONFLICT REVIEW
================================================================================
Found 3 pending conflicts:

[1] CONF_001 | numeric conflict
  Topic: bailout_gas_requirements
  Chunks: C145 (Manual - Diving Operations) ↔ C289 (IMCA D014 Standard)
  
  C145 Context: "...bailout gas must have 50 bar minimum pressure..."
  C289 Context: "...emergency gas supply shall be 60 bar minimum..."
  
  Status: pending
  Detected: 2024-12-16 10:23:45

[2] CONF_002 | unit_mismatch
  Topic: maximum_depth_requirements
  Chunks: C198 ↔ C312
  
  C198: "...maximum depth 30 metres..."
  C312: "...depth limit 100 feet..."
  
  Auto-conversion check: 30m = 98.4ft (within tolerance)
  Suggested resolution: Convert units and accept as equivalent
  
  Status: pending
  Detected: 2024-12-16 10:25:12

Commands:
  resolve-conflict CONF_001 --action [accept_chunk1|accept_chunk2|merge|dismiss]
  resolve-conflict CONF_002 --action convert_units
```

### 2. Resolve Conflict

```bash
# Accept one chunk as authoritative
python manual_core.py resolve-conflict CONF_001 --action accept_chunk1 \
    --reason "IMCA standard supersedes operational manual" \
    --user "john.doe"

# Convert units and mark as equivalent
python manual_core.py resolve-conflict CONF_002 --action convert_units \
    --reason "Values are equivalent after conversion" \
    --user "john.doe"

# Merge information from both chunks
python manual_core.py resolve-conflict CONF_003 --action merge \
    --reason "Both values are contextually valid" \
    --user "john.doe"

# Dismiss as false positive
python manual_core.py resolve-conflict CONF_004 --action dismiss \
    --reason "Different contexts - not actually conflicting" \
    --user "john.doe"
```

### 3. Approval Workflow

```bash
# Submit resolution for approval
python manual_core.py request-approval --conflict-id CONF_001 \
    --level supervisor --approver "jane.smith"

# Approve a resolution
python manual_core.py approve-resolution --conflict-id CONF_001 \
    --user "jane.smith" --comments "Reviewed and approved"

# Reject a resolution
python manual_core.py reject-resolution --conflict-id CONF_001 \
    --user "jane.smith" --comments "Need additional evidence"

# List pending approvals
python manual_core.py list-approvals [--user jane.smith]
```

### 4. Conflict Reports

```bash
# Generate conflict resolution report
python manual_core.py conflict-report \
    --format [text|csv|html] \
    --output report.html \
    --status [all|pending|resolved|deferred]

# Show conflict statistics
python manual_core.py conflict-stats
```

**Stats Output Example:**
```
CONFLICT RESOLUTION STATISTICS
================================================================================
Total Conflicts Detected:    47
  Pending Review:           12  (25.5%)
  Resolved:                 30  (63.8%)
  Deferred:                  3  (6.4%)
  Dismissed:                 2  (4.3%)

By Type:
  Numeric Conflicts:        23  (48.9%)
  Unit Mismatches:          18  (38.3%)
  Modal Conflicts:           4  (8.5%)
  Structural:                2  (4.3%)

Resolution Methods:
  Accept Chunk 1:           14  (46.7% of resolved)
  Accept Chunk 2:            8  (26.7%)
  Convert Units:            12  (40.0%)
  Merge:                     3  (10.0%)
  Manual Override:           1  (3.3%)

Average Resolution Time:     2.3 days
Pending Approvals:          5
```

## Implementation Functions

### Core Functions

#### 1. Create Conflict Resolution Entry

```python
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
```

#### 2. Resolve Conflict

```python
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
        return False
    
    if row[0] != 'pending':
        print(f"Error: Conflict {conflict_id} already {row[0]}")
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
```

#### 3. Request Approval

```python
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
        return False
    
    resolution_id, status = row
    
    if status != 'resolved':
        print(f"Error: Conflict must be resolved before requesting approval")
        return False
    
    # Create approval request
    cursor.execute('''
        INSERT INTO approval_workflow (
            conflict_resolution_id, approval_level, approver,
            approval_status, approved_at
        ) VALUES (?, ?, ?, 'pending', NULL)
    ''', (resolution_id, approval_level, approver))
    
    conn.commit()
    conn.close()
    
    # Log audit event
    log_audit_event(
        'approval_requested',
        f"Approval requested for {conflict_id} from {approver} (level {approval_level})"
    )
    
    return True
```

## GUI Integration (Future)

Phase 1.5 establishes the backend infrastructure. A future GUI could add:

1. **Conflict Dashboard** - Visual overview of conflicts by status/type
2. **Side-by-Side Comparison** - Show conflicting chunks with highlighting
3. **Unit Converter Widget** - Interactive unit conversion tool
4. **Approval Queue** - Drag-and-drop workflow for approvers
5. **Resolution History** - Timeline of conflict lifecycle

## Testing Requirements

### Unit Tests

1. **Unit Conversion Tests**
   ```python
   def test_unit_conversion():
       assert convert_unit(30, "meters", "feet") ≈ 98.4
       assert convert_unit(50, "bar", "psi") ≈ 725.2
       assert units_match_within_tolerance(30, "meters", 98.4, "feet") == True
   ```

2. **Conflict Resolution Tests**
   ```python
   def test_conflict_resolution():
       conflict_id = create_conflict_resolution(...)
       assert resolve_conflict(conflict_id, "accept_chunk1", "test_user", "Test") == True
       # Verify database state
   ```

3. **Approval Workflow Tests**
   ```python
   def test_approval_workflow():
       conflict_id = create_conflict_resolution(...)
       resolve_conflict(conflict_id, ...)
       assert request_approval(conflict_id, 1, "supervisor") == True
   ```

### Integration Tests

1. **End-to-End Conflict Resolution**
   - Detect conflict → Review → Resolve → Approve → Verify audit log

2. **Unit Conversion Pipeline**
   - Detect unit mismatch → Auto-suggest conversion → Apply → Verify equivalence

3. **Multi-Level Approval**
   - Resolve conflict → Request level 1 → Approve → Request level 2 → Approve

## Migration from Phase 1

```python
# migrate_phase1_to_phase1.5.py
def migrate_existing_conflicts():
    """
    Migrate conflicts detected in Phase 1 to Phase 1.5 resolution system.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all chunks with conflict_type set
    cursor.execute(
        "SELECT id, topic_id, conflict_type FROM chunks WHERE conflict_type IS NOT NULL"
    )
    flagged_chunks = cursor.fetchall()
    
    # Re-run conflict detection and create resolution entries
    for chunk_id, topic_id, conflict_type in flagged_chunks:
        # Find conflicting pairs and create resolution entries
        conflicts = detect_conflicts_for_chunk(chunk_id, topic_id)
        for conflict in conflicts:
            create_conflict_resolution(
                chunk_id,
                conflict['other_chunk_id'],
                topic_id,
                conflict_type,
                conflict['detail'],
                conflict.get('context1', ''),
                conflict.get('context2', '')
            )
    
    conn.close()
    print(f"Migrated {len(flagged_chunks)} conflict flags to resolution system")
```

## Success Criteria

Phase 1.5 is complete when:

✅ All conflict detection creates resolution entries  
✅ Manual review CLI commands functional  
✅ Unit conversion system working with 6+ unit pairs  
✅ Approval workflow tracks multi-level approvals  
✅ Audit log captures all resolution events  
✅ Resolution statistics and reporting available  
✅ Migration script converts Phase 1 conflicts  
✅ All tests passing (unit + integration)  
✅ Documentation updated with Phase 1.5 features  

## Timeline Estimate

- **Database Schema**: 1 day
- **Unit Conversion System**: 2 days
- **CLI Commands**: 3 days
- **Conflict Resolution Logic**: 2 days
- **Approval Workflow**: 2 days
- **Testing**: 2 days
- **Documentation**: 1 day
- **Migration & Validation**: 1 day

**Total**: ~14 days (2 weeks)

## Future Enhancements (Phase 2+)

- Machine learning to suggest resolutions based on past decisions
- Automatic conflict resolution for high-confidence cases
- Web-based conflict review dashboard
- Email notifications for pending approvals
- Bulk conflict resolution operations
- Conflict pattern analysis and reporting

## References

- Phase 1 Implementation: `PHASE1_SUMMARY.md`
- Database Schema: `PHASE1_README.md` (Schema section)
- TAGGING_RULESET: `manual_core.py` lines 54-245
- Conflict Detection: `manual_core.py` lines 495-582
