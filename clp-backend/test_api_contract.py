#!/usr/bin/env python3
"""
Test the HTTP API changes for session persistence and deferred execution.
"""

import sys
import os
import json

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from server import ResolveRequest, ExecuteRequest, ResolveResponse, ExecuteResponse


def test_resolve_request_has_session_id():
    """Verify ResolveRequest now accepts session_id."""
    print("\n[TEST] ResolveRequest should accept session_id...")
    
    # Create request with session_id
    req = ResolveRequest(query="test query", session_id="sess_123")
    assert req.query == "test query"
    assert req.session_id == "sess_123"
    print("✓ ResolveRequest accepts session_id")
    
    # Create request without session_id (should default to "")
    req2 = ResolveRequest(query="test query")
    assert req2.query == "test query"
    assert req2.session_id == ""
    print("✓ ResolveRequest session_id is optional with default empty")
    
    return True


def test_execute_request_structure():
    """Verify ExecuteRequest contract."""
    print("\n[TEST] ExecuteRequest should have session_id, command, source...")
    
    req = ExecuteRequest(
        session_id="sess_123",
        command="ls",
        source="kb_fuzzy"
    )
    assert req.session_id == "sess_123"
    assert req.command == "ls"
    assert req.source == "kb_fuzzy"
    print("✓ ExecuteRequest has all required fields")
    
    return True


def test_response_models_compatible():
    """Verify response models still have expected fields."""
    print("\n[TEST] Response models should have expected fields...")
    
    # ResolveResponse
    resp = ResolveResponse(
        commands=["ls"],
        source="kb_fuzzy",
        source_display="Knowledge Base (Fuzzy Match)",
        score=0.95,
        intent="file_op",
        requires_confirmation=False,
        tool_name="find_files",
        missing_placeholders=[],
        tool_output="",
        error=""
    )
    assert resp.commands == ["ls"]
    assert resp.source == "kb_fuzzy"
    assert resp.tool_output == ""
    print("✓ ResolveResponse has expected fields")
    
    # ExecuteResponse
    exec_resp = ExecuteResponse(
        results=[{"command": "ls", "success": True, "output": "test", "error": ""}],
        line="success"
    )
    assert len(exec_resp.results) == 1
    assert exec_resp.results[0]["success"] is True
    print("✓ ExecuteResponse has expected fields")
    
    return True


def test_validation_helper():
    """Test validator node directly."""
    print("\n[TEST] Validator should recognize Python-native execution...")
    
    from agent.nodes import validator_node
    from agent.state import AgentState
    
    # Case 1: execution_result with success=True
    state1: AgentState = {
        "commands": [],
        "execution_result": [{"success": True, "output": "test"}],
        "validated": False,
        "error": "",
    }
    result1 = validator_node(state1)
    assert result1["validated"] is True, "Should mark validated when execution_result has success"
    assert result1.get("error") == "", "Should not set error for successful execution"
    print("✓ Validator recognizes successful execution_result")
    
    # Case 2: tool_output with no error
    state2: AgentState = {
        "commands": [],
        "tool_output": "file created",
        "validated": False,
        "error": "",
    }
    result2 = validator_node(state2)
    assert result2["validated"] is True, "Should mark validated when tool_output exists"
    print("✓ Validator recognizes tool_output")
    
    # Case 3: no commands, no execution_result → should error
    state3: AgentState = {
        "commands": [],
        "execution_result": {},
        "tool_output": "",
        "validated": False,
    }
    result3 = validator_node(state3)
    assert result3["validated"] is False, "Should not validate empty state"
    assert "No commands generated" in result3.get("error", ""), "Should set appropriate error"
    print("✓ Validator rejects empty state")
    
    return True


def test_planner_pass_through():
    """Test planner node directly."""
    print("\n[TEST] Planner should pass through without LLM...")
    
    from agent.nodes import planner_node
    from agent.state import AgentState
    
    state: AgentState = {
        "normalized_input": "create a file called test.txt",
    }
    result = planner_node(state)
    assert result["tasks"] == ["create a file called test.txt"], "Should set tasks to normalized input"
    print("✓ Planner sets tasks from normalized_input")
    
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("API CONTRACT & VALIDATOR TESTS")
    print("=" * 70)
    
    tests = [
        ("ResolveRequest.session_id", test_resolve_request_has_session_id),
        ("ExecuteRequest contract", test_execute_request_structure),
        ("Response models", test_response_models_compatible),
        ("Validator node logic", test_validation_helper),
        ("Planner node logic", test_planner_pass_through),
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
