const DEFAULT_BASE = 'http://127.0.0.1:8000';

function baseUrl() {
  return (import.meta.env.VITE_API_BASE || DEFAULT_BASE).replace(/\/$/, '');
}

async function parseJsonResponse(res) {
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(
      res.ok
        ? `Invalid JSON from server: ${text.slice(0, 200)}`
        : `HTTP ${res.status}: ${text.slice(0, 200)}`
    );
  }

  if (!res.ok) {
    const msg =
      data.detail != null
        ? typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail)
        : data.message || data.error || `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    err.data = data;
    throw err;
  }

  return data;
}

/**
 * POST /resolve — resolve a natural language query into commands.
 * Returns: { commands: string[], source: string, source_display: string, intent: string, error?: string, missing_placeholders?: string[], tool_output?: string }
 */
export async function resolveQuery(query, session_id = '') {
  const res = await fetch(`${baseUrl()}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ query, session_id }),
  });
  return parseJsonResponse(res);
}

/**
 * POST /execute — execute approved commands.
 * Returns: { results: Array<{command, success, output, error}>, line: string }
 */
export async function executeCommands(session_id, commands, source) {
  // Join multiple commands with ||| separator for the server
  const commandStr = Array.isArray(commands) ? commands.join('|||') : commands;
  const res = await fetch(`${baseUrl()}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ session_id, command: commandStr, source }),
  });
  return parseJsonResponse(res);
}

/** POST /input */
export async function sendInteractiveInput(session_id, input) {
  const res = await fetch(`${baseUrl()}/input`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ session_id, input }),
  });
  return parseJsonResponse(res);
}

/** GET /status */
export async function getInteractiveStatus(session_id) {
  const q = new URLSearchParams({ session_id });
  const res = await fetch(`${baseUrl()}/status?${q}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return parseJsonResponse(res);
}

/** GET /health */
export async function checkHealth() {
  const res = await fetch(`${baseUrl()}/health`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal: AbortSignal.timeout(3000),
  });
  return parseJsonResponse(res);
}
