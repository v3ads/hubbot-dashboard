# HubBot Run — 2026-08-19

- **Started:** 2026-08-19T09:03:42-04:00
- **Completed:** 2026-08-19T09:16:55-04:00
- **Status:** complete

## Community Access
- OK — 20 members total, 5 genuinely new, 3 already-welcomed (skipped) since 2026-08-12

## New Members (5)
- Benjamin Parker
- Lillian
- inder grewal
- Nancy Burrell
- Fernando Ceballos

## Welcomes Posted (5)
- Benjamin Parker
- Lillian
- inder grewal
- Nancy Burrell
- Fernando Ceballos

## AI-news Post
- **Title:** Small-business owners now trust AI for insurance advice as much as their own agent
- **Status:** published
- **URL:** https://community.hubactually.com/791723a3-6044-469e-a310-ef9dc6ee5b7b
- **Source:** https://www.insurancebusinessmag.com/us/news/breaking-news/small-business-owners-now-trust-ai-insurance-advice-as-much-as-their-own-agent-survey-finds-586585.aspx
- **Image concept:** Two symbolic chairs at a consultation table: a glowing golden orb representing AI in one seat, an empty chair for a human insurance advisor in the other, a half-signed insurance document and pen on the table, soft morning window light. Hand-painted gouache editorial illustration, muted earthy palette with one golden accent. Concept: AI earning a seat at the high-stakes decision table alongside (not replacing) a human advisor.
- **Image status:** uploaded

## Pre-publish Checks
- image_generated: True
- image_attached: True
- clickable_link: True
- channel_and_author: True
- post_publish_verified_headless: pass
- source_reachable: True

## Owner Alert
- **Status:** sent_via_brevo_by_pipeline (new_members_found). No additional alert sent — the pipeline's alert covered new members; flagged items are recorded in this ledger for owner review and do not require an immediate separate alert (no failed required step, no irreversible action).

## Saturday Digest
- **Status:** not_saturday_skipped

## Blockers (0)

## Flagged Items (3)
- Pipeline defect: welcome mode returned no_op:true (0 genuinely-new) due to a cutoff ordering bug in _build_cutoff_from_ledger. It computes max(run_completed_at_et, 7-day-floor); the default mode of the SAME run wrote run_completed_at_et=now into latest.json before welcome mode read it, so max(now, 7-days-ago)=now and no member who joined earlier today qualified. The default mode's direct 7-day-floor cutoff was correct and found all 5 genuinely-new members. Welcome-once was verified independently (none of the 5 appear in any prior ledger welcomes_posted across 12 backfilled days). Not fixed live per lean rules.
- Browser-backend transient 'internal server error' failures recurred throughout the welcome DM choreography (click actions most affected). Recovered via a page-refresh workaround: the click registered server-side despite the error response, and refreshing landed on the /messages/<thread-id> route with the DM thread open, after which fill+send succeeded. All 5 DMs ultimately sent and verified. No DM was lost, but the flaky backend inflated the run's browser action count.
- Discussion scan false-positive: the open_browser_review verdict listed Hub Bot's OWN prior welcome post (bcb4ae95, 'Welcome our newest member!') as a member thread needing attention. The ID-exclusion caught 1 HubBot post but missed this older one (it predates the recent-threads-by-ID set). Owner's announcement (cd15fe38) also surfaced as 'needs attention' despite 0 comments being appropriate for an owner promo post.

## Recommended Next Actions
- Patch _build_cutoff_from_ledger cutoff ordering so welcome mode does not re-derive cutoff from the current run's just-written ledger (medium priority).
- Tighten discussion_check self/owner-post exclusion (low priority).
- No action needed on welcomes — all 5 genuinely-new members welcomed via DM + public post, welcome-once rule intact.
