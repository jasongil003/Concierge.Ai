# Controlled Improvement Loop

## Goal

Give the property operator an AI-assisted review loop that can continue until the operator is satisfied while keeping provider choice, authority, pace, and termination under explicit human control.

The loop is advisory. It evaluates the objective, acceptance criteria, supplied evidence, prior iterations, and operator feedback. It does not publish configuration, edit application code, contact guests, or mark itself satisfied.

## Control contract

- The operator chooses the provider and exact model. Any enabled provider may be used, including Gemini, OpenAI, Claude, Groq, OpenRouter, or Local AI.
- The loop never changes the guest-chat default provider.
- `Manual approval` stops after every completed iteration and waits for an operator decision.
- `Continuous advisory` starts another evaluation after the configured interval.
- `0` maximum iterations means unlimited. A positive value is a hard cap.
- The operator may run one iteration, pause, resume, stop, or mark the objective satisfied at any time.
- A model may recommend that the criteria are satisfied, but only the operator can end the loop as satisfied.
- Repeated provider failures automatically move the loop to `error` after the configured threshold.
- Loop state, model responses, decisions, and feedback persist in SQLite.

## State machine

```text
draft -> running -> awaiting_approval -> running
             |              |
             v              v
           paused <---------+
             |
             v
           running

Any active state -> stopped
Any active state -> satisfied (operator only)
Repeated failures -> error -> paused/configured -> running
```

## Delivery plan

### Phase 1: foundation

- Persistent loop and iteration tables
- Provider/model-specific execution through the existing AI provider layer
- Strict state transitions and failure handling
- Server-side background runner with startup recovery
- REST API and unit tests

### Phase 2: operator control center

- Objective, satisfaction criteria, and evidence fields
- Provider and model selectors populated from configured AI connections
- Manual/continuous authority mode
- Interval, iteration cap, and failure threshold controls
- Start, run once, pause, resume, stop, and satisfied controls
- Iteration timeline with score, findings, next action, and decisions

### Phase 3: stronger evidence

- Attach automated test summaries, accessibility reports, and product metrics
- Optional screenshot evidence through a trusted local capture pipeline
- Cost/token budgets by provider
- Named loop templates for UI quality, reliability, security, and content quality

### Phase 4: governed execution

- Optional change proposals as reviewable patches
- Separate reviewer and executor models
- Mandatory test and rollback gates
- Role-based approvals and immutable audit export

Phase 4 must not allow an AI model to modify or publish production state without an explicit operator-approved policy and a recoverable change boundary.
