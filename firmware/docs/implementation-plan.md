# Desk firmware implementation plan

Goal: useful ESP-IDF C desk companion with a tested LifeOS API adapter.
Spec: design.md. Constraints: firmware/ ownership, pinout first, no hardware/ edits,
public repo, no secrets, PR and green CI before merge, fetch/rebase before merging.

- [x] Publish docs/pinout.md and coordinate with PCB work.
- [x] Write failing host tests for CRC, conversion, FIFO overflow/ack, JSON bounds,
      malformed responses and framebuffer clipping; implement desk_core and run.
- [x] Write failing adapter tests for schedule selection, dedup, authentication,
      upstream writes/retry/conflict; implement adapter and run full host suite.
- [x] Implement IDF driver and task orchestration against the tested interfaces;
      add reproducible Docker CI build, configuration and operator documentation.
- [ ] Fresh-context whole-branch review, fix material findings, run full suite,
      open PR; fetch/rebase origin/main, push and merge once CI passes.

Review focus: a partial network failure must never erase samples; bad JSON must
not replace cached events; invalid UTC must remain explicit; absent peripherals
must not prevent sleep; retrying an accepted reading must not duplicate logs.
