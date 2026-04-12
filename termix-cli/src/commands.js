// Command registry for TermiX CLI
const BOOT_TIME = new Date();

const commands = {
  help: () => ({
    type: 'info',
    lines: [
      '╔══════════════════════════════════════════════════╗',
      '║           TermiX CLI — Command Reference         ║',
      '╚══════════════════════════════════════════════════╝',
      '',
      '  SYSTEM',
      '  ──────────────────────────────────────────────',
      '  help          Show this help menu',
      '  clear         Clear terminal history',
      '  version       Show TermiX version info',
      '  uptime        Show session uptime',
      '  sysinfo       Display system information',
      '',
      '  AI & API',
      '  ──────────────────────────────────────────────',
      '  ask <query>   Send query to AI backend',
      '  connect       Test backend API connection',
      '  status        Show API connection status',
      '',
      '  DEVELOPER TOOLS',
      '  ──────────────────────────────────────────────',
      '  ls [path]     List files (simulated)',
      '  pwd           Print working directory',
      '  env           Show environment variables',
      '  ping <host>   Ping a host',
      '  echo <text>   Echo text to output',
      '  date          Show current date/time',
      '  whoami        Show current user',
      '',
      '  TERMINAL',
      '  ──────────────────────────────────────────────',
      '  history       Show command history',
      '  theme <name>  Switch color theme (green/amber/blue)',
      '  exit          Exit TermiX',
      '',
      '  TIP: Use ↑↓ arrow keys to navigate command history',
    ],
  }),

  clear: () => ({ type: 'clear' }),

  version: () => ({
    type: 'success',
    lines: [
      'TermiX CLI v1.0.0',
      'Runtime: Electron + React + Vite',
      'Node: v20.x | Chromium: 120.x',
      'Build: 2025-01-01 | MIT License',
    ],
  }),

  uptime: () => {
    const now = new Date();
    const diff = Math.floor((now - BOOT_TIME) / 1000);
    const h = Math.floor(diff / 3600).toString().padStart(2, '0');
    const m = Math.floor((diff % 3600) / 60).toString().padStart(2, '0');
    const s = (diff % 60).toString().padStart(2, '0');
    return {
      type: 'info',
      lines: [`Session uptime: ${h}:${m}:${s}`, `Started: ${BOOT_TIME.toLocaleTimeString()}`],
    };
  },

  sysinfo: () => ({
    type: 'info',
    lines: [
      '┌─ System Information ───────────────────────────┐',
      `│  OS        : ${navigator.platform || 'Linux x86_64'}`,
      `│  CPU Cores : ${navigator.hardwareConcurrency || 8}`,
      `│  Language  : ${navigator.language}`,
      `│  Online    : ${navigator.onLine ? '✓ Connected' : '✗ Offline'}`,
      `│  App       : TermiX CLI v1.0.0`,
      `│  Engine    : Electron / Chromium`,
      '└────────────────────────────────────────────────┘',
    ],
  }),

  whoami: () => ({
    type: 'success',
    lines: ['dev@termix', 'Role: Administrator', 'Shell: termix-shell 1.0'],
  }),

  date: () => ({
    type: 'info',
    lines: [new Date().toString()],
  }),

  pwd: () => ({
    type: 'info',
    lines: ['/home/dev/termix'],
  }),

  env: () => ({
    type: 'info',
    lines: [
      'NODE_ENV=development',
      'TERM=xterm-256color',
      'SHELL=/bin/termix',
      'LANG=en_US.UTF-8',
      'API_URL=http://localhost:8000',
      'TERMIX_VERSION=1.0.0',
      'HOME=/home/dev',
    ],
  }),

  history: (args, history) => ({
    type: 'info',
    lines: history.map((cmd, i) => `  ${String(i + 1).padStart(3)}  ${cmd}`),
  }),

  connect: async () => {
    try {
      const res = await fetch('http://localhost:8000/health', { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        return { type: 'success', lines: ['✓ Backend connected at http://localhost:8000', `  Status: ${res.status} OK`] };
      }
      return { type: 'error', lines: [`✗ Backend returned ${res.status}`, '  Check your server logs.'] };
    } catch {
      return { type: 'error', lines: ['✗ Cannot reach http://localhost:8000', '  Is your backend running?', '  Run: uvicorn main:app --reload'] };
    }
  },

  status: async () => {
    try {
      await fetch('http://localhost:8000/health', { signal: AbortSignal.timeout(2000) });
      return { type: 'success', lines: ['API Status: ● ONLINE', 'Endpoint: http://localhost:8000'] };
    } catch {
      return { type: 'warn', lines: ['API Status: ○ OFFLINE', 'Endpoint: http://localhost:8000', 'Start backend to enable AI features.'] };
    }
  },

  ask: async (args) => {
    const query = args.join(' ').trim();
    if (!query) return { type: 'error', lines: ['Usage: ask <your question>'] };
    try {
      const res = await fetch('http://localhost:8000/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
        signal: AbortSignal.timeout(10000),
      });
      const data = await res.json();
      const answer = data.response || data.answer || JSON.stringify(data);
      return {
        type: 'ai',
        lines: ['┌─ AI Response ────────────────────────────────┐', ...answer.split('\n').map(l => '│  ' + l), '└──────────────────────────────────────────────┘'],
      };
    } catch {
      return {
        type: 'warn',
        lines: [
          '⚠ Backend offline — Demo response:',
          '┌─ AI Response ────────────────────────────────┐',
          `│  Query: "${query}"`,
          '│',
          '│  This is a simulated AI response.',
          '│  Connect a backend at localhost:8000 for live AI.',
          '│  Run: ask help  for more info.',
          '└──────────────────────────────────────────────┘',
        ],
      };
    }
  },

  ls: (args) => {
    const path = args[0] || '.';
    const mockFiles = {
      '.': ['drwxr-xr-x  src/', 'drwxr-xr-x  electron/', 'drwxr-xr-x  public/', '-rw-r--r--  package.json', '-rw-r--r--  vite.config.js', '-rw-r--r--  index.html', '-rw-r--r--  README.md'],
      src: ['drwxr-xr-x  components/', '-rw-r--r--  App.jsx', '-rw-r--r--  main.jsx', '-rw-r--r--  index.css', '-rw-r--r--  commands.js'],
      electron: ['-rw-r--r--  main.js', '-rw-r--r--  preload.js'],
    };
    const key = path === '.' ? '.' : path.replace(/^\.\//, '');
    return {
      type: 'info',
      lines: [`total ${(mockFiles[key] || []).length}`, ...(mockFiles[key] || [`ls: cannot access '${path}': No such file or directory`])],
    };
  },

  ping: (args) => {
    const host = args[0];
    if (!host) return { type: 'error', lines: ['Usage: ping <hostname>'] };
    const ms = () => (Math.random() * 20 + 1).toFixed(3);
    return {
      type: 'info',
      lines: [
        `PING ${host} (127.0.0.1) 56 bytes of data.`,
        `64 bytes from ${host}: icmp_seq=1 ttl=64 time=${ms()} ms`,
        `64 bytes from ${host}: icmp_seq=2 ttl=64 time=${ms()} ms`,
        `64 bytes from ${host}: icmp_seq=3 ttl=64 time=${ms()} ms`,
        `--- ${host} ping statistics ---`,
        '3 packets transmitted, 3 received, 0% packet loss',
      ],
    };
  },

  echo: (args) => ({
    type: 'info',
    lines: [args.join(' ')],
  }),

  theme: (args) => {
    const themes = { green: '#00FF9C', amber: '#FFB800', blue: '#58A6FF', red: '#FF4545', cyan: '#00D4FF' };
    const name = args[0]?.toLowerCase();
    if (!name || !themes[name]) {
      return { type: 'info', lines: [`Available themes: ${Object.keys(themes).join(', ')}`] };
    }
    document.documentElement.style.setProperty('--green', themes[name]);
    document.documentElement.style.setProperty('--green-dim', themes[name] + 'CC');
    document.documentElement.style.setProperty('--green-glow', themes[name] + '26');
    document.documentElement.style.setProperty('--green-glow-strong', themes[name] + '66');
    return { type: 'success', lines: [`Theme switched to: ${name}`, `Color: ${themes[name]}`] };
  },

  exit: () => {
    setTimeout(() => window.close?.(), 800);
    return { type: 'warn', lines: ['Goodbye. Closing TermiX...'] };
  },
};

export async function processCommand(input, commandHistory) {
  const trimmed = input.trim();
  if (!trimmed) return null;

  const parts = trimmed.split(/\s+/);
  const cmd = parts[0].toLowerCase();
  const args = parts.slice(1);

  if (cmd in commands) {
    const handler = commands[cmd];
    const result = await handler(args, commandHistory);
    return result;
  }

  // Unknown command
  return {
    type: 'error',
    lines: [
      `termix: command not found: ${cmd}`,
      `Type 'help' to see available commands.`,
    ],
  };
}
