# HF Space Demo Package

**Date:** 2026-06-15  
**Project:** ShopStack  
**Space:** `pranaysuyash/shopstack`

This package captures the end-to-end submission story:

- A real household flow.
- Photos being uploaded, scanned, and converted into inventory / action.
- The mobile-friendly Space experience.
- The public-facing LinkedIn and X copy.

## Demo Goal

Show that ShopStack is not a toy dashboard. It is a working shopping
intelligence workflow:

1. Pick the active household.
2. Upload a shelf/fridge photo and get a decision-oriented scan.
3. Upload a receipt / purchase photo and add items into inventory.
4. Show the "what to buy", "what to use soon", and "what to find at home"
   surfaces reacting to those inputs.

## Recommended Recording Length

- Target: 90 seconds to 2 minutes
- Absolute cap: 3 minutes
- Style: fast, confident, real

## Suggested Recording Flow

### Scene 1: Open the live Space

- Open the HF Space in a browser.
- Let the landing page settle.
- If needed, switch to the correct household in the workspace admin
  accordion so the rest of the flow is recorded against the right home.
  If a dropdown switch does not stick, refresh once and continue with
  the visible household.

### Scene 2: Show the photo-based scan

- Go to `Market Lens: Should I Buy This?`
- Upload a shelf, fridge, or pantry photo.
- Show the scan result: items detected, decisions, and reasons.
- Pause briefly on the "BUY / SKIP / USE SOON" style output.

### Scene 3: Show adding a purchase

- Go to `Add Purchase`.
- Upload a receipt or purchase photo.
- Confirm the item addition flow.
- Show that the inventory / memory surfaces update afterward.

### Scene 4: Show the downstream effect

- Switch to `Use Soon / Waste Saver` or `Plan Today's Shopping`.
- Show the newly updated list / recommendation state.
- Optionally jump to `Find an Item at Home` to show the storage map.

### Scene 5: Close with the product thesis

- End on the Today dashboard or the home screen.
- Let the main product line be visible:
  - know what is at home,
  - know what to buy next,
  - know what to skip,
  - know what to use soon.

## Recording Checklist

Use this as the exact capture order for the screen recording:

1. Open the Space and wait for the initial UI to settle.
2. Show the active household name.
3. Upload a shelf or fridge photo in `Market Lens`.
4. Pause on the detection / decision result.
5. Upload a receipt or purchase photo in `Add Purchase`.
6. Confirm the item is added to inventory.
7. Jump to `Use Soon` or `Today` and show the updated list.
8. Jump to `Find an Item at Home` or `Shopping` to show the same data propagating.
9. End on the home / Today view with the summary line visible.

## Suggested Assets

- One clear shelf or fridge photo with visible pantry items.
- One receipt or purchase photo with enough contrast for OCR.
- Optional second item photo if you want to show a second scan.
- Optional short clip of the household dropdown switch at the start.

## Narration Script

Use these lines as a rough voiceover guide:

1. "ShopStack is a household shopping intelligence app built as a Gradio Space."
2. "I can switch the active household, scan a shelf photo, and get a buy/skip/use-soon decision."
3. "Then I can upload a receipt or purchase photo and turn that into inventory updates."
4. "The downstream screens react immediately: today's shopping, use-soon items, and item lookup all update from the same local data."
5. "It is designed to stay local-first by default, while still supporting a Hugging Face planner backend when configured."

## Shot List

| Time | Shot | What to show |
|------|------|--------------|
| 0:00-0:10 | Opening | HF Space page and title |
| 0:10-0:20 | Household | Active household selection |
| 0:20-0:45 | Shelf scan | Photo upload in Market Lens |
| 0:45-1:10 | Receipt add | Purchase / receipt upload |
| 1:10-1:30 | Downstream | Use Soon / Today / Find at Home update |
| 1:30-2:00 | Close | Product thesis and final state |

## Visual Notes

- Keep the browser zoom at a comfortable mobile-like scale if possible.
- Prefer one or two uploads with clear, legible photos.
- Make sure the feedback text is visible before moving on.
- Avoid too much cursor wandering. The flow should feel deliberate.

## Assets Needed

- 1 shelf/fridge/pantry photo
- 1 receipt or purchase photo
- 1 optional close-up photo for a second scan
- Optional short screen capture of the household switch

## LinkedIn Draft

ShopStack is live on Hugging Face Spaces, and the demo is finally
showing the workflow the product was built for:

- pick the household
- upload a shelf/fridge photo
- scan what is already at home
- upload a receipt or purchase photo
- add the items to inventory
- watch the shopping and "use soon" views update from the same data

It is a local-first household shopping intelligence app, built around
real photo inputs and practical decisions, not a generic chat wrapper.

The current Space deployment is working, and I fixed a PWA route issue
so `/sw.js` is served correctly on Hugging Face Spaces.

If you want the full walkthrough, the demo video shows the end-to-end
flow in one pass.

## X Draft

ShopStack is live on Hugging Face Spaces.

Demo flow:
- switch household
- upload a shelf/fridge photo
- scan items
- upload a receipt / purchase photo
- add to inventory
- watch Today / Use Soon / Find at Home update

Local-first shopping intelligence, not a chat wrapper.
PWA route issue on Spaces is fixed too.

Suggested caption if you want it even tighter:

ShopStack on HF Spaces now shows the real workflow: switch household,
scan a shelf photo, add a purchase photo, and watch inventory plus
shopping views update from the same data.

## Posting Notes

- Use the LinkedIn draft for a fuller product story.
- Use the X draft for a tighter announcement with the workflow bullet list.
- Post the demo video link in both, and keep the HF Space link in the
  first paragraph or first line.
