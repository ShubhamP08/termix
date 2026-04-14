## Frontend-Backend Integration Fixes - Summary

### Overview
Fixed frontend-backend integration issues to properly handle:
1. Session ID persistence across resolve/execute flow
2. Missing placeholder prompt states (not treated as errors)
3. Python-native tool output display
4. Proper state machine transitions in the terminal UI

---

## Changes Made

### Backend Changes

#### 1. **Validator Node - Missing Placeholders Not an Error**
**File:** [agent/nodes.py](agent/nodes.py#L214-L264)

**Change:** Added special handling for missing_placeholders state
- Before: validator_node would set `error="No commands generated"` when there were no commands
- After: When `missing_placeholders` is present, validator sets `validated=False` but does NOT set an error
- This correctly recognizes that missing placeholders is a valid prompt-for-input state, not a failure

**Code added (line 238-244):**
```python
# Check if we're waiting for user to provide missing placeholders — not an error
missing = state.get("missing_placeholders") or []
if missing:
    # Missing placeholders is a valid prompt-for-input state, not an error
    state["validated"] = False
    state["error"] = ""  # Do not set error for missing placeholders
    logger.debug("[validator] awaiting missing placeholders, no error set")
    return state
```

**Impact:** Missing placeholder responses are no longer treated as errors by the backend.

---

### Frontend Changes

#### 1. **API Service - Send session_id with /resolve**
**File:** [termix-cli/src/services/api.js](termix-cli/src/services/api.js#L36-L45)

**Change:** Updated `resolveQuery()` function signature
- Before: `resolveQuery(query)` - only took query parameter
- After: `resolveQuery(query, session_id = '')` - optional session_id parameter with empty string default
- The session_id is now sent with the POST request to `/resolve`

**Code:**
```javascript
export async function resolveQuery(query, session_id = '') {
  const res = await fetch(`${baseUrl()}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ query, session_id }),
  });
  return parseJsonResponse(res);
}
```

**Impact:** Backend can now persist deferred tool state in sessions across the resolve→execute flow.

---

#### 2. **Terminal UI - Proper State Handling for All Resolve Cases**
**File:** [termix-cli/src/components/TerminalUI.jsx](termix-cli/src/components/TerminalUI.jsx#L200-L275)

**Changes:** Restructured resolve response handling with proper precedence:

1. **Call /resolve with session_id** (line 213):
   ```javascript
   const r = await resolveQuery(query, sid);
   ```

2. **Handle error state** (lines 216-221):
   - If `r.error` exists → show as blocked/error and reset

3. **Handle missing placeholders** (lines 223-231):
   - If `r.missing_placeholders.length > 0` → show which placeholders are needed
   - Stay in 'idle' state to allow user input for those values
   - **Don't treat as error** — it's a valid prompt-for-input state

4. **Handle tool_output** (lines 233-240):
   - If `r.tool_output && r.tool_output.trim()` → Python-native tool executed successfully
   - Show output as success immediately
   - Reset flow (no confirmation needed)

5. **Handle commands** (lines 242-263):
   - If `r.commands && r.commands.length > 0` → use existing confirmation flow
   - Show generated commands with [y/N] confirmation prompt

6. **Handle no result** (lines 265-267):
   - Only show "No commands generated" if none of the above apply

**Code structure:**
```javascript
// Handle error state
if (r.error) { ... }

// Handle missing placeholders — prompt user for more input
if (r.missing_placeholders && r.missing_placeholders.length > 0) { 
  appendLines(...);
  setFlowStep('idle');  // Back to idle for user input
  return;
}

// Handle tool_output — Python-native tool executed successfully
if (r.tool_output && r.tool_output.trim()) { ... }

// Handle commands — show confirmation
if (r.commands && r.commands.length > 0) { ... }

// No commands, no output, no missing placeholders, no error
appendLines(setOutput, 'error', ['No commands generated.']);
```

**Impact:** 
- Terminal UI now properly shows missing placeholder prompts without treating them as errors
- Python-native tool output is displayed immediately as success
- Shell commands still go through confirmation flow
- Better UX with clear state transitions

---

## Verification

### Test Results
All integration tests pass:

**Backend Integration Tests (test_integration.py):**
- ✓ Planner passes through without requiring Gemini
- ✓ Python-native tools execute and mark validated correctly  
- ✓ Deferred tool state properly populated

**API Contract Tests (test_api_contract.py):**
- ✓ ResolveRequest.session_id field accepted
- ✓ ExecuteRequest contract maintained
- ✓ Response models compatible
- ✓ Validator node logic correct (missing placeholders no error)
- ✓ Planner node pass-through working

**Frontend Integration Tests (test_frontend_integration.py):**
- ✓ Missing placeholders response has no error
- ✓ Tool output response works correctly
- ✓ Error response works correctly
- ✓ Commands response works correctly
- ✓ ResolveRequest handles session_id correctly
- ✓ Graph flow with missing placeholders doesn't set error

**Compilation:**
- ✓ All backend files compile without errors
- ✓ JavaScript syntax valid

---

## State Machine Flow (Updated)

### /resolve Endpoint
```
Query → Backend processes → Returns one of:
  1. error + message → Show blocked/error
  2. missing_placeholders → Show prompt for values (return to idle)
  3. tool_output → Show output as success
  4. commands → Show confirmation prompt
  5. nothing → Show "No commands generated"
```

### Frontend State Transitions
```
idle → (submit query) → resolve
  ├→ error: show error, stay idle
  ├→ missing_placeholders: show prompt, stay idle
  ├→ tool_output: show output, back to idle
  ├→ commands: show confirmation, change to 'confirm'
  └→ nothing: show error, stay idle

confirm → (yes/y) → execute (via /execute)
confirm → (no/n) → back to idle
```

---

## Key Design Decisions

1. **Missing Placeholders ≠ Error**: Missing placeholders are a valid state that prompts the user for more input, not a failure condition. The backend no longer sets an error message for this state.

2. **Session ID Persistence**: Session IDs are now generated on the frontend and passed with /resolve to enable backend to store deferred tool state for later execution in /execute.

3. **Deterministic Ordering in Frontend**: The terminal UI checks resolve states in a specific order:
   - Error first (blocking state)
   - Missing placeholders (prompt-for-input)
   - Tool output (immediate success)
   - Commands (confirmation needed)
   - Nothing (error)
   
   This ensures proper UX flow.

4. **No Error Message for Missing Placeholders**: When placeholders are missing, the response has no error field — this signals to the frontend that it's a prompt state, not an error state.
