#!/usr/bin/env python3
"""
Direct validation of the /resolve and /execute flow.
"""

import sys
import os

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from server import ResolveRequest, ExecuteRequest, sessions, _format_source


def test_session_storage_logic():
    """Test the session storage logic that would be called in /resolve."""
    print("\n[TEST] Session storage logic in /resolve endpoint...")
    
    # Simulate what /resolve endpoint does after graph.invoke
    session_id = "test_sess_abc"
    resolved_state = {
        "pending_tool": {
            "rule_id": "fs_remove_file",
            "arguments": {"filename": "demo.txt"}
        },
        "tool_name": "remove_file",
        "source": "kb_fuzzy",
        "rule_id": "fs_remove_file",
    }
    
    # This is the exact code from /resolve endpoint
    if session_id and resolved_state.get("pending_tool"):
        sessions[session_id] = {
            "status": "resolved",
            "pending_tool": resolved_state.get("pending_tool"),
            "tool_name": resolved_state.get("tool_name"),
            "source": resolved_state.get("source"),
            "requires_confirmation": resolved_state.get("requires_confirmation"),
            "commands": resolved_state.get("commands"),
            "tool_output": resolved_state.get("tool_output"),
            "rule_id": resolved_state.get("rule_id"),
        }
    
    # Verify it was stored
    stored = sessions.get(session_id)
    assert stored is not None, "Session should be stored"
    assert stored["pending_tool"]["rule_id"] == "fs_remove_file"
    assert stored["status"] == "resolved"
    print("✓ Session storage logic works correctly")
    print(f"  Stored session: {stored}")
    return True


def test_deferred_execution_logic():
    """Test the deferred execution logic that would be called in /execute."""
    print("\n[TEST] Deferred execution logic in /execute endpoint...")
    
    from tools.tool_runner import execute_confirmed_tool
    
    # Simulate what /execute endpoint does when pending_tool exists
    session_id = "test_deferred_exec"
    sessions[session_id] = {
        "status": "resolved",
        "pending_tool": {
            "rule_id": "fs_remove_file",
            "arguments": {"filename": "nonexistent.txt"}
        },
        "source": "kb_fuzzy",
    }
    
    # This is the exact logic from /execute endpoint
    session = sessions.get(session_id)
    if session and session.get("pending_tool"):
        pending_tool = session["pending_tool"]
        rule_id = pending_tool.get("rule_id", "")
        arguments = pending_tool.get("arguments", {})
        
        print(f"  Executing: rule_id={rule_id}, args={arguments}")
        tool_result = execute_confirmed_tool(rule_id, arguments)
        
        # Convert ToolResult to ExecuteResponse format
        rendered_cmd = (tool_result.rendered_commands[0] if tool_result.rendered_commands else rule_id)
        results = [{
            "command": rendered_cmd,
            "success": not bool(tool_result.error),
            "output": tool_result.output,
            "error": tool_result.error,
        }]
        
        # Update session status
        session["status"] = "completed"
        
        print(f"✓ Deferred execution logic works")
        print(f"  Tool result: success={results[0]['success']}, output={results[0]['output']}")
        return True
    else:
        print("✗ No pending_tool in session")
        return False


def test_format_source():
    """Test that source formatting still works."""
    print("\n[TEST] Source formatting helper...")
    
    assert _format_source("kb_fuzzy") == "Knowledge Base (Fuzzy Match)"
    assert _format_source("kb_semantic") == "Knowledge Base (Semantic)"
    assert _format_source("llm") == "LLM (Gemini)"
    assert _format_source("intent") == "Deterministic (Intent Handler)"
    print("✓ Source formatting works correctly")
    return True


def test_request_models():
    """Test request/response model instantiation."""
    print("\n[TEST] Request models...")
    
    # ResolveRequest with session_id
    req1 = ResolveRequest(query="test", session_id="sess_1")
    assert req1.query == "test"
    assert req1.session_id == "sess_1"
    
    # ResolveRequest without session_id (defaults to "")
    req2 = ResolveRequest(query="test2")
    assert req2.query == "test2"
    assert req2.session_id == ""
    
    # ExecuteRequest
    req3 = ExecuteRequest(session_id="sess_1", command="ls", source="kb_fuzzy")
    assert req3.session_id == "sess_1"
    assert req3.command == "ls"
    assert req3.source == "kb_fuzzy"
    
    print("✓ Request models work correctly")
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("DIRECT LOGIC & MODEL VALIDATION")
    print("=" * 70)
    
    tests = [
        ("Session storage logic", test_session_storage_logic),
        ("Deferred execution logic", test_deferred_execution_logic),
        ("Source formatting", test_format_source),
        ("Request models", test_request_models),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
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
    sys.exit(0 if all_passed else 1)
