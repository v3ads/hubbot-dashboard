# HubBot Run — 2026-08-15

- **Started:** 2026-08-15T09:02:05-04:00
- **Completed:** 2026-08-15T09:22:28-04:00
- **Status:** complete_with_blockers

## Community Access
- OK — 20 members total, 2 genuinely new, 5 already-welcomed (skipped) since 2026-08-08

## New Members (2)
- 
- 

## Welcomes Posted (8)
- Maker Majuec
- Isabella Jo
- Mayur Pote
- Marie Mitchell
- QuoCentric
- serge Panasenko
- Jim Kyser
- Public welcome post in General

## AI-news Post
- **Title:** Google Sheets can now turn your spreadsheet into an interactive mini-app with one prompt
- **Status:** published
- **URL:** https://community.hubactually.com/40e0cf41-5708-43a9-a49e-16d854cbecf2
- **Source:** https://blog.google/products-and-platforms/products/workspace/sheets-canvas-for-google-sheets-spreadsheets/
- **Image concept:** None
- **Image status:** uploaded

## Pre-publish Checks
- image_generated: pass
- image_attached: pass
- clickable_link: pass
- channel_and_author: pass
- post_publish_verified_headless: pass

## Owner Alert
- **Status:** sent_via_brevo

## Saturday Digest
- **Status:** scheduled

## Blockers (1)
- Saturday weekly digest blocked: GetResponse newsletter create failed with HTTP 400

## Flagged Items (3)
- Isabella Jo asked to see how SignalSmith works in her intro thread — a product question directed at the owner. HubBot welcomed her and noted Ayman will follow up, but a personal owner reply/demo would land well.
- Pipeline bug persists: discussion-scan does not exclude HubBot-authored threads (author field empty on API read-back), so HubBot's own 0-comment AI-news posts get flagged as member threads needing attention.
- Saturday digest initially failed with GetResponse HTTP 400. Root cause found and fixed: newsletter payload was missing the required top-level campaign.campaignId. Script hubbot_send_weekly_digest.py patched and committed to repo (commit 8302c89f4e); digest then scheduled successfully for 10:00 AM ET.

## Recommended Next Actions
- Owner to reply to Isabella Jo's SignalSmith question in thread 204c97c8-4e14-4688-9ed9-9c214321c79b.
- Fix discussion-scan to exclude HubBot-authored threads so HubBot's own posts stop being flagged as member threads.
