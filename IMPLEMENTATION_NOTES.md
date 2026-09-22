# Implementation Notes

This file is a short interview guide for the changes in this submission.

## 1. Governance gate

File: `app/autonomy.py`

`evaluate_gate` is a pure policy function. Read tools always return `allow=True` because they do not change the workspace. Shadow writes return `allow=True` and `simulate=True`, so the run records the intended effect without executing it. Supervised writes require approval. Autonomous writes are allowed only while `writes_so_far < max_auto_writes`; the strict comparison makes the budget boundary exact.

Interview point: the gate does not call tools or mutate state. Keeping policy separate makes every branch easy to test and prevents tool implementations from deciding their own permissions.

## 2. Verification

File: `app/verifier.py`

The verifier loops over expected effects and searches for one unused actual effect with the same tool name and all expected argument values. A `claimed` set prevents one effect from matching multiple expectations. Any expected effect without a match is missing, and any unclaimed actual effect is unexpected. The verdict passes only when both lists are empty.

Interview point: simulated effects are intentionally treated like real effects. Shadow mode should prove behavioral correctness without causing external changes.

## 3. Agent loop

File: `app/agent.py`

Each turn parses a model intent, handles a final answer, resolves the requested tool, checks the gate, optionally asks the reviewer, executes the tool, records steps, records successful writes, and sends an observation back to the model. Unknown tools, tool errors, and rejected writes continue the loop because they are recoverable information. Invalid JSON, provider exceptions, a missing task, and the maximum step count fail the run.

Interview point: `run.steps` is an audit transcript, while `run.effects` contains only successful writes that the verifier should inspect. The workspace is injected through `AgentDeps`, which keeps tests isolated.

## 4. Model retry

File: `app/model_client.py`

`complete_with_retry` retries only `ThrottleError`. It sleeps for `base * 2**attempt` before each retry and re-raises the final throttle error. `FatalError` and all other exceptions propagate immediately.

Interview point: retrying a bad credential wastes time and quota, while a rate limit or transient provider failure may succeed on the next attempt.

## 5. Idempotent messaging

File: `app/tools.py`

`Workspace.send_message` validates the contact and idempotency key, checks the workspace key map before sending, and stores the original result. A repeated key returns the same message id with `deduped=True` and does not append a second message.

Interview point: idempotency is enforced inside the side-effecting tool, not only in the agent loop. That protects the world even if the caller repeats a request.

## 6. Start-run endpoint

File: `app/api.py`

`POST /runs` looks up the task, returns 404 when absent, creates and stores a run, creates a fresh workspace, binds the registry to that same workspace, runs the agent synchronously, and returns the finished run.

Interview point: using one workspace for both the registry and dependencies prevents bound tool methods from writing to a different world.

## 7. Tests

File: `tests/test_example.py`

The tests cover the gate decision table, verifier outcomes and duplicate matching, retry call counts, fatal non-retry behavior, workspace-level idempotency, successful and shadow runs, recoverable tool problems, max-step failure, fatal provider handling, and the HTTP endpoint.

The strongest assertions inspect state: `model.calls == 1` proves fatal errors are not retried, and `workspace.messages == []` proves shadow mode did not mutate the world.

## Validation

Run from the project virtual environment:

```text
.venv\Scripts\python.exe -m pytest -q
```

Result during implementation: `26 passed`.
