# PLAN — <Feature/Skill Name>

## 0) Research / recon (do this before planning)
(Spend 15–60 minutes validating the real-world environment.)
- Target URLs/APIs: what’s the *actual* HTML/JSON and access pattern?
- Auth/bot protection/WAF/CDN issues?
- Download endpoints: do they return the real bytes, or an interstitial/viewer?
- Rate limits / ToS constraints?
- Decide early: fully automated vs “human-in-the-loop” steps.
- Output: a short bullet list of confirmed facts + blockers + recommended approach.

## 1) Summary
(What we will build, in 5–10 lines.)

## 2) Architecture
### Modules / boundaries
- `core`:
- `adapters`:
- `cli/tool wrapper`:

### Data model / contracts
- 

## 3) Dependencies
- Library:
  - Why:
  - Alternatives considered:

## 4) Testing plan
### Unit tests
- Scope:
- Key cases:

### Integration tests
- Fixtures:
- Key cases:

## 5) Observability & error handling
- Logging approach:
- Error taxonomy (user error vs system error):

## 6) Security & safety
- Input validation:
- File size caps:
- Safe path handling:

## 7) Decision log (tiny)
- Decision:
  - Rationale:
  - Implications:

## 8) Rollout / verification
- How the main agent/user will verify this works:
