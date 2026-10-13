# ECC Intelligent Guest Concierge Audit

**Review target:** `jasongil003/Concierge.Ai` commit `4c75d2745831a80ab6633956476eb0259b4fc290`  
**Local worktree:** `codex/guest-concierge-premium-2026-10-13`, based on the exact review SHA  
**Disposition:** **FAIL for a real hotel pilot.** Navigation, dialog accessibility, sessions, the previous GitHub browser failure, and synthetic request flows now pass their relevant gates. Local grounding improvements make known hotel facts retrieval-backed and source-tagged, but the free-form AI claim filter is heuristic and has not been proven against a live provider or real property corpus. These local edits are uncommitted and have no GitHub Actions result.

## PASS / FAIL matrix

| Gate | Result | Evidence / limit |
|---|---|---|
| Latest commit identity | PASS | Local `HEAD` is exactly `4c75d2745831a80ab6633956476eb0259b4fc290`. |
| GitHub Actions for target SHA | PASS | All 10 jobs succeeded, including browser, backend, integration, static security, dependency security, secret scan, Docker, and Linux/macOS deployment validation. [Run 38357045441](https://github.com/jasongil003/Concierge.Ai/actions/runs/38357045441). |
| Previously failing browser job | PASS on latest SHA | Prior log identifies the session test race; latest browser job passes 300 tests with 38 skipped. [Prior failed job](https://github.com/jasongil003/Concierge.Ai/actions/runs/38348166556/job/115134286790), [latest browser job](https://github.com/jasongil003/Concierge.Ai/actions/runs/38357045441/job/115162252242). |
| Guest route navigation, direct custom-page URL, refresh, Back/Forward, `history.state` | PASS | Responsive route/history Playwright matrix passed in Chromium and mobile Chrome. |
| Dialog keyboard containment, Escape, focus restoration, inert background, load errors | PASS | Guest dialog Playwright flows passed in Chromium and mobile Chrome, including memory, map, and native staff dialog. |
| Guest session resume and property boundary | PASS | Session reload/resume and cross-property host restart tests passed in both browser projects. |
| Published, property-scoped guest inventory | PASS in synthetic data | Guest retrieval uses the active session property and guest-visible stores; cross-property facility and knowledge tests pass. Live property data is unverified. |
| Grounded factual cards and provenance | PASS for implemented structured paths | Restaurant, facility, service, map, external-place and profile detail blocks carry property-scoped source IDs. Restaurant period/status flow now has an end-to-end test. |
| Price, hours, availability and free-form hallucination prevention | **FAIL / not established** | Deterministic listed facts and unsupported-price fallback are tested. The final free-form response guard is pattern-based; it cannot prove entailment for arbitrary language. No live model/provider evaluation was available. |
| Housekeeping/request review and persistence | PASS with synthetic configuration | Request review requires explicit confirmation; the backend verifies the current property catalog before creating a scoped record and returning its ID/status. |
| Responsive browser suite | PASS | Final full Playwright on the completed local tree: 303 passed, 37 skipped in 5.9 minutes across Chromium and mobile Chrome. |
| Backend suite | PASS | Final local full suite: 1,145 passed, 18 skipped, 2 deprecation warnings. Persistent application SQLite snapshot remained unchanged. |
| Accessibility | PASS for targeted checks; full WCAG audit unverified | Focus/name/inert/touch/contrast checks passed. No axe run, screen-reader testing, or physical iOS/Android device testing. |
| Local static security | PASS | Bandit at CI severity/confidence thresholds exited 0. `node --check`, Python compile, and `git diff --check` passed. |
| Local package audits | UNVERIFIED locally | `npm audit` and `pip-audit` could not reach package services because network DNS was unavailable. Target SHA GitHub dependency and Python dependency jobs both passed. |
| CI for local uncommitted changes | UNVERIFIED | Local fixes have not been pushed and must receive their own remote checks before release. |
| Real hotel pilot readiness | **FAIL** | Grounding completeness and live property/provider behavior remain release blockers. Do not pilot. |

## Findings

### ECC-INTEL-01 — Hotel fact grounding is improved locally, but not proven complete — **P1, pilot blocker remains**

**Root cause.** The existing chat flow supplied property and retrieved context to the model, but the old output validator did not verify that hotel facts in generated prose were entailed by that context. Prompt instructions alone could not guarantee factuality.

**Local remediation.** Added guest-visible, property-scoped retrieval for published knowledge, public profile facts, enabled guest services, active facilities, restaurants, published menu items, and current external place results. Known fact questions now return deterministic claims/cards or an explicit unavailable-information fallback. Factual blocks and entity cards carry bounded `guest:<property>:<record-type>:<record-id>` references. AI output is buffered until a last-mile hospitality/price/time/availability scan runs, so unreviewed tokens are not streamed to the guest; unsupported claims fall back to concierge contact. The guest renderer validates and retains source IDs as inert metadata.

**Residual risk.** The free-form validator in [guest_grounding.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/app/guest_grounding.py>) is a conservative lexical/pattern check, not semantic entailment. Open-vocabulary facilities, indirect claims, or future response styles may evade it. The source IDs are internal references, not human-readable citations with a source-detail view. No production credentials, real hotel content, or live provider were used. Therefore this remediation reduces known risk but does **not** establish the requested “never invents” guarantee.

**Files.** [main.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/app/main.py>), [guest_grounding.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/app/guest_grounding.py>), [intelligent_ui.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/app/intelligent_ui.py>), [guest_v2/app.js](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/app/guest_v2/app.js>), [operations.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/app/operations.py>), [places.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/app/places.py>), and grounding/context/UI tests.

**Evidence.** [test_guest_grounding.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/tests/test_guest_grounding.py>), [test_ai_context.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/tests/test_ai_context.py>), [test_intelligent_ui.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/tests/test_intelligent_ui.py>); 1,145 backend tests pass. These tests establish the listed known cases only, not universal factuality.

### ECC-INTEL-02 — Meal-specific restaurant cards could include unrelated venues and hide unavailable status — **P2, fixed locally**

**Root cause.** The card adapter selected every guest-visible restaurant for a food query, even when configured meal periods excluded the requested meal, and did not show non-open restaurant status. The breakfast fast path could also answer a price question with breakfast hours.

**Change.** Meal-specific queries now require a configured matching period (including explicit all-day service); unspecified or mismatched records are not presented as matching. Cards and source-backed claims display closed/capacity/unavailable status. A price question without a matching published menu item gets a clear verification fallback; breakfast hours no longer intercept price questions.

**Files.** [main.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/app/main.py>), [test_intelligent_ui.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/tests/test_intelligent_ui.py>), [guest.spec.js](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/tests/e2e/guest.spec.js>).

**Evidence.** Backend regression asserts dinner filtering, hidden disabled records, visible “Temporarily closed,” source ID, and unavailable-price fallback. An end-to-end test creates a synthetic dinner restaurant through the actual admin API, sends a guest chat turn through the real concierge API, then verifies the sourced closed-status card at 320, 390 and 1440 px in both browser projects (2 passed).

### ECC-INTEL-03 — Previous GitHub browser failure was a test timing race — **P2, fixed in target commit**

**Actual failing test and log.** The previous run (`38348166556`, browser job `115134286790`) failed on Chromium and mobile Chrome at `tests/e2e/guest-premium.spec.js:141` (remote test line 150): “guest session resumes on reload within the current property.” It asserted `sessionStorage.getItem("concierge-session-id")` immediately after the hotel heading appeared and received `null`; the page had rendered before the `/api/session/start` response completed. The job ended `2 failed, 38 skipped, 292 passed (9.0m)`. This was a race in the test assertion, not evidence that a stored session was incorrectly resumed.

**Resolution/evidence.** The target commit waits for the actual session-start response before reading the ID, and waits for the session-resume response after reload. Its browser job is green: `300 passed, 38 skipped (6.3m)`. The latest run’s other nine jobs also passed.

### ECC-INTEL-04 — Empty-property browser fixture did not isolate the service catalog — **P2, fixed locally in test fixture**

**Root cause.** The test replaced the guest home inventory but left the seeded service catalog live, so a locally seeded property did not meet the test’s “empty property” premise.

**Change/evidence.** `installEmptyProperty` now returns an empty `/api/guest/service-catalog` response. The empty-property journey passes on Chromium and mobile Chrome. No product service-catalog behavior changed for this finding.

**File.** [guest-premium.spec.js](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/tests/e2e/guest-premium.spec.js>).

### Previous ECC navigation and modal findings — **P2, verified passing**

The target commit’s route handling uses published custom-page slugs for core navigation and processes `popstate` without pushing a new history entry. Menu/dialog changes preserve the actual invoking header control as the focus-return target, contain focus, mark the background inert for custom dialogs, and give the native staff dialog an explicit name. The browser suite verifies direct custom-page entry, refresh, Back/Forward and `history.state`; it also checks keyboard containment/restoration, modal error cleanup, inert state, guest-session continuity and cross-property rejection on desktop and mobile.

## Concierge scenarios and limits

| Scenario | Result | Evidence / limit |
|---|---|---|
| Restaurant/dinner question | PASS, synthetic property | Actual browser-to-backend turn returns only configured meal-period matches with current non-open status and restaurant source ID. |
| Hotel information and facility hours | PASS, configured data | Profile/facility details are sourced; an E2E question renders configured pool hours/location. |
| Prices | PASS for matched published menu records; otherwise fallback | Backend tests prove matched menu price provenance and no-price fallback. Real menu content is unverified. |
| Local attractions | PASS with synthetic place result | Details and directions UI are covered; no live Places provider/API key was exercised. Third-party directions content is not hotel-verified. |
| Facility map | PASS with synthetic configured map | Map markers, source IDs, text alternative, missing-map fallback and request error states are covered. Real hotel map accuracy is unverified. |
| Extra pillow/housekeeping | PASS with synthetic service catalog | Proposal/review precedes confirmation; backend verifies enabled service in the guest’s property and persists a request with returned ID/status. No live housekeeping dispatch channel was exercised. |
| Request status/My Requests | PASS, synthetic record | Created request appears with status; cancellation journey passes. Operational receipt/fulfillment by a hotel team is unverified. |
| Empty property and cross-property | PASS in isolated synthetic setup | Empty views do not fabricate inventory; sessions and knowledge/facilities stay scoped. |

## Accessibility, browser, and visual evidence

The final full browser run on the completed local tree passed **303 tests with 37 skipped in 5.9 minutes** across Chromium and mobile Chrome. This includes the synthetic restaurant-card flow through the real guest API. The final full backend suite passed **1,145 tests, 18 skipped**. Python compile, JavaScript syntax checks, `git diff --check`, and Bandit passed.

The manual browser inventory saw 2,117 visible control instances and 2,082 focusable controls, with zero enabled non-focusable controls, zero missing accessible names, and no invalid composite widgets. Dialog focus/inert/error flows passed; tested privacy text contrast remained at least 4.5:1. These are focused automated checks, not a complete WCAG audit. Screen readers, physical mobile devices, and a third-party axe scan were not run.

The responsive guest matrix includes Home, Concierge, Explore, Requests, My Stay, and a custom guest page at 320, 375, 390, 430, 768, 1024, 1440 and 1920 px. The full local run retained 53 PNGs under `/tmp/concierge-ai-4c75-final/` (synthetic property data):

- [Home at 320 px](/tmp/concierge-ai-4c75-final/home/320.png)
- [Concierge at 1440 px](/tmp/concierge-ai-4c75-final/concierge/1440.png)
- [Custom guest page at 390 px](/tmp/concierge-ai-4c75-final/custom-page/390.png)
- [Explore at 1920 px](/tmp/concierge-ai-4c75-final/explore/1920.png)

Guest responsive and browser journeys recorded no unexpected page errors or failed requests. Manual QA test outputs that overwrite tracked baseline screenshots were restored; generated screenshots are not committed.

## Changed local files

Implementation: `app/guest_grounding.py`, `app/main.py`, `app/intelligent_ui.py`, `app/guest_v2/app.js`, `app/operations.py`, and `app/places.py`.

Coverage/fixture corrections: `tests/test_guest_grounding.py`, `tests/test_intelligent_ui.py`, `tests/test_ai_context.py`, `tests/test_guest_personal_home.py`, `tests/test_service_catalog.py`, `tests/test_properties.py`, `tests/e2e/guest.spec.js`, and `tests/e2e/guest-premium.spec.js`.

All changes remain local and uncommitted. No deployment, merge, production database write, or push was performed. The exact review SHA’s GitHub CI is green, but the local remediation must run through GitHub Actions on its own revision. **Release recommendation: do not start a real hotel pilot until grounding completeness is resolved and provider-backed, property-data acceptance testing passes.**
