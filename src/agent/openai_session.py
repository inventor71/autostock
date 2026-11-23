"""Responses API research session with journal tools and read-only market data.

Shares the production prompts, journal and executor with Claude. No shell or
broker order tool is exposed. API credentials are independent of Codex login.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from src.agent.session import AgentSession, AgentTurnResult, _REPO_ROOT
from src.agent.steering.security import scrub_agent_env
from src.agent.tools.fixtures import MARKET_COMMANDS, FIXTURE_ENV
from src.core.jsonl import atomic_write_text


def _function(name, description, properties):
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(properties), "additionalProperties": False}}


class OpenAIAgentSession(AgentSession):
    def __init__(self, workspace=None, *, api_key="", model="gpt-6-astra", effort="high",
                 timeout=600.0, max_output_tokens=32768, one_shot=False, read_only=False,
                 session_date=None, client=None, observer=None, allow_web=True):
        if not api_key and client is None:
            raise ValueError("OPENAI_API_KEY is required; Codex subscription login is not an API key")
        super().__init__(workspace=workspace, model=model, effort=effort, timeout=timeout,
                         one_shot=one_shot, session_date=session_date)
        self.api_key = api_key
        self.max_output_tokens = max_output_tokens
        self.read_only = read_only
        self.observer = observer
        self.allow_web = allow_web
        self._staged_writes: dict[Path, str] | None = None
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, max_retries=0)
        self.client = client

    def _state_file(self):
        return self.workspace / ".sessions" / f"{self.session_date.isoformat()}.openai.json"

    def create_sub_agent(self, workspace, model=None, timeout=600.0, runner=None, effort=None):
        return type(self)(
            workspace, api_key=self.api_key, model=model or self.model,
            effort=effort or self.effort, timeout=timeout, max_output_tokens=self.max_output_tokens,
            one_shot=True, read_only=True, client=self.client, observer=self.observer,
            allow_web=self.allow_web,
        )

    def _tools(self):
        string = {"type": "string"}
        tools = [
            _function("read_file", "Read a UTF-8 journal file relative to the workspace.",
                      {"path": string}),
            _function("list_files", "List journal files under a relative directory ('.' for root).",
                      {"path": string}),
            _function("market_data", "Call the read-only market CLI. Example: ['quote','AAPL']. "
                      "Commands: " + ", ".join(sorted(MARKET_COMMANDS)),
                      {"arguments": {"type": "array", "items": string}}),
        ]
        if not self.read_only:
            tools.append(_function("write_file", "Write a journal file. Read before replacing "
                                   "existing content; append=true adds text, e.g. a JSONL line.",
                                   {"path": string, "content": string, "append": {"type": "boolean"}}))
        if self.allow_web and not os.environ.get(FIXTURE_ENV):
            tools.append({"type": "web_search"})
        return tools

    def _path(self, relative: str) -> Path:
        root = self.workspace.resolve()
        candidate = root / relative
        path = candidate.resolve()
        if (Path(relative).is_absolute() or not path.is_relative_to(root)
                or any(part.startswith(".") and part not in (".", "..")
                       for part in candidate.relative_to(root).parts)):
            raise ValueError("Only journal files inside the workspace are accessible")
        return path

    def _tool(self, name: str, args: dict, deadline: float) -> str:
        if name in ("read_file", "list_files", "write_file"):
            path = self._path(args["path"])
            if name == "list_files":
                names = {p.name for p in path.iterdir()
                         if not p.name.startswith(".") and not p.is_symlink()} if path.exists() else set()
                names.update(p.relative_to(path).parts[0] for p in (self._staged_writes or {})
                             if p.is_relative_to(path) and p != path)
                return json.dumps(sorted(names))
            if path.suffix not in (".md", ".json", ".jsonl", ".txt"):
                raise ValueError("Only text journal formats are supported")
            if name == "read_file":
                staged = self._staged_writes or {}
                return (staged[path] if path in staged else path.read_text(encoding="utf-8"))[:100_000]
            if self.read_only:
                raise ValueError("Analysts cannot write journal decisions")
            content = args["content"]
            if not isinstance(args["append"], bool):
                raise ValueError("append must be a boolean")
            if not isinstance(content, str) or len(content) > 100_000:
                raise ValueError("Journal write exceeds the text limit")
            staged = self._staged_writes or {}
            if args["append"]:
                content = (staged[path] if path in staged else
                           path.read_text(encoding="utf-8") if path.exists() else "") + content
            if self._staged_writes is not None:
                self._staged_writes[path] = content
                return "Staged; will be saved when the turn completes"
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, content)
            return "Saved"
        if name != "market_data":
            raise ValueError(f"Unknown tool: {name}")
        argv = args["arguments"]
        if (not isinstance(argv, list) or not argv or argv[0] not in MARKET_COMMANDS
                or len(argv) > 20 or any(not isinstance(v, str) or len(v) > 1000 for v in argv)):
            raise ValueError("Only read-only market CLI commands are permitted")
        env = scrub_agent_env(dict(os.environ))
        # Market tools do not need model-provider credentials.
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            env.pop(key, None)
        env["AGENT_JOURNAL_ROOT"] = str(self.workspace)
        env["PYTHONPATH"] = str(_REPO_ROOT)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Research turn deadline exceeded")
        proc = subprocess.run([sys.executable, "-m", "src.agent.tools", *argv],
                              cwd=self.workspace, env=env, capture_output=True, text=True,
                              timeout=min(remaining, 60))
        return (proc.stdout if proc.returncode == 0 else proc.stderr)[:100_000]

    def run_turn(self, prompt, system_prompt=None, model=None, timeout=None, effort=None):
        # Tool calls may precede an API failure or incomplete response. Keep
        # their journal writes private until the whole turn completes, and
        # publish decisions last so the executor never sees a partial proposal.
        self._staged_writes = {}
        try:
            result = self._run_turn(prompt, system_prompt, model, timeout, effort)
            for path in sorted(self._staged_writes, key=lambda p: (p.name == "decisions.jsonl", str(p))):
                path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(path, self._staged_writes[path])
            if not self._one_shot:
                self._write_state(result.session_id)
            return result
        finally:
            self._staged_writes = None

    def _run_turn(self, prompt, system_prompt=None, model=None, timeout=None, effort=None):
        self.journal.init()
        model, effort = model or self.model, effort or self.effort
        if effort not in ("low", "medium", "high", "xhigh", "max"):
            raise ValueError(f"Unsupported reasoning effort: {effort}")
        state = None if self._one_shot else self._read_state()
        previous = state.get("session_id") if state else None
        resumed = bool(previous)
        manual = (self.workspace / "CLAUDE.md").read_text(encoding="utf-8")
        instructions = "\n\n".join(filter(None, [manual, system_prompt, (
            "Use read_file/list_files/write_file for journal work and market_data for "
            "python -m src.agent.tools commands described in the manual. No shell is available. "
            "Market access is read-only; the executor alone places orders. "
            + ("You are an analyst: return findings without journal writes." if self.read_only else "")
        )]))
        if os.environ.get(FIXTURE_ENV):
            instructions += "\nFrozen evaluation: use only supplied evidence and fixture tools."
        inputs = [{"role": "user", "content": prompt}]
        totals = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}
        resolved = set()
        started = time.monotonic()
        deadline = started + (timeout or self.timeout)
        budget = self.max_output_tokens
        for _ in range(32):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or budget <= 0:
                raise TimeoutError("OpenAI turn exhausted its time or output budget")
            request = dict(model=model, reasoning={"effort": effort}, instructions=instructions,
                           input=inputs, tools=self._tools(), max_output_tokens=budget,
                           timeout=remaining, store=True)
            if previous:
                request["previous_response_id"] = previous
            call_start = time.monotonic()
            event = {"model": model, "effort": effort, "provider": "openai",
                     "prompt": prompt, "cost_scope": "request", "reported_cost_usd": None}
            try:
                response = self.client.responses.create(**request)
                payload = response.model_dump(mode="json")
                event.update(response=payload, resolved_models=[response.model], is_error=False)
                usage = payload.get("usage") or {}
                event["usage"] = {
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "cache_read_input_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
                    "cache_creation_input_tokens": 0,
                }
                for key in totals:
                    totals[key] += event["usage"].get(key) or 0
                budget -= usage.get("output_tokens", 0)
                resolved.add(response.model)
                if response.status != "completed":
                    raise RuntimeError(f"OpenAI response incomplete: {response.status}")
            except Exception as exc:
                event.update(is_error=True, error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                event["wall_seconds"] = time.monotonic() - call_start
                if self.observer:
                    self.observer(event)
            previous = response.id
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                if not response.output_text.strip():
                    raise RuntimeError("OpenAI returned no final text")
                raw = {"usage": totals, "modelUsage": {m: {} for m in sorted(resolved)},
                       "autostock_request": {"provider": "openai", "model": model, "effort": effort},
                       "duration_ms": int((time.monotonic() - started) * 1000)}
                return AgentTurnResult(response.output_text, previous, resumed, raw)
            inputs = []
            for call in calls:
                try:
                    result = self._tool(call.name, json.loads(call.arguments), deadline)
                except (ValueError, KeyError, OSError, TypeError) as exc:
                    result = json.dumps({"error": str(exc)})
                inputs.append({"type": "function_call_output", "call_id": call.call_id,
                               "output": result})
        raise RuntimeError("OpenAI tool-round limit exceeded")
