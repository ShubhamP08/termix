import React, { useState, useEffect, useRef, useCallback } from 'react';
import OutputLine from './OutputLine.jsx';
import {
  resolveQuery,
  executeCommands,
  sendInteractiveInput,
  getInteractiveStatus,
  checkHealth,
} from '../services/api.js';

function appendLines(setOutput, type, lines) {
  const id = Date.now() + Math.random();
  setOutput((prev) => [...prev, { type, lines, id }]);
}

const BOOT_LINES = [
  { type: 'system', lines: ['TermiX Shell v1.0.0  —  Electron + React + Vite'] },
  { type: 'system', lines: ['Copyright (c) 2025 TermiX. All rights reserved.'] },
  { type: 'system', lines: [''] },
  { type: 'system', lines: ['Initializing runtime...          [OK]'] },
  { type: 'system', lines: ['Loading AI modules...            [OK]'] },
];

export default function TerminalUI({ visible }) {
  const [output, setOutput] = useState([]);
  const [input, setInput] = useState('');
  const [cmdHistory, setCmdHistory] = useState([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [isProcessing, setIsProcessing] = useState(false);
  const [showContent, setShowContent] = useState(false);
  /** @type {'idle' | 'confirm' | 'running'} */
  const [flowStep, setFlowStep] = useState('idle');
  const [flowSessionId, setFlowSessionId] = useState(null);
  const [flowCommands, setFlowCommands] = useState([]);
  const [flowSource, setFlowSource] = useState(null);
  const [flowSourceDisplay, setFlowSourceDisplay] = useState(null);

  const resetInteractiveFlow = useCallback(() => {
    setFlowStep('idle');
    setFlowSessionId(null);
    setFlowCommands([]);
    setFlowSource(null);
    setFlowSourceDisplay(null);
  }, []);

  const inputRef = useRef(null);
  const bottomRef = useRef(null);
  const containerRef = useRef(null);

  // Animate boot lines + health check
  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(() => setShowContent(true), 100);
    let i = 0;
    const interval = setInterval(() => {
      if (i < BOOT_LINES.length) {
        setOutput(prev => [...prev, { ...BOOT_LINES[i], id: Date.now() + i }]);
        i++;
      } else {
        clearInterval(interval);
        // Check backend health
        checkHealth()
          .then(() => {
            appendLines(setOutput, 'success', ['Connecting to backend...         [OK]']);
            appendLines(setOutput, 'system', ['']);
            appendLines(setOutput, 'info', ['Enter commands or natural language queries to execute. help / clear']);
            appendLines(setOutput, 'system', ['']);
          })
          .catch(() => {
            appendLines(setOutput, 'warn', ['Connecting to backend...         [OFFLINE]']);
            appendLines(setOutput, 'system', ['']);
            appendLines(setOutput, 'warn', ['⚠ Backend not running. Start with: cd clp-backend && uvicorn server:app --port 8000']);
            appendLines(setOutput, 'system', ['']);
            appendLines(setOutput, 'info', ['Enter commands or natural language queries to execute. help / clear']);
            appendLines(setOutput, 'system', ['']);
          });
        setTimeout(() => inputRef.current?.focus(), 100);
      }
    }, 60);
    return () => { clearTimeout(timer); clearInterval(interval); };
  }, [visible]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [output]);

  const focusInput = () => inputRef.current?.focus();

  const handleSubmit = useCallback(async () => {
    const trimmed = input.trim();
    setInput('');
    setHistoryIndex(-1);
    if (!trimmed) return;

    const cmdEntry = { type: 'command', text: trimmed, id: Date.now() };
    setOutput((prev) => [...prev, cmdEntry]);

    if (flowStep === 'idle' && trimmed.toLowerCase() !== 'clear' && trimmed.toLowerCase() !== 'help') {
      setCmdHistory((prev) => [trimmed, ...prev.filter((c) => c !== trimmed)].slice(0, 100));
    }

    setIsProcessing(true);

    if (trimmed.toLowerCase() === 'clear') {
      setTimeout(() => setOutput([]), 100);
      resetInteractiveFlow();
      setIsProcessing(false);
      return;
    }

    if (trimmed.toLowerCase() === 'help') {
      appendLines(setOutput, 'info', [
        '╔══════════════════════════════════════════════════╗',
        '║           TermiX CLI — Command Reference         ║',
        '╚══════════════════════════════════════════════════╝',
        '',
        '  <query>      — Natural language or direct commands',
        '                 Automatically resolves via AI agent',
        '                 and executes (no confirmation needed).',
        '',
        '  clear        — Clear terminal screen and reset flow',
        '  help         — Show this help message',
        '',
        '  TIP: Use ↑↓ arrow keys to navigate command history',
      ]);
      setIsProcessing(false);
      return;
    }

    try {
      // ── Confirmation step ──────────────────────────────
      if (flowStep === 'confirm') {
        const t = trimmed.toLowerCase();
        if (t === 'no' || t === 'n') {
          appendLines(setOutput, 'system', ['Cancelled.']);
          resetInteractiveFlow();
          return;
        }
        if (t !== 'yes' && t !== 'y') {
          appendLines(setOutput, 'info', ['Reply with yes or no (or y/n).']);
          return;
        }

        // User confirmed — execute commands
        const sid = flowSessionId;
        const cmds = flowCommands;
        const src = flowSource;

        const exec = await executeCommands(sid, cmds, src);

        // Show executor log lines (like the CLI screenshot)
        if (exec.line) {
          const logLines = exec.line.split('\n');
          appendLines(setOutput, 'system', logLines);
        }

        // Show detailed results (like `$ command  (exit 0)` and output)
        const results = exec.results || [];
        for (const item of results) {
          const exitCode = item.success ? 0 : 1;
          const header = `$ ${item.command}  (exit ${exitCode})`;
          const lines = [header];

          if (item.output && item.output.trim()) {
            lines.push(...item.output.trimEnd().split('\n'));
          }
          if (item.error && item.error.trim()) {
            lines.push(...item.error.trimEnd().split('\n'));
          }

          appendLines(setOutput, item.success ? 'success' : 'error', lines);
        }

        resetInteractiveFlow();
        return;
      }

      // ── Running step (interactive input) ──────────────
      if (flowStep === 'running') {
        if (/^ask\s/i.test(trimmed)) {
          appendLines(setOutput, 'error', [
            'Cannot start a new ask while a process is running. Respond to the CLI, or use clear.',
          ]);
          return;
        }
        const sid = flowSessionId;
        const res = await sendInteractiveInput(sid, trimmed);
        if (res.line != null && res.line !== '') {
          appendLines(setOutput, 'system', [res.line]);
        }

        const st = await getInteractiveStatus(sid);
        if (st.status === 'completed') {
          appendLines(setOutput, 'success', ['Command completed.']);
          resetInteractiveFlow();
        }
        return;
      }

      // ── New "ask" command ─────────────────────────────
      const query = trimmed;
      if (!query) {
        appendLines(setOutput, 'error', ['Empty query.']);
        return;
      }

      resetInteractiveFlow();
      const sid = crypto.randomUUID();
      setFlowSessionId(sid);

      // Call /resolve with session_id
      const r = await resolveQuery(query, sid);

      // Handle error state
      if (r.error) {
        appendLines(setOutput, 'error', [`Blocked: ${r.error}`]);
        resetInteractiveFlow();
        return;
      }

      // Handle missing placeholders — prompt user for more input
      if (r.missing_placeholders && r.missing_placeholders.length > 0) {
        const placeholderLines = [
          'Need more information:',
          ...r.missing_placeholders.map(p => `  • ${p}`),
          '',
          'Please provide the missing value(s):',
        ];
        appendLines(setOutput, 'info', placeholderLines);
        setFlowStep('idle');  // Back to idle for user input
        return;
      }

      // Handle tool_output — Python-native tool executed successfully
      if (r.tool_output && r.tool_output.trim()) {
        const lines = [
          `[Source: ${r.source_display}]`,
          r.tool_output.trimEnd(),
        ];
        appendLines(setOutput, 'success', lines);
        resetInteractiveFlow();
        return;
      }

      // Handle commands — show confirmation
      if (r.commands && r.commands.length > 0) {
        // Store flow state
        setFlowCommands(r.commands);
        setFlowSource(r.source);
        setFlowSourceDisplay(r.source_display);
        setFlowStep('confirm');

        // ── Display generated commands with confirmation ──
        const outputLines = ['Generated commands:'];
        r.commands.forEach((cmd, i) => {
          outputLines.push(`  ${i + 1}. ${cmd}`);
        });
        outputLines.push('');
        outputLines.push(`[Source: ${r.source_display}]`);
        outputLines.push('');
        outputLines.push("Execute these command(s)? [y/N]:");

        appendLines(setOutput, 'info', outputLines);
        return;
      }

      // No commands, no output, no missing placeholders, no error
      appendLines(setOutput, 'error', ['No commands generated.']);
      resetInteractiveFlow();

    } catch (err) {
      resetInteractiveFlow();
      appendLines(setOutput, 'error', [`Error: ${err.message}`]);
    } finally {
      setIsProcessing(false);
    }
  }, [input, flowStep, flowSessionId, flowCommands, flowSource, flowSourceDisplay, resetInteractiveFlow]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const newIdx = Math.min(historyIndex + 1, cmdHistory.length - 1);
      setHistoryIndex(newIdx);
      setInput(cmdHistory[newIdx] || '');
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      const newIdx = Math.max(historyIndex - 1, -1);
      setHistoryIndex(newIdx);
      setInput(newIdx === -1 ? '' : cmdHistory[newIdx]);
    } else if (e.key === 'c' && e.ctrlKey) {
      setInput('');
      resetInteractiveFlow();
      setOutput((prev) => [...prev, { type: 'system', lines: ['^C'], id: Date.now() }]);
    } else if (e.key === 'l' && e.ctrlKey) {
      e.preventDefault();
      setOutput([]);
      resetInteractiveFlow();
    }
  };

  if (!visible) return null;

  return (
    <div
      onClick={focusInput}
      style={{
        position: 'fixed', inset: 0,
        background: 'var(--bg-primary)',
        display: 'flex', flexDirection: 'column',
        opacity: showContent ? 1 : 0,
        transition: 'opacity 0.4s ease',
        cursor: 'text',
      }}
    >
      {/* Scanline */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 100,
        background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.015) 2px, rgba(0,0,0,0.015) 4px)',
      }} />

      {/* Top title bar */}
      <div style={{
        height: 38,
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center',
        padding: '0 16px',
        flexShrink: 0,
        WebkitAppRegion: 'drag',
        gap: 8,
      }}>
        {/* Title */}
        <div style={{
          flex: 1, textAlign: 'center',
          fontSize: 12, color: 'rgba(0,255,156,0.4)',
          letterSpacing: 3, textTransform: 'uppercase',
          fontFamily: 'var(--font-mono)',
        }}>
          TermiX CLI — dev@termix:~
        </div>

        {/* Right badges */}
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', WebkitAppRegion: 'no-drag' }}>
          <span style={{ fontSize: 10, color: 'rgba(0,255,156,0.3)', letterSpacing: 1 }}>
            {isProcessing
              ? '⟳ PROCESSING'
              : flowStep === 'confirm'
                ? '? CONFIRM'
                : flowStep === 'running'
                  ? '▶ RUNNING'
                  : '● READY'}
          </span>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{
        height: 30,
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 0,
        flexShrink: 0,
      }}>
        <div style={{
          padding: '0 20px',
          height: '100%',
          display: 'flex', alignItems: 'center',
          background: 'var(--bg-primary)',
          borderRight: '1px solid var(--border)',
          fontSize: 11, color: 'var(--green)',
          letterSpacing: 1,
          gap: 6,
        }}>
          <span style={{ fontSize: 9, opacity: 0.6 }}>⬤</span>
          termix
        </div>
        <div style={{
          padding: '0 16px', height: '100%',
          display: 'flex', alignItems: 'center',
          fontSize: 11, color: 'var(--muted-text)',
          letterSpacing: 1, gap: 6, cursor: 'pointer',
          opacity: 0.4,
        }}>
          <span style={{ fontSize: 12 }}>+</span>
        </div>
      </div>

      {/* Output area */}
      <div
        ref={containerRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px 20px 8px',
          fontFamily: 'var(--font-mono)',
          fontSize: 13,
          lineHeight: 1.6,
        }}
      >
        {output.map((entry, i) => (
          <OutputLine key={entry.id || i} entry={entry} index={i} />
        ))}

        {/* Processing indicator */}
        {isProcessing && (
          <div style={{
            color: 'rgba(0,255,156,0.5)',
            fontSize: 12,
            paddingLeft: 4,
            animation: 'blink 0.8s step-end infinite',
          }}>
            ⟳ processing...
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input row */}
      <div style={{
        padding: '10px 20px 14px',
        borderTop: '1px solid var(--border)',
        background: 'var(--bg-secondary)',
        flexShrink: 0,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          {/* Prompt */}
          <span style={{
            color: flowStep === 'confirm' ? 'var(--amber)' : 'rgba(0,255,156,0.6)',
            fontSize: 13,
            fontFamily: 'var(--font-mono)',
            flexShrink: 0,
            userSelect: 'none',
          }}>
            {flowStep === 'confirm' ? '[y/N]>' : flowStep === 'running' ? 'cli>' : 'dev@termix:~$'}
          </span>

          {/* Input */}
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isProcessing}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'var(--green)',
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              caretColor: 'var(--green)',
              padding: 0,
              userSelect: 'text',
            }}
          />
        </div>

        {/* Bottom hints */}
        <div style={{
          marginTop: 6,
          display: 'flex', gap: 20,
          fontSize: 10, color: 'var(--muted-text)',
          letterSpacing: '0.05em',
        }}>
          <span>↑↓ history</span>
          <span>Ctrl+C cancel</span>
          <span>Ctrl+L clear</span>
          <span style={{ marginLeft: 'auto', color: 'rgba(0,255,156,0.2)' }}>
            {cmdHistory.length} commands
          </span>
        </div>
      </div>
    </div>
  );
}
