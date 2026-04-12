# AI Terminal Agent

Local AI developer assistant that converts natural language into terminal commands.

## Goals
- Natural language → typed intent → parallel retrieval → confidence routing → safety gate → dry-run → execute
- Local-first, fast, safe-by-default
- Built with Python + LangGraph

## Project structure
- `cli/`: CLI entrypoint
- `agent/`: LangGraph graph, nodes, state definitions
- `ai/`: LLM interface + planning/command generation/error recovery
- `knowledge/`: JSON KB + vector store + retrieval/learning stubs
- `execution/`: command execution + shell abstraction
- `security/`: command validation / deny-list gate
- `filesystem/`: file-operation helper agent (stub)
- `utils/`: normalization, OS detection, fuzzy matching (stubs)
- `prompts/`: prompt templates
- `data/`: local data artifacts (reserved)
- `tests/`: tests (reserved)

## Notes
- This repo currently contains **structure and placeholders only** (no functional logic yet).
- JSON KB is intended to be loaded once at graph compile time and closed over in nodes.

