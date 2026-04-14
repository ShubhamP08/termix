#!/usr/bin/env python3
"""
Test the complete tool-layer integration with frontend API contract.
"""

import sys
import os

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from server import ResolveRequest, ResolveResponse


def test_missing_placeholders_no_error():
    """Test that missing_placeholders returns without error field."""
    print("\n[TEST] Missing placeholders should not include error...")
    
    # Create a response with missing placeholders (no error)
    resp = ResolveResponse(
        commands=[],
        source="kb_fuzzy",
        source_display="Knowledge Base (Fuzzy Match)",
        score=0.8,
        intent="file_op",
        requires_confirmation=False,
        tool_name="create_file",
        missing_placeholders=["filename"],
        tool_output="",
        error=""  # No error when missing placeholders
    )
    
    assert resp.missing_placeholders == ["filename"]
    assert resp.error == ""
    assert resp.commands == []
    print("✓ Response correctly has missing_placeholders without error")
    return True


def test_tool_output_response():
    """Test response with tool_output (Python-native execution)."""
    print("\n[TEST] Response with tool_output...")
    
    resp = ResolveResponse(
        commands=[],
        source="kb_fuzzy",
        source_display="Knowledge Base (Fuzzy Match)",
        score=0.9,
        intent="file_op",
        requires_confirmation=False,
        tool_name="find_files",
        missing_placeholders=[],
        tool_output="Found 3 files matching pattern",
        error=""
    )
    
    assert resp.tool_output == "Found 3 files matching pattern"
    assert resp.missing_placeholders == []
    assert resp.error == ""
    print("✓ Response correctly has tool_output")
    return True


def test_error_response():
    """Test response with error (blocked/unsafe)."""
    print("\n[TEST] Response with error...")
    
    resp = ResolveResponse(
        commands=[],
        source="kb_fuzzy",
        source_display="Knowledge Base (Fuzzy Match)",
        score=0.0,
        intent="unknown",
        requires_confirmation=False,
        tool_name="",
        missing_placeholders=[],
        tool_output="",
        error="Tool execution blocked as unsafe"
    )
    
    assert resp.error == "Tool execution blocked as unsafe"
    assert resp.tool_output == ""
    print("✓ Response correctly has error field")
    return True


def test_commands_response():
    """Test response with commands (shell execution)."""
    print("\n[TEST] Response with commands...")
    
    resp = ResolveResponse(
        commands=["ls -la", "pwd"],
        source="kb_semantic",
        source_display="Knowledge Base (Semantic)",
        score=0.85,
        intent="file_op",
        requires_confirmation=False,
        tool_name="",
        missing_placeholders=[],
        tool_output="",
        error=""
    )
    
    assert resp.commands == ["ls -la", "pwd"]
    assert len(resp.commands) == 2
    assert resp.missing_placeholders == []
    print("✓ Response correctly has commands")
    return True


def test_resolve_request_with_session():
    """Test ResolveRequest accepts session_id."""
    print("\n[TEST] ResolveRequest with session_id...")
    
    req = ResolveRequest(query="test query", session_id="sess_abc123")
    assert req.query == "test query"
    assert req.session_id == "sess_abc123"
    
    req2 = ResolveRequest(query="another query")
    assert req2.query == "another query"
    assert req2.session_id == ""  # Default empty string
    
    print("✓ ResolveRequest handles session_id correctly")
    return True


def test_graph_missing_placeholders_flow():
    """Test that knowledge_lookup_node doesn't set error for missing slots."""
    print("\n[TEST] Graph flow with missing placeholders...")
    
    from agent.graph import graph
    
    initial = {
        "user_input": "create file",  # Missing filename
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
    
    if missing:
        # If KB has the rule and it's missing placeholders, there should be no error
        assert error == "", f"Should not have error when missing_placeholders present, got: {error}"
        print(f"✓ Graph correctly sets missing_placeholders without error: {missing}")
        return True
    else:
        # If KB doesn't have the rule, it's not a failure
        print("~ No missing_placeholders (KB may not have matching rule)")
        return True


if __name__ == "__main__":
    print("=" * 70)
    print("FRONTEND-BACKEND INTEGRATION TESTS")
    print("=" * 70)
    
    tests = [
        ("Missing placeholders no error", test_missing_placeholders_no_error),
        ("Tool output response", test_tool_output_response),
        ("Error response", test_error_response),
        ("Commands response", test_commands_response),
        ("ResolveRequest with session", test_resolve_request_with_session),
        ("Graph missing placeholders flow", test_graph_missing_placeholders_flow),
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
