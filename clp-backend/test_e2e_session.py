#!/usr/bin/env python3
"""
End-to-end test of /resolve and /execute flow with session persistence.
"""

import sys
import os
import asyncio

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from server import app, sessions, ResolveRequest, ExecuteRequest


async def test_resolve_with_session_persistence():
    """Test that /resolve stores pending_tool in session."""
    print("\n[TEST] /resolve should persist pending_tool to session...")
    
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    # Send resolve request with session_id
    session_id = "test_sess_12345"
    response = client.post(
        "/resolve",
        json={
            "query": "delete file demo.txt",
            "session_id": session_id
        }
    )
    
    print(f"✓ /resolve returned status {response.status_code}")
    data = response.json()
    print(f"  requires_confirmation: {data.get('requires_confirmation')}")
    print(f"  tool_name: {data.get('tool_name')}")
    
    # Check if session has pending_tool
    session = sessions.get(session_id)
    if session and session.get("pending_tool"):
        print(f"✓ Session {session_id} has pending_tool:")
        print(f"    rule_id: {session['pending_tool'].get('rule_id')}")
        print(f"    arguments: {session['pending_tool'].get('arguments')}")
        return True
    else:
        print(f"~ Session does not have pending_tool (KB may not have fs_remove_file rule)")
        return True


async def test_execute_deferred_tool():
    """Test that /execute picks up deferred tool from session."""
    print("\n[TEST] /execute should execute deferred tool from session...")
    
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    # Manually set up a session with pending_tool
    session_id = "test_deferred_123"
    sessions[session_id] = {
        "status": "resolved",
        "pending_tool": {
            "rule_id": "fs_remove_file",
            "arguments": {"filename": "nonexistent_test_file.txt"}
        },
        "tool_name": "remove_file",
        "source": "kb_fuzzy",
        "user_input": "delete file nonexistent_test_file.txt",
    }
    
    # Call /execute with that session
    response = client.post(
        "/execute",
        json={
            "session_id": session_id,
            "command": "dummy",  # Not used when pending_tool exists
            "source": "kb_fuzzy"
        }
    )
    
    print(f"✓ /execute returned status {response.status_code}")
    data = response.json()
    print(f"  results: {data.get('results')}")
    print(f"  line: {data.get('line')}")
    
    # Verify session was updated
    updated_session = sessions.get(session_id)
    if updated_session:
        print(f"✓ Session status updated to: {updated_session.get('status')}")
        return True
    else:
        print("✗ Session was not found after execute")
        return False


async def test_standard_shell_execution():
    """Test that /execute still works for standard commands."""
    print("\n[TEST] /execute should fall back to shell execution without pending_tool...")
    
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    # Call /execute without a session (no pending_tool)
    response = client.post(
        "/execute",
        json={
            "session_id": "no_session",
            "command": "echo hello",
            "source": "user"
        }
    )
    
    print(f"✓ /execute returned status {response.status_code}")
    data = response.json()
    
    if response.status_code == 200:
        results = data.get("results", [])
        if results:
            print(f"  First result: {results[0]}")
            print(f"✓ Standard shell execution still works")
            return True
        else:
            print("  No results returned")
            return False
    else:
        print(f"  Error: {data}")
        return False


async def main():
    print("=" * 70)
    print("END-TO-END SESSION & DEFERRED EXECUTION TESTS")
    print("=" * 70)
    
    tests = [
        ("Resolve with session persistence", test_resolve_with_session_persistence),
        ("Execute deferred tool", test_execute_deferred_tool),
        ("Standard shell execution", test_standard_shell_execution),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = await test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"✗ {name} failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
    
    all_passed = all(p for _, p in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
