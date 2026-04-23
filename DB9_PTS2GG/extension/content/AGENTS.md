# AGENTS.md

## Scope
This AGENTS.md applies to files in this folder, especially:
- provider-chatgpt.js
- provider-gemini.js
- injected-monitor-chatgpt.js
- content-script.js

## Purpose
This folder controls browser-side automation for provider UIs.

These files are fragile because provider DOM, aria labels, test ids, and timing frequently change.
When editing here, prioritize reliability under UI changes over elegance.

## Primary goal
For provider files, the goal is to:
1. detect the correct provider composer elements,
2. inject prompt or upload image reliably,
3. submit safely,
4. detect output correctly,
5. fail with useful logs when selectors break.

## Required workflow
When working in this folder:

1. Identify which provider is being changed:
   - ChatGPT
   - Gemini
   - shared content-script glue
   - monitor logic

2. Identify which stage is failing:
   - prompt input detection
   - send button detection
   - upload flow
   - upload confirmation
   - output detection
   - download flow

3. Fix only the failing stage first.

4. Test immediately in browser after each meaningful change.

5. Use real DOM behavior, console output, and page state to guide the next change.

Do not rewrite the full provider unless multiple stages are broken.

## Editing rules
- Keep provider-chatgpt.js isolated from provider-gemini.js.
- Do not mix selector logic across providers.
- Do not introduce app-wide refactors from this folder unless absolutely necessary.
- Prefer small helper functions over large rewrites.
- Preserve the exported interface on window.__DB9_PROVIDER unless explicitly required.
- Keep compatibility with the shared orchestrator in content-script.js.
- Keep existing fallback paths unless a better verified replacement exists.

## Selector strategy
Provider UIs change often. Therefore:

- Prefer stable attributes first:
  - data-testid
  - aria-label
  - id
  - name
  - role
- Then use broader fallback selectors.
- Avoid relying on brittle class names unless there is no better option.
- When adding a fallback selector, keep it narrow enough to avoid false positives.
- If multiple selectors are used, order them from most stable to least stable.
- If possible, score selectors and log which strategy succeeded.

## Smart selector rules
- Prefer selector arrays over one hardcoded selector.
- Try stable selectors first, then semantic fallbacks, then generic fallback.
- Always verify the matched node is visible, connected, and interactive when relevant.
- For prompt inputs, verify the node is editable.
- For submit buttons, verify the node is enabled.
- For upload controls, verify the node can accept files or successfully opens the file picker path.
- Log which selector matched so selector drift is easy to debug.

## Input and submit rules
For prompt input:
- Prefer contenteditable detection that is specific to the composer.
- Do not assume there is only one contenteditable on the page.
- Verify the target is visible and user-editable before typing.
- Do not submit from input code.

For submit:
- Prefer clicking the send button when it is clearly enabled.
- Keep Enter-key fallback only as a fallback.
- Do not submit if the page is still in a blocked or generating state unless that is explicitly intended.

## Upload rules
For uploads:
- Prefer the native hidden file input when available.
- Preserve React-safe file injection behavior.
- Keep paste fallback as backup only.
- After upload, always verify using either:
  - monitor confirmation,
  - visible preview,
  - or another explicit observable signal.

Do not assume upload succeeded just because file input was set.

## Timing and waiting rules
- Avoid hardcoded long sleeps unless there is no better option.
- Prefer polling with timeout over blind waiting.
- Keep waits localized to the stage being verified.
- When a wait fails, log which exact stage timed out.
- When possible, use condition-based waiting instead of fixed delay.

## Logging rules
Logs must help debug selector drift quickly.

- Log the current stage before major actions.
- Log which strategy succeeded:
  - strategy 1
  - strategy 2
  - fallback
- Log timeout failures with the exact stage name.
- Do not spam logs with noisy repeated messages inside tight loops unless useful.
- Prefer logs that identify provider, stage, selector strategy, and result.

## Output detection rules
For generated output:
- Prefer assistant-message-scoped image detection.
- Filter out avatars, icons, and tiny images.
- Require readiness checks before treating an image as final.
- If possible, confirm the image source is stable before download.

## Download rules
- Prefer the highest-fidelity method first.
- Keep direct fetch and canvas fallback behavior.
- Do not remove a working fallback unless a better verified replacement exists.
- If download fails, preserve enough logging to identify whether the failure is:
  - selector,
  - fetch,
  - cross-origin,
  - or canvas-related.

## Debugging checklist
Before making a bigger change, check:
- Is the content script loaded?
- Is the provider file loaded?
- Does prompt input lookup return the right node?
- Is send button lookup returning the real submit control?
- Is the upload control still present?
- Does the provider menu still open?
- Does the upload preview appear?
- Is output detection failing because of timing, selector drift, or filtering?
- Is download failing because of overlay selector or fetch/canvas restrictions?

## Strong defaults
- Small patch over rewrite
- Stable selector over clever selector
- Polling with timeout over blind sleep
- Verified browser behavior over assumption
- Logs that identify failure stage over generic logs

## Verification (MANDATORY)
After changes in this folder, verify as many of these as possible:

1. provider loads without console error
2. prompt is inserted successfully
3. send works
4. upload works if upload path was touched
5. upload confirmation is detected
6. generated output is detected
7. download works if output/download path was touched

If some steps were not verified, say exactly which ones were not tested.

## Final response format
Always end with:
- Plan:
- Changed:
- Verified:
- Assumptions:
- Risks / next step:
