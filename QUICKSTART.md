# Quick-Start Guide — Android BSP Diagnostic Expert (Alpha)

> **Who this is for:** BSP / kernel engineers trying the tool for the first time.
> **Time to first diagnosis:** ~5 minutes (excluding Anthropic API key sign-up).

---

## Step 1 — Get an Anthropic API key

The diagnostic agent (CLI mode) calls Claude via the Anthropic API.
The skills themselves are pure Python and **never** require a key.

1. Create a free account at <https://console.anthropic.com/>
2. Generate an API key under **API keys**
3. Keep it handy — you will set it as an environment variable below

> **Note:** If you only want to run the unit tests or use the MCP server inside
> Claude Code, skip this step entirely.

---

## Step 2 — Clone and set up the environment

```bash
git clone https://github.com/jonaschen/ai-bsp-agent.git
cd ai-bsp-agent

# Create an isolated Python environment (Python 3.11+ required — see pyproject.toml)
python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows (PowerShell)

# Install all dependencies
pip install -r requirements.txt
```

---

## Step 3 — Verify the installation (no API key needed)

```bash
source venv/bin/activate
python -m pytest tests/product_tests/ -q
```

Expected last line:

```
539 passed in Xs
```

All 539 tests are deterministic — no Anthropic key, no network access.

---

## Step 4 — Set your API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Add this line to `~/.bashrc` or `~/.zshrc` to make it permanent.

---

## Step 5 — Run your first diagnosis

### Option A — CLI (quickest)

```bash
# Diagnose a kernel panic log
python cli.py --dmesg /path/to/dmesg.txt

# With a /proc/meminfo snapshot (needed for STD hibernation cases)
python cli.py --dmesg /path/to/dmesg.txt --meminfo /path/to/meminfo.txt

# Save the structured JSON result to a file
python cli.py --dmesg /path/to/dmesg.txt --output result.json

# Describe the symptom explicitly
python cli.py --dmesg /path/to/dmesg.txt \
              --query "Device fails to resume from suspend-to-disk" \
              --device "MyBoard-v2" \
              --output result.json

# Logcat file (SELinux denials, init.rc failures)
python cli.py --dmesg /path/to/dmesg.txt --logcat /path/to/logcat.txt
```

The agent prints a `ConsultantResponse` JSON to stdout. Status messages go to
stderr, so you can pipe the JSON directly:

```bash
python cli.py --dmesg dmesg.txt | jq .root_cause_summary
```

### Option B — MCP server inside Claude Code (VS Code)

This makes all 24 skills available as native tools in Claude's conversation window.

```bash
# Install the package once (from the project root, venv active)
pip install -e .

# Register with Claude CLI
claude mcp add bsp-diagnostics bsp-diagnostics-mcp
```

Then start a Claude Code session and paste your log — Claude will automatically
invoke the relevant skills.

---

## Step 6 — Use a sample log (if you don't have your own yet)

The repository ships with validated log fixtures:

```bash
# Watchdog timeout example
python cli.py --dmesg logs/validation/watchdog_soft_lockup_01.txt

# Kernel Oops example
python cli.py --dmesg logs/validation/kernel_oops_null_pointer_01.txt

# STD hibernation failure (needs meminfo)
python cli.py \
  --dmesg  logs/validation/std_hibernation_high_sunreclaim_01.txt \
  --meminfo logs/validation/meminfo_high_sunreclaim_01.txt
```

See `logs/validation/` for the full list of 28 validated fixtures.

---

## What to do when a skill misses your hardware pattern

Real hardware log formats often differ from the emulator-trained patterns.
When `confidence < 0.5` or `failure_detected = false` for a log you know is a
failure, extend the skill:

```
1. Ask the agent: "The skill missed this log. Can you suggest an extension?"
2. The agent calls validate_skill_extension (dry-run) to confirm your regex matches.
3. The agent calls suggest_pattern_improvement to persist it.
4. Re-run — the skill now picks up your pattern (confidence = 0.60, [user pattern] prefix).
```

See `docs/skill-extension-guide.md` for the full workflow.

---

## Reporting issues and feedback

Please open a GitHub Issue with:

- The log snippet (redact serial numbers / IP addresses if needed)
- The skill output JSON you got (`--output result.json`)
- The expected behaviour

Feedback from alpha testers directly drives the next development iteration.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'anthropic'` | `pip install -r requirements.txt` inside the venv |
| `AuthenticationError: invalid api key` | Check `echo $ANTHROPIC_API_KEY`; re-export if empty |
| `539 passed` but you see `16 errors` | Those are legacy studio tests — ignore them; only `tests/product_tests/` matter |
| Skill returns `failure_detected: false` on real hardware | See **What to do when a skill misses your hardware pattern** above |
| `addr2line: command not found` (workspace skill) | Install binutils: `sudo apt install binutils-aarch64-linux-gnu` |
