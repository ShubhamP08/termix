# TermiX CLI

A terminal-style AI developer tool built with React + Vite + Electron.

## Features
- 🖥️ Full-screen welcome screen with typewriter animation
- ⚡ Smooth transition to terminal UI
- 🤖 AI backend integration (localhost:8000)
- ⌨️ Command history with ↑↓ navigation
- 🎨 Switchable color themes
- 🔧 Built-in developer commands

## Setup & Run

### 1. Install dependencies
```bash
npm install
```

### 2. Run in browser (Vite only)
```bash
npm run dev
# Open http://localhost:5173
```

### 3. Run as desktop app (Electron)
```bash
npm run electron:dev
```

### 4. Build for distribution
```bash
npm run electron:build
```

## Available Commands
| Command | Description |
|---------|-------------|
| `help` | Show all commands |
| `ask <query>` | Query AI backend |
| `connect` | Test backend connection |
| `status` | Show API status |
| `sysinfo` | System information |
| `ls [path]` | List files |
| `ping <host>` | Ping host |
| `theme <name>` | Switch theme (green/amber/blue/cyan/red) |
| `history` | Show command history |
| `clear` | Clear terminal |
| `exit` | Exit app |

## Keyboard Shortcuts
- `↑` / `↓` — Navigate command history
- `Ctrl+C` — Cancel current input
- `Ctrl+L` — Clear terminal
- `Enter` — Execute command

## Backend Integration
Connect an API at `http://localhost:8000` with endpoints:
- `GET /health` — Health check
- `POST /ask` — AI query `{ query: string }` → `{ response: string }`

## Tech Stack
- **React 18** — UI components + hooks
- **Vite 5** — Fast dev server + bundler
- **Electron 28** — Desktop wrapper
- **Axios** — HTTP client for API calls

## Project Structure
```
termix/
├── electron/
│   ├── main.js        # Electron main process
│   └── preload.js     # Context bridge
├── src/
│   ├── components/
│   │   ├── WelcomeScreen.jsx   # Animated splash
│   │   ├── TerminalUI.jsx      # Terminal interface
│   │   └── OutputLine.jsx      # Output renderer
│   ├── commands.js    # Command processor
│   ├── App.jsx        # Root component
│   ├── main.jsx       # React entry
│   └── index.css      # Global styles + animations
├── index.html
├── vite.config.js
└── package.json
```
