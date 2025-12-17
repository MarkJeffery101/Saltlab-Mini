#!/usr/bin/env python3
"""
migrate_db.py - Migration script from JSON to SQLite + FAISS
Migrates existing db.json to the new SQLite database structure.
"""

import os
import json
import sqlite3
import sys
from datetime import datetime
import numpy as np

# Try to import FAISS
try:
    import faiss
except ImportError:
    print("Warning: FAISS not installed. Vector index will not be created.", file=sys.stderr)
    faiss = None

# Import constants from manual_core
from manual_core import (
    DB_PATH, SQLITE_DB_PATH, FAISS_INDEX_PATH,
    init_sqlite_db, detect_doc_type, generate_topic_id,
    detect_emergency_procedure, extract_units
)


def migrate():
    """Migrate from db.json to SQLite + FAISS."""
    
    print("="*80)
    print("DATABASE MIGRATION: JSON → SQLite + FAISS")
    print("="*80)
    
    # Check if source exists
    if not os.path.exists(DB_PATH):
        print(f"\nError: Source database '{DB_PATH}' not found.")
        print("Nothing to migrate.")
        return False
    
    # Check if target already exists
    if os.path.exists(SQLITE_DB_PATH):
        response = input(f"\nWarning: '{SQLITE_DB_PATH}' already exists. Overwrite? (yes/no): ")
        if response.lower() != 'yes':
            print("Migration cancelled.")
            return False
        os.remove(SQLITE_DB_PATH)
    
    # Load JSON database
    print(f"\n[1/5] Loading {DB_PATH}...")
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    chunks = db.get('chunks', [])
    print(f"      Found {len(chunks)} chunks")
    
    if not chunks:
        print("      No chunks to migrate.")
        return False
    
    # Initialize SQLite
    print(f"\n[2/5] Initializing SQLite database at {SQLITE_DB_PATH}...")
    init_sqlite_db()
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    
    # Extract unique manuals
    print("\n[3/5] Migrating document metadata...")
    manuals = {}
    for chunk in chunks:
        manual_id = chunk.get('manual_id', '')
        if manual_id and manual_id not in manuals:
            manuals[manual_id] = {
                'first_text': chunk.get('text', ''),
                'file_path': f"manuals/{manual_id}.txt"  # Reconstruct likely path
            }
    
    print(f"      Found {len(manuals)} unique documents")
    
    # Insert documents
    for manual_id, info in manuals.items():
        # Try to detect doc_type from filename or content
        doc_type = detect_doc_type(manual_id, info['first_text'])
        
        cursor.execute('''
            INSERT INTO documents (manual_id, doc_type, file_path, ingested_at)
            VALUES (?, ?, ?, ?)
        ''', (manual_id, doc_type, info['file_path'], datetime.utcnow().isoformat()))
        
        print(f"      - {manual_id} (detected as: {doc_type})")
    
    conn.commit()
    
    # Migrate chunks
    print("\n[4/5] Migrating chunks with enhanced metadata...")
    topics_seen = set()
    all_embeddings = []
    all_chunk_ids = []
    
    migrated_count = 0
    for chunk in chunks:
        chunk_id = chunk.get('id', '')
        manual_id = chunk.get('manual_id', '')
        text = chunk.get('text', '')
        heading = chunk.get('heading', '')
        path = chunk.get('path', '')
        heading_num = chunk.get('heading_num', '')
        level = chunk.get('level', 0)
        
        # Generate new metadata if not present
        topic_id = chunk.get('topic_id') or generate_topic_id(heading)
        
        # Check for emergency procedures
        is_emergency = chunk.get('is_emergency_procedure')
        emergency_category = chunk.get('emergency_category')
        
        if is_emergency is None:
            is_emergency, emergency_category = detect_emergency_procedure(text, heading)
        
        # Extract units if not present
        units = chunk.get('units')
        if units is None or units == []:
            units = extract_units(text)
        
        # Insert chunk
        cursor.execute('''
            INSERT INTO chunks 
            (id, manual_id, text, heading, path, heading_num, level, 
             topic_id, is_emergency_procedure, emergency_category, units)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            chunk_id,
            manual_id,
            text,
            heading,
            path,
            heading_num,
            level,
            topic_id,
            1 if is_emergency else 0,
            emergency_category,
            json.dumps(units)
        ))
        
        # Register topic
        if topic_id and topic_id not in topics_seen:
            cursor.execute('''
                INSERT OR IGNORE INTO topics (topic_id, first_seen)
                VALUES (?, ?)
            ''', (topic_id, datetime.utcnow().isoformat()))
            topics_seen.add(topic_id)
        
        # Collect embeddings for FAISS
        embedding = chunk.get('embedding')
        if embedding:
            all_embeddings.append(embedding)
            all_chunk_ids.append(chunk_id)
        
        migrated_count += 1
        if migrated_count % 100 == 0:
            print(f"      Migrated {migrated_count}/{len(chunks)} chunks...")
    
    conn.commit()
    print(f"      ✓ Migrated {migrated_count} chunks with enhanced metadata")
    print(f"      ✓ Registered {len(topics_seen)} unique topics")
    
    # Create FAISS index
    print("\n[5/5] Building FAISS vector index...")
    if faiss and all_embeddings:
        embeddings_array = np.array(all_embeddings, dtype='float32')
        dimension = embeddings_array.shape[1]
        
        print(f"      Dimension: {dimension}")
        print(f"      Vectors: {len(all_embeddings)}")
        
        # Use IndexFlatIP for cosine similarity (after normalization)
        index = faiss.IndexFlatIP(dimension)
        
        # Normalize vectors for cosine similarity
        faiss.normalize_L2(embeddings_array)
        index.add(embeddings_array)
        
        # Save index
        faiss.write_index(index, FAISS_INDEX_PATH)
        
        # Save chunk ID mapping
        with open(FAISS_INDEX_PATH + ".ids", "w") as f:
            json.dump(all_chunk_ids, f)
        
        print(f"      ✓ FAISS index saved to {FAISS_INDEX_PATH}")
    elif not faiss:
        print("      ⚠ FAISS not available - skipping vector index")
    else:
        print("      ⚠ No embeddings found - skipping vector index")
    
    # Log migration
    cursor.execute('''
        INSERT INTO audit_log (timestamp, user, action, details)
        VALUES (?, ?, ?, ?)
    ''', (
        datetime.utcnow().isoformat(),
        'system',
        'migrate_database',
        f'Migrated {migrated_count} chunks from {DB_PATH}'
    ))
    
    conn.commit()
    conn.close()
    
    print("\n" + "="*80)
    print("MIGRATION COMPLETE!")
    print("="*80)
    print(f"\n✓ SQLite database: {SQLITE_DB_PATH}")
    if faiss and all_embeddings:
        print(f"✓ FAISS index: {FAISS_INDEX_PATH}")
    print(f"✓ Documents: {len(manuals)}")
    print(f"✓ Chunks: {migrated_count}")
    print(f"✓ Topics: {len(topics_seen)}")
    
    print(f"\nOriginal {DB_PATH} has been preserved.")
    print("You can now use the new SQLite database with manual_core.py")
    
    return True


def verify_migration():
    """Verify migration was successful."""
    print("\n" + "="*80)
    print("VERIFICATION")
    print("="*80)
    
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"\n✗ SQLite database not found: {SQLITE_DB_PATH}")
        return False
    
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    
    # Check documents
    cursor.execute("SELECT COUNT(*) FROM documents")
    doc_count = cursor.fetchone()[0]
    print(f"\n✓ Documents table: {doc_count} records")
    
    # Check chunks
    cursor.execute("SELECT COUNT(*) FROM chunks")
    chunk_count = cursor.fetchone()[0]
    print(f"✓ Chunks table: {chunk_count} records")
    
    # Check topics
    cursor.execute("SELECT COUNT(*) FROM topics")
    topic_count = cursor.fetchone()[0]
    print(f"✓ Topics table: {topic_count} records")
    
    # Check emergency procedures
    cursor.execute("SELECT COUNT(*) FROM chunks WHERE is_emergency_procedure = 1")
    emergency_count = cursor.fetchone()[0]
    print(f"✓ Emergency procedures: {emergency_count} chunks")
    
    # Check audit log
    cursor.execute("SELECT COUNT(*) FROM audit_log")
    audit_count = cursor.fetchone()[0]
    print(f"✓ Audit log: {audit_count} events")
    
    conn.close()
    
    # Check FAISS
    if os.path.exists(FAISS_INDEX_PATH):
        print(f"✓ FAISS index exists: {FAISS_INDEX_PATH}")
    else:
        print(f"⚠ FAISS index not found (optional)")
    
    print("\nVerification complete!")
    return True


if __name__ == "__main__":
    print("Manual Intelligence Engine - Database Migration Tool")
    print("This will migrate your db.json to SQLite + FAISS format.\n")
    
    success = migrate()
    
    if success:
        print("\nRunning verification...")
        verify_migration()
        
        print("\n" + "="*80)
        print("Next steps:")
        print("  1. Test the new database: python manual_core.py list")
        print("  2. Try new commands: python manual_core.py list-metadata")
        print("  3. If everything works, you can keep db.json as backup")
        print("="*80)
    else:
        print("\nMigration failed or was cancelled.")
        sys.exit(1)
