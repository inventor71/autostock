"""F74 prompt-eval harness core.

Pure-python pipeline the promptfoo glue (``evals/``) drives: scenario schema,
sandbox construction, turn execution through the production orchestrator,
artifact extraction, and Tier-1 deterministic grading. Everything here is
token-free and unit-testable; the only LLM call happens inside a real
``AgentSession`` turn, which tests replace with a fake runner.
"""
