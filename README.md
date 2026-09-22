# Agent Runner Lite — Intern Take-Home

Thanks for taking the time on this. You'll build a small **governed agent runner**: a service that
drives an AI agent through a tool-use loop, decides what the agent is allowed to do on its own, and
then checks that it actually did what was asked — and nothing more.

The full brief — the six tasks, what we look for, and the ground rules — is in **`BRIEF.md`**.
**Read that first.** This file is just how to run things, plus a map of the code, and it's where you
write up your work when you're done.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest -q                                             # the example tests pass on a fresh checkout
uvicorn app.main:app --reload                         # http://127.0.0.1:8000/docs
```

Requires **Python 3.11+**. No API keys, no network, no external services — the language model is a
script (`app/seed.py`), so everything is deterministic and offline.

On a fresh checkout the app imports and `pytest` is green, but the six functions you're implementing
raise `NotImplementedError` (and `POST /runs` returns a 501). That's expected. Search the project for
`TODO(candidate)` to find them — there are six, numbered by task.

Nothing is persisted. Restart the server and your tasks and runs are gone. That's fine, don't work
around it.

## Where things are

```
app/
  models.py          the whole data contract — READ THIS FIRST, it's the map
  config.py          settings, all overridable by env var
  seed.py            toy contacts + 11 scripted model conversations
  store.py           two dicts standing in for a database
  model_client.py    TASK 4a — complete_with_retry     (mock model provided)
  tools.py           TASK 4b — send_message            (read tools + update_contact provided)
  autonomy.py        TASK 1  — evaluate_gate
  verifier.py        TASK 2  — verify
  agent.py           TASK 3  — run_agent               (five helpers provided)
  api.py             TASK 5  — start_run               (three other routes provided)
  main.py            the FastAPI app
tests/
  helpers.py         make_run() — builds an isolated run in one line
  conftest.py        store reset + a `client` fixture for HTTP tests
  test_example.py    four example tests showing the shapes you'll want
```

## A suggested first hour

If you're not sure where to start:

1. `pip install -r requirements.txt && pytest -q`. Green? Good.
2. Read **`app/models.py`** top to bottom. It's commented and it's the whole data model — most of
   the "what shape do I return?" questions are answered there.
3. Read **`app/seed.py`** to see what the mock model does. This is the trick that makes the whole
   thing testable, and it's worth understanding before anything else.
4. Open **`app/autonomy.py`** (Task 1). Write the tests for it first — `test_example.py` has a
   `parametrize` example to copy. Watch them fail, then make them pass.
5. Then `app/verifier.py` (Task 2), same way.

By then you'll have the shape of the codebase and two of the six tasks done.

## Useful to know

- **The scenarios in `app/seed.py` are your test fixtures.** There's one for each path you need to
  handle: `send_followup` (the happy path), `unknown_tool` (a hallucinated tool name),
  `tool_error` (a tool that fails), `three_writes` (the autonomy budget), `never_finishes` (the
  `max_steps` cap), `flaky_provider` (throttled then fine), `bad_credentials` (fatal, don't retry),
  `bad_json_then_good` and `always_bad_json` (malformed model output). Read the comments there.
- **`tests/helpers.py::make_run`** gives you a Run and its dependencies in one line, isolated. Use it
  for every loop test.
- **Everything is synchronous.** Plain `def`, `time.sleep`, no `await` anywhere. If you find
  yourself reaching for `asyncio`, you've gone off the path.
- **Settings are injected, not global.** Your functions take `settings`, so a test can say "budget
  of 1, retry twice" without touching the environment:
  `make_run(script, settings=replace(SETTINGS, max_auto_writes=1))`.
- Once Task 5 is done, `http://127.0.0.1:8000/docs` gives you a UI to create a task and start a run
  without writing any curl. Good for a sanity check that pytest can't give you.

---

# Your write-up

Please replace this section before submitting. See `BRIEF.md` §7 for what we're after.

### What's working

All six tasks are complete:

- The autonomy gate handles reads, shadow simulation, supervised approval, and the exact autonomous write budget boundary.
- Verification performs one-to-one subset matching and reports missing and unexpected effects, including simulated effects.
- The agent loop completes, records an audit trail, recovers from normal tool problems, and fails cleanly for unrecoverable model errors or the step cap.
- Model throttles use exponential backoff; fatal model errors are not retried.
- `send_message` is idempotent by key and the start-run HTTP endpoint runs a task end to end.
- The test suite contains focused unit, loop, resilience, idempotency, and HTTP coverage.

### Design decisions

The loop treats unknown tools, tool errors, and reviewer rejection as observations rather than terminal failures. This gives the scripted model another turn and matches how a useful agent should recover. Only a final model intent marks a run completed; invalid model output, provider errors, a missing task, and the maximum step count mark it failed.

Every tool decision and result is added to `run.steps`. Successful writes also become `Effect` objects, with `simulated=True` in shadow mode. The verifier intentionally ignores that flag so shadow runs answer the same correctness question without mutating the workspace.

The verifier tracks claimed effect indexes. This prevents one actual effect from satisfying multiple expectations and lets unclaimed effects be reported as unexpected. An autonomous write is allowed only when `writes_so_far < max_auto_writes`, so a budget of two permits exactly two writes.

`send_message` stores the first result under the caller's idempotency key. Repeated keys return the original message id with `deduped=True` and do not append another workspace message. The existing agent helper supplies a stable run-and-step key when the model does not provide one.

### Testing approach

I wrote the gate and verifier tests before their implementations, using a table for the gate branches and explicit tests for pass, missing, unexpected, and duplicate matching. I then added tests for throttled retries, fatal non-retry behavior, actual workspace idempotency, loop recovery, shadow isolation, the step cap, fatal model handling, and the HTTP start-run path.

The tests deliberately assert on state changes such as `workspace.messages`, `model.calls`, and `run.effects`, rather than only checking returned values. I did not add persistence, real provider, concurrency, or authentication tests because those are explicitly out of scope.

### What was hardest

The most subtle part was keeping governance, execution, and verification separate. A rejected or failed tool call must be visible to the model but must not become an effect, while a simulated write must become an effect even though the workspace stays unchanged. The duplicate-effect rule was another easy place to make a plausible mistake, so I used claimed indexes instead of repeatedly searching the full effects list.

### What I'd do next

I would add structured logging with the run id, make reviewer approval an asynchronous persisted state, and add per-tool policy overrides. I would also improve verdict details to identify the exact missing expectation and add a broader HTTP scenario test for a governed write.

### Time spent

Approximately 4 focused hours, including implementation, tests, and documentation.
