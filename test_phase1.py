#!/usr/bin/env python3
"""
Basic tests for Phase 1 functionality.
Tests helper functions, database operations, and metadata extraction.
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime

# Import functions to test
from manual_core import (
    generate_topic_id,
    detect_emergency_procedure,
    extract_units,
    detect_doc_type,
    init_sqlite_db,
    get_db_connection,
    log_audit_event,
    SQLITE_DB_PATH
)


def test_topic_id_generation():
    """Test that topic_id generation is deterministic and correct."""
    print("\n=== Testing Topic ID Generation ===")
    
    test_cases = [
        ("1.5 Bailout Gas Requirements", "bailout_gas_requirements"),
        ("3.2.1 Deck Decompression Chamber Operation", "deck_decompression_chamber_operation"),
        ("EMERGENCY PROCEDURES", "emergency_procedures"),
        ("2 DIVING OPERATIONS", "diving_operations"),
        ("Safety Equipment", "safety_equipment"),
        ("", ""),
    ]
    
    passed = 0
    failed = 0
    
    for input_text, expected in test_cases:
        result = generate_topic_id(input_text)
        if result == expected:
            print(f"  ✓ '{input_text}' → '{result}'")
            passed += 1
        else:
            print(f"  ✗ '{input_text}' → '{result}' (expected: '{expected}')")
            failed += 1
    
    # Test determinism (same input = same output)
    test_heading = "1.5 Bailout Gas Requirements"
    result1 = generate_topic_id(test_heading)
    result2 = generate_topic_id(test_heading)
    if result1 == result2:
        print(f"  ✓ Deterministic: '{test_heading}' always gives '{result1}'")
        passed += 1
    else:
        print(f"  ✗ Not deterministic: got different results")
        failed += 1
    
    return passed, failed


def test_emergency_detection():
    """Test emergency procedure detection."""
    print("\n=== Testing Emergency Detection ===")
    
    test_cases = [
        ("This describes bailout gas requirements", "Bailout Gas", True, "bailout"),
        ("Emergency procedures for equipment failure", "Emergency", True, "equipment_failure"),  # "equipment failure" keyword matched first in new ruleset
        ("Abort procedures in case of weather", "Weather Abort", True, "abort"),  # "abort" keyword matched first
        ("Normal diving operations", "Standard Ops", False, None),
        ("Medical emergency requiring first aid", "Medical Emergency", True, "medical"),  # Using "medical emergency" keyword
    ]
    
    passed = 0
    failed = 0
    
    for text, heading, expected_is_em, expected_cat in test_cases:
        is_em, cat = detect_emergency_procedure(text, heading)
        if is_em == expected_is_em and (not expected_is_em or cat == expected_cat):
            print(f"  ✓ '{heading}': is_emergency={is_em}, category={cat}")
            passed += 1
        else:
            print(f"  ✗ '{heading}': got ({is_em}, {cat}), expected ({expected_is_em}, {expected_cat})")
            failed += 1
    
    return passed, failed


def test_unit_extraction():
    """Test unit extraction from text."""
    print("\n=== Testing Unit Extraction ===")
    
    test_cases = [
        ("The depth is 30 metres", [("30", "meters")]),
        ("Pressure must be 50 bar minimum", [("50", "bar")]),
        ("Tank capacity is 3000 psi or 200 bar", [("3000", "psi"), ("200", "bar")]),
        ("Distance of 100 feet", [("100", "feet")]),
        ("Volume is 12 litres or 0.42 cf", [("12", "litres"), ("0.42", "cubic_feet")]),
        ("No units in this text", []),
    ]
    
    passed = 0
    failed = 0
    
    for text, expected_units in test_cases:
        units = extract_units(text)
        found_units = [(u['value'], u['unit']) for u in units]
        
        if len(found_units) == len(expected_units) and all(u in found_units for u in expected_units):
            print(f"  ✓ '{text[:50]}...' → {len(found_units)} units")
            passed += 1
        else:
            print(f"  ✗ '{text[:50]}...' → found {found_units}, expected {expected_units}")
            failed += 1
    
    return passed, failed


def test_doc_type_detection():
    """Test document type auto-detection."""
    print("\n=== Testing Document Type Detection ===")
    
    test_cases = [
        ("Manual - Diving Operations.txt", "manual"),
        ("IMCA D014 Standard.txt", "standard"),
        ("Safety Guidance Document.txt", "guidance"),
        ("HSE Diving Regulations Act.txt", "legislation"),  # "act" keyword will match
        ("Client Specification.txt", "client_spec"),
        ("Procedure Manual.txt", "manual"),
    ]
    
    passed = 0
    failed = 0
    
    for filename, expected_type in test_cases:
        doc_type = detect_doc_type(filename)
        if doc_type == expected_type:
            print(f"  ✓ '{filename}' → '{doc_type}'")
            passed += 1
        else:
            print(f"  ✗ '{filename}' → '{doc_type}' (expected: '{expected_type}')")
            failed += 1
    
    return passed, failed


def test_database_operations():
    """Test SQLite database initialization and operations."""
    print("\n=== Testing Database Operations ===")
    
    # Use a temporary database for testing
    test_db = "test_manual_data.db"
    
    # Clean up if exists
    if os.path.exists(test_db):
        os.remove(test_db)
    
    passed = 0
    failed = 0
    
    # Temporarily override DB path
    import manual_core
    original_db_path = manual_core.SQLITE_DB_PATH
    manual_core.SQLITE_DB_PATH = test_db
    
    try:
        # Test 1: Initialize database
        init_sqlite_db()
        if os.path.exists(test_db):
            print(f"  ✓ Database created: {test_db}")
            passed += 1
        else:
            print(f"  ✗ Database not created")
            failed += 1
        
        # Test 2: Check tables
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        expected_tables = {'documents', 'chunks', 'topics', 'audit_log'}
        
        if expected_tables.issubset(set(tables)):
            print(f"  ✓ All required tables created: {', '.join(expected_tables)}")
            passed += 1
        else:
            print(f"  ✗ Missing tables. Found: {tables}")
            failed += 1
        
        conn.close()
        
        # Test 3: Audit logging
        log_audit_event("test_action", "Test event details")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_log")
        count = cursor.fetchone()[0]
        
        if count == 1:
            print(f"  ✓ Audit event logged successfully")
            passed += 1
        else:
            print(f"  ✗ Audit log count incorrect: {count}")
            failed += 1
        
        # Test 4: Verify audit log content
        cursor.execute("SELECT action, details, user FROM audit_log")
        row = cursor.fetchone()
        
        if row and row[0] == "test_action" and row[1] == "Test event details" and row[2] == "system":
            print(f"  ✓ Audit log content correct")
            passed += 1
        else:
            print(f"  ✗ Audit log content incorrect: {row}")
            failed += 1
        
        conn.close()
        
    finally:
        # Restore original DB path
        manual_core.SQLITE_DB_PATH = original_db_path
        
        # Clean up test database
        if os.path.exists(test_db):
            os.remove(test_db)
    
    return passed, failed


def main():
    """Run all tests."""
    print("="*70)
    print("PHASE 1 FUNCTIONALITY TESTS")
    print("="*70)
    
    total_passed = 0
    total_failed = 0
    
    # Run all test suites
    test_suites = [
        test_topic_id_generation,
        test_emergency_detection,
        test_unit_extraction,
        test_doc_type_detection,
        test_database_operations,
    ]
    
    for test_func in test_suites:
        try:
            passed, failed = test_func()
            total_passed += passed
            total_failed += failed
        except Exception as e:
            print(f"\n  ✗ Test suite failed with error: {e}")
            import traceback
            traceback.print_exc()
            total_failed += 1
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"  Passed: {total_passed}")
    print(f"  Failed: {total_failed}")
    print(f"  Total:  {total_passed + total_failed}")
    
    if total_failed == 0:
        print("\n  ✓ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n  ✗ {total_failed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
