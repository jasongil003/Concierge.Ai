# Okada Manila trial guest QA report

**Date:** 17 October 2026 (Asia/Manila)

**Browser:** Separate Codex in-app browser; public guest portal and Google Maps route pages

**Overall result:** Blocked. The live guest page rendered but could not initialize the concierge, and secure Admin access was unavailable.

## Executed browser checks

| Check | Result | Evidence |
|---|---|---|
| Open the public guest homepage | PASS, read-only page loaded at http://115.85.36.117:8080/ | Page title “Concierge.Ai”; initial view showed “Okada” and “How can I help with your stay today?” |
| Initialize the guest concierge | FAIL | The conversation panel displayed “Unable to start the concierge: Cross-origin guest mutation denied.” |
| Send a guest question | BLOCKED | The message composer Send button was disabled after initialization failed. No question was submitted. |
| Verify demo disclosure | FAIL / NOT PRESENT IN INITIAL VIEW | The displayed property label was “Okada”; no unofficial-research-demo disclosure was visible in the initial view. This is not proof of the complete landing page state. |
| Check map and in-app directions | BLOCKED | The map editor and property map could not be reached without Admin Portal access. |
| Check mobile layout | NOT RUN | The concierge failed before guest journeys could be exercised. No mobile layout result is claimed. |
| Check guest privacy / cross-property isolation | NOT RUN | No authenticated property or test guest session was available. No guest-specific data was viewed. |

The rejection message corresponds to the configured-origin guard in [app/main.py](</Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai/app/main.py:4051>), which checks that browser mutations come from a configured property or canonical origin. The guard is designed to reject unconfigured origins. This evidence is consistent with a live host/property-origin configuration mismatch; it does not establish the exact setting that needs correction. Do not disable or weaken the guard to make the page work.

## Research-derived answer checks

The following answers are grounded in the official-source research and are the expected content to exercise after a property and knowledge are configured. They are **not** results from the Concierge.AI model.

| Guest question | Expected grounded answer | Live AI result |
|---|---|---|
| Where can I eat Filipino food? | Kiapo serves Filipino cuisine on the Upper Ground Floor, Coral Wing. Check the official page for current hours. | Not executed; concierge failed to start. |
| Which restaurant serves Japanese cuisine? | Enbu, Kappou Yoshi, and Ginza Nagaoka are Japanese dining options. Confirm Ginza Nagaoka hours because official sources conflict. | Not executed; concierge failed to start. |
| Where is Medley Buffet today? | Through 19 October 2026, Medley Buffet is temporarily at Sinag, 3rd Floor, Coral Wing. Usual location: Upper Ground Floor, The Promenade, Pearl Wing. Recheck after the override period. | Not executed; concierge failed to start. |
| Where can my children play? | Okada Kids Club is on the Upper Ground Floor, Coral Wing. Sessions, age rules, and adult-supervision requirements apply; check availability first. | Not executed; concierge failed to start. |
| Where is the nearest shopping mall? | Ayala Malls Manila Bay is a nearby option. A Google Maps route snapshot showed 2.3 km and 8 minutes by car; refresh for current traffic. | Not executed; concierge failed to start. |
| How do I reach The Fountain? | Use Crystal Corridor / Crystal Pavilion as the map reference. The research map does not establish turn-by-turn routing. | Not executed; map editor unavailable. |
| What time is check-out? | An official offer page lists 12:00 noon; confirm the reservation’s own terms. | Not executed; concierge failed to start. |
| Is The Fountain operating tonight? | The official page currently displays an undated adverse-weather notice saying the show is suspended tonight until further notice. Its date is not shown, so confirm with hotel staff whether it remains in effect. | Not executed; concierge failed to start. |
| Can you show me the spa location? | The Retreat Spa is on the 3rd Floor, Pearl Wing. No indoor route is asserted. | Not executed; map editor unavailable. |
| How do I reach the Coral Wing? | The official map names the wing and public entrances, but no verified route graph was established. Give floor/wing orientation or direct the guest to staff; do not invent turns. | Not executed; map editor unavailable. |

Expected model behavior includes recognizing current dated overrides, checking the date before using them, acknowledging unknown live operating status, avoiding unsupported rates or availability, and never claiming a reservation was made.

## Nearby route research

I used Google Maps in the separate in-app browser with driving mode and “Leave now.” The map displayed the following snapshots from the Okada Manila pin on 17 October 2026:

| Destination | Distance | Drive estimate | Route note |
|---|---:|---:|---|
| Ayala Malls Manila Bay | 2.3 km | 8 min | New Seaside Drive and Jose W. Diokno Boulevard northbound |
| SM Mall of Asia | 3.7 km | 18 min | Driving route |
| PARQAL | 2.7 km | 10 min | Jose W. Diokno Boulevard northbound |
| DreamPlay at City of Dreams Manila | 2.7 km | 10 min | Jose W. Diokno Boulevard / Asean Avenue |

These are external research snapshots, not Concierge.AI Nearby results or a routing-provider integration. Times change with traffic. Use the live navigation links in [OKADA_MANILA_CONTENT_MANIFEST.json](OKADA_MANILA_CONTENT_MANIFEST.json).

## Test boundaries and remediation

- No Admin baseline, saved configuration, persistence check, guest portal content check after save, or screenshot evidence could be collected because the Admin Portal failed to load over HTTPS.
- The guest page’s initialization failure is reproduced in the browser. The source guard intentionally denies unknown origins; the live property/domain configuration must be checked through secure Admin access.
- No source change is justified yet. The observation points to deployment/property origin configuration, and weakening the security guard would be unsafe.
- Once secure Admin access is available: inspect existing property/domain settings; correct the canonical guest origin through the supported UI; verify the demo disclaimer; configure content and dated overrides; then repeat guest questions and mobile checks. Test property isolation and map destinations before calling the trial ready.
