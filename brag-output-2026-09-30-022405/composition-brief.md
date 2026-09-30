# Hyperframes Composition Brief: Concierge.Ai

## Objective
Create a short launch-style brag video for Concierge.Ai, centered on its intended hotel guest Wi-Fi to digital concierge journey.

## Output
- Composition directory: `brag-output-2026-09-30-022405/composition/`
- Rendered video: `brag-output-2026-09-30-022405/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 20 seconds

## Source Material
- Project root: `/Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai`
- Primary files read: `README.md`, `package.json`, `app/static/index.html`, `app/static/styles.css`, `app/static/app.js`
- Product name: Concierge.Ai
- Tagline / strongest claim: “On-prem, AI-powered hotel concierge designed to integrate with guest Wi-Fi and ANTlabs gateways.”
- Key UI or visual moment to recreate: mobile guest home → concierge question → property-informed dining answer
- Copy that must appear verbatim:
  - “The stay starts on Wi-Fi.”
  - “On-prem, AI-powered hotel concierge.”
- Demo copy: “Where can I get breakfast?” / “Breakfast is served in the Garden Room. Want the menu?” Label these fictional sample details inside the phone UI.

## Creative Direction
- Tone preset: polished
- Creative direction: quiet premium hotel welcome, with one crisp phone interaction
- Interpretation: calm light, generous space, restrained motion, and enough hold time for each part of the guest exchange to read.
- Angle: Show how the guest Wi-Fi welcome can lead into a useful on-prem digital concierge experience. Use the actual guest app's structure as the hero instead of a generic feature list. Keep the demo property's fictional facts visibly identified as sample content.
- Hook: “The stay starts on Wi-Fi.”
- Outro / punchline: Concierge.Ai — “On-prem, AI-powered hotel concierge.” Supporting line: “Designed around guest Wi-Fi.”
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign
  - Any claim that Concierge.Ai itself authenticates a guest or opens internet access; ANTlabs remains the authentication authority.

## Visual Identity
- Background: `#fbfcfe`, `#eef2f7`, and `#f6f7f9` from `app/static/styles.css`
- Text: `#111827` primary and `#667085` secondary
- Accent: `#0f766e` teal and `#172033` navy
- Display font: Iowan Old Style / Baskerville / Times New Roman serif stack
- Body font: Geist Sans / Inter / system sans stack
- Visual references from the project: phone guest app; navy-to-teal hotel mark; pale guest home; serif welcome; conversation composer; five-item bottom navigation.
- Use `composition/DESIGN.md` as the composition's visual identity contract; it derives these tokens and type choices from the source guest app.

## Storyboard
Use `brag-plan.md` as the creative contract.

Scene summary:
1. The Wi-Fi welcome — 3.7s — guest Wi-Fi context and readable hook
2. A familiar guest home — 3.7s — real-style guest app home and quick actions
3. Ask — 4.9s — tap Concierge and type a sample property question
4. A useful answer — 5.1s — fictional sample answer and Browse dining action
5. Concierge.Ai — 2.6s — product name and on-prem hotel concierge claim

## Audio
- Audio role: warm, understated business bed with sparse soft UI accents
- Audio arc: music begins softly, supports one tap and the answer reveal, then fades beneath the end card.
- Music: `happy-beats-business-moves-vol-11-by-ende-dot-app.mp3`
- Music treatment: low-to-moderate volume, begin at 0s, fade during the final second.
- Music cue guidance: bundled preset at `../brag/skills/brag/assets/music/cues/happy-beats-business-moves-vol-11-by-ende-dot-app.music-cues.json`; 114.84 BPM. Optional strong-cue targets: 3.70s (UI reveal), 12.65s (answer), 17.91s (wordmark). Preserve reading time; do not beat-sync text.
- Audio-reactive treatment: subtle warmth/shadow breathing on an existing phone or teal accent. No waveform, equalizer, or pulsing text. If the bundled extraction workflow is unavailable, document and skip audio-reactive movement.
- Audio-coupled moments:
  - Scene 3 tap/send — one soft click at the interaction start.
  - Scene 4 answer — quiet reveal accent as the message settles.
  - Scene 5 wordmark — optional restrained final accent.
- SFX selection guidance: use sparse, low high-frequency-risk sounds matched to the tap and answer reveal.
- SFX analysis guidance: `../brag/skills/brag/assets/sfx/sfx-analysis.md`
- Exact SFX choice: choose filenames, timestamps, density, and volume to match the implemented animation.
- Audio files: copy selected tracks into `composition/assets/` and use relative paths.

## Hyperframes Instructions
Create the composition from this brief and `brag-plan.md`. Recreate the guest phone UI from the source HTML/CSS, keep fictional data clearly labeled, and use smooth transitions and readable scene holds. Preserve source palette and type. Build a single 20-second landscape video. Run `npx hyperframes check` before rendering; fix all errors, then render to `../brag.mp4`.
