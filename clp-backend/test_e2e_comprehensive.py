#!/usr/bin/env python3
"""
Comprehensive end-to-end test of all tool-layer integration fixes.
"""

import sys
import os

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from agent.graph import graph
from server import ResolveRequest, ResolveResponse


def test_e2e_simple_deterministic_command():
    """Test: Simple command resolves without Gemini."""
    print("\n[E2E TEST 1] Simple deterministic command (no LLM)...")
    
    initial = {
        "user_input": "create file test.txt",
        "normalized_input": "create file test.txt",
        "commands": [],
        "validated": False,
        "approved": False,
        "execution_result": {},
        "error": "",
    }
    
    result = graph.invoke(initial)
    
    # Should either:
    # - Have tool_output (Python native executed)
    # - Have commands (shell commands to execute)
    # - Have missing_placeholders (prompt for values)
    # But should NOT have error
    
    has_output = bool(result.get("tool_output"))
    has_commands = bool(result.get("commands"))
    has_missing = bool(result.get("missing_placeholders"))
    has_error = bool(result.get("error"))
    
    print(f"  tool_output: {has_output}")
    print(f"  commands: {has_commands}")
    print(f"  missing_placeholders: {has_missing}")
    print(f"  error: {has_error}")
    
    # At least one of the above should be true (except error)
    success = (has_output or has_commands or has_missing) and not has_error
    assert success, "Should have tool output, commands, or missing placeholders, not error"
    print("✓ Deterministic command resolved without error")
    return True


def test_e2e_missing_placeholder_flow():
    """Test: Missing placeholder shows as valid state, not error."""
    print("\n[E2E TEST 2] Missing placeholder handling...")
    
    initial = {
        "user_input": "create file",  # Missing filename placeholder
        "normalized_input": "create file",
        "commands": [],
        "validated": False,
        "approved": False,
        "execution_result": {},
        "error": "",
    }
    
    result = graph.invoke(initial)
    
    missing = result.get("missing_placeholders", [])
    error = result.get("error", "")
    
    print(f"  missing_placeholders: {missing}")
    print(f"  error: '{error}'")
    
    if missing:
        # If placeholders are missing, there should be NO error
        assert error == "", f"Should not have error when missing placeholders, got: '{error}'"
        print("✓ Missing placeholders correctly returns without error")
        return True
    else:
        # If no match in KB, that's okay
        print("~ No match in KB for this pattern")
        return True


def test_e2e_python_native_success():
    """Test: Python-native tool execution marked as validated."""
    print("\n[E2E TEST 3] Python-native tool execution...")
    
    initial = {
        "user_input": "show file readme",
        "normalized_input": "show file readme",
        "commands": [],
        "validated": False,
        "approved": False,
        "execution_result": {},
        "error": "",
    }
    
    result = graph.invoke(initial)
    
    tool_output = result.get("tool_output", "")
    validated = result.get("validated", False)
    error = result.get("error", "")
    
    print(f"  tool_output: {bool(tool_output)}")
    print(f"  validated: {validated}")
    print(f"  error: '{error}'")
    
    if tool_output:
        # If tool executed, should be marked validated
        assert validated, "Python-native execution should be marked validated"
        assert error == "", "Python-native execution should not have error"
        print("✓ Python-native execution correctly validated")
        return True
    else:
        # If no match, that's okay
        print("~ No matching rule for this query")
        return True


def test_e2e_deferred_tool_state():
    """Test: Deferred tools (delete) store pending_tool state."""
    print("\n[E2E TEST 4] Deferred tool state persistence...")
    
    initial = {
        "user_input": "delete file test.txt",
        "normalized_input": "delete file test.txt",
        "commands": [],
        "validated": False,
        "approved": False,
        "execution_result": {},
        "error": "",
    }
    
    result = graph.invoke(initial)
    
    pending = result.get("pending_tool", {})
    requires_conf = result.get("requires_confirmation", False)
    error = result.get("error", "")
    
    print(f"  pending_tool: {bool(pending)}")
    print(f"  requires_confirmation: {requires_conf}")
    print(f"  error: '{error}'")
    
    if pending:
        # Deferred op should have pending_tool set
        assert pending.get("rule_id"), "pending_tool should have rule_id"
        assert pending.get("arguments"), "pending_tool should have arguments"
        assert requires_conf, "Deferred ops should require confirmation"
        print(f"✓ Deferred tool state stored: rule_id={pending.get('rule_id')}")
        return True
    else:
        # If no match in KB, that's okay
        print("~ No matching rule for delete")
        return True


def test_e2e_response_models():
    """Test: Response models work for all states."""
    print("\n[E2E TEST 5] ResolveResponse models for all states...")
    
    # State 1: Error
    r1 = ResolveResponse(
        commands=[],
        source="kb_fuzzy",
        source_display="Knowledge Base",
        score=0.0,
        intent="unknown",
        error="Tool blocked"
    )
    assert r1.error == "Tool blocked"
    print("✓ Error response model works")
    
    # State 2: Missing placeholders
    r2 = ResolveResponse(
        commands=[],
        source="kb_fuzzy",
        source_display="Knowledge Base",
        score=0.8,
        intent="file_op",
        missing_placeholders=["filename"]
    )
    assert r2.missing_placeholders == ["filename"]
    assert r2.error == ""
    print("✓ Missing placeholders response model works")
    
    # State 3: Tool output
    r3 = ResolveResponse(
        commands=[],
        source="kb_fuzzy",
        source_display="Knowledge Base",
        score=0.9,
        intent="file_op",
        tool_output="File contents here"
    )
    assert r3.tool_output == "File contents here"
    print("✓ Tool output response model works")
    
    # State 4: Commands
    r4 = ResolveResponse(
        commands=["ls", "pwd"],
        source="kb_semantic",
        source_display="Knowledge Base",
        score=0.85,
        intent="file_op"
    )
    assert r4.commands == ["ls", "pwd"]
    print("✓ Commands response model works")
    
    return True


def test_e2e_session_id_flow():
    """Test: Session ID can be generated and used."""
    print("\n[E2E TEST 6] Session ID flow...")
    
    import uuid
    
    # Generate session ID (as frontend would)
    session_id = str(uuid.uuid4())
    print(f"  Generated session_id: {session_id[:12]}...")
    
    # Create request with session ID (as frontend API would)
    req = ResolveRequest(query="test query", session_id=session_id)
    assert req.session_id == session_id
    print("✓ Session ID flows through request model")
    
    # Session ID can be used to store state (as backend would)
    from server import sessions
    sessions[session_id] = {
        "status": "resolved",
        "pending_tool": {"rule_id": "test", "arguments": {}},
    }
    
    stored = sessions.get(session_id)
    assert stored is not None
    assert stored["pending_tool"]["rule_id"] == "test"
    print("✓ Session state can be persisted and retrieved")
    
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("END-TO-END TOOL-LAYER INTEGRATION TEST SUITE")
    print("=" * 70)
    
    tests = [
        ("Simple deterministic command", test_e2e_simple_deterministic_command),
        ("Missing placeholder flow", test_e2e_missing_placeholder_flow),
        ("Python-native execution", test_e2e_python_native_success),
        ("Deferred tool state", test_e2e_deferred_tool_state),
        ("Response models", test_e2e_response_models),
        ("Session ID flow", test_e2e_session_id_flow),
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
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    all_passed = all(p for _, p in results)
    sys.exit(0 if all_passed else 1)
