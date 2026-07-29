---
name: plugins-setup
description: Install and configure Claude Code plugins for ib-trader — LSP (pyright/clangd), market data (equity-research, trading-ideas), SQLite, shell utilities. Enables real-time type checking, financial data access, and workflow acceleration.
---

# Plugins Setup — Instalar herramientas

Plugins útiles instalados (algunos) y cómo instalar nuevos.

## Ya instalados
```bash
# LSP type checkers (autocomplete en scripts/)
- pyright-lsp (Python, type hints)
- clangd-lsp (C++, refactoring)

# Trading/financial data
- equity-research (Anthropics)
- trading-ideas (Quant Sentiment)
- trading-market-analysis (Claude Trading Skills)
```

## Instalar nuevos (recomendados para ib-trader)

### 1. SQLite plugin (si no existe)
```bash
codex plugin install sqlite@claude-plugins-official
# Permite: `SELECT * FROM poly_opt_bars` directo en conversación
```

### 2. Shell/Bash plugin (ejecución segura de scripts)
```bash
codex plugin install shell@anthropics-knowledge-work-plugins
# Permite: ejecutar scripts con permisos controlados
```

### 3. Financials plugin (si hay de Yodlee/IEX)
```bash
codex plugin browse --marketplace "anthropics-financial-services-plugins"
codex plugin install financial-data@anthropics-financial-services-plugins
```

## Ver plugins instalados
```bash
cat ~/.claude/plugins/installed_plugins.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for name, versions in d.get('plugins', {}).items():
  print(f'{name}: {versions[0][\"version\"]}')"
```

## Habilitar en CLI
```bash
# En sesión, plugins automáticos si están instalados
codex exec --full-auto "<prompt>" --with-plugins
```

## Fuente propia
Configuración del repo + marketplace oficial
