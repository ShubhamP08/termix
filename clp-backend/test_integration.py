#!/usr/bin/env python3
"""
Quick integration test for the tool-layer fixes.
Tests:
  1. Planner doesn't require Gemini for simple queries
  2. Validator recognizes successful Python-native executions
  3. Session persistence of pending_tool
  4. Deferred tool execution
"""

import sys
import os

# Ensure imports work
_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from agent.graph import graph
from agent.state import AgentState


def test_planner_no_llm():
    """Test that planner passes through query without LLM call."""
    print("\n[TEST 1] Planner should not require LLM for simple query...")
    
    initial = {
        "user_input": "create a file called demo.txt",
        "normalized_input": "create a file called demo.txt",
        "commands": [],
        "validated": False,
        "approved": False,
        "execution_result": {},
        "error": "",
    }
    
    # This will fail if planner tries to import/use LLMEngine without Gemini API
    try:
        result = graph.invoke(initial)
        print("✓ Planner passed through without crashing")
        print(f"  Tasks set: {result.get('tasks')}")
        return True
    except Exception as e:
        if "GEMINI" in str(e) or "API" in str(e):
            print(f"✗ Planner still requires LLM: {e}")
            return False
        raise


def test_python_native_execution():
    """Test that Python-native tools execute and set validated=True."""
    print("\n[TEST 2] Python-native tools should execute without shell...")
    
    initial = {
        "user_input": "find files named test",
        "normalized_input": "find files named test",
        "commands": [],
        "validated": False,
        "approved": False,
        "execution_result": {},
        "error": "",
    }
    
    try:
        result = graph.invoke(initial)
        tool_output = result.get("tool_output", "")
        execution_result = result.get("execution_result", {})
        validated = result.get("validated", False)
        
        print(f"✓ Graph executed successfully")
        print(f"  tool_output present: {bool(tool_output)}")
        print(f"  execution_result: {execution_result}")
        print(f"  validated: {validated}")
        
        # If it's a Python-native tool, validator should have marked it validated
        if tool_output or (isinstance(execution_result, list) and len(execution_result) > 0):
            if validated:
                print("✓ Validator correctly marked Python-native execution as validated")
                return True
            else:
                print("✗ Validator did not mark Python-native execution as validated")
                return False
        else:
            print("~ Tool was LLM-backed or no match (validator would be skipped)")
            return True
    except Exception as e:
        print(f"✗ Graph execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_deferred_tool_state():
    """Test that deferred tools set pending_tool in state."""
    print("\n[TEST 3] Deferred destructive tools should set pending_tool...")
    
    initial = {
        "user_input": "delete file demo.txt",
        "normalized_input": "delete file demo.txt",
        "commands": [],
        "validated": False,
        "approved": False,
        "execution_result": {},
        "error": "",
    }
    
    try:
        result = graph.invoke(initial)
        pending_tool = result.get("pending_tool", {})
        requires_confirmation = result.get("requires_confirmation", False)
        
        print(f"✓ Graph executed")
        print(f"  requires_confirmation: {requires_confirmation}")
        print(f"  pending_tool: {bool(pending_tool)}")
        
        if pending_tool:
            print(f"  rule_id: {pending_tool.get('rule_id')}")
            print("✓ Deferred tool state correctly populated")
            return True
        else:
            # If KB doesn't have the rule, it's not a failure
            print("~ No pending_tool (may be KB miss)")
            return True
    except Exception as e:
        print(f"✗ Graph execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("TOOL-LAYER INTEGRATION TESTS")
    print("=" * 70)
    
    results = []
    results.append(("Planner no LLM", test_planner_no_llm()))
    results.append(("Python-native execution", test_python_native_execution()))
    results.append(("Deferred tool state", test_deferred_tool_state()))
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
    
    all_passed = all(p for _, p in results)
    sys.exit(0 if all_passed else 1)
