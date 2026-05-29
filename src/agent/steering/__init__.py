"""Human steering (F4): detached operator console over a file-drop channel.

The operator interface is a separate process (Unit B, opencode-based). It and
the trading daemon communicate ONLY through append-only files under the
repo-root ``steering/`` directory (outside the agent's ``workspace/`` cwd):

- ``steering/commands.jsonl``  -- operator -> daemon (confirmed, token-bearing)
- ``steering/events.jsonl``    -- daemon -> operator (outcomes/fills/pending/...)
- ``steering/snapshot.json``   -- daemon -> operator (live read view)

Trades flow through the SAME ``DecisionExecutor`` -> ``RiskManager`` -> ``Broker``
gate as agent trades (no second order path). See
``aidlc-docs/construction/steering-core/`` for the design.
"""
