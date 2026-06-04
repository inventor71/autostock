# F54 — Build Instructions

No build step (pure Python). Verify the worktree imports and deps are intact.

```bash
# from the F54 worktree, with the main venv python
cd .claude/worktrees/F54
/home/jihoonpark/Project/autostock/venv/bin/python -c "import main"   # import smoke
/home/jihoonpark/Project/autostock/venv/bin/pip check                 # deps intact
```

Expected: `import` succeeds, `No broken requirements found`. **0 new runtime deps.**
