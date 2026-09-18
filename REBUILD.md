# Rebuilding The Aging Ledger

This is the O2C "top 100 open items" page (`aging-ledger.html`). The first build took
~25 separate tool calls end to end. This doc is the fast path: **1 command, 3 `refinery`
calls, no manual data-wrangling.**

## Fast path

```bash
python3 build_aging_ledger.py --as-of 2026-09-17
```

That regenerates `aging-ledger.html` from live Oracle EBS data using
`aging-ledger.template.html`. Then publish it (Claude Code's Artifact tool, or just open
the file — it's fully self-contained, no build step, no external data files).

Flags:

| Flag | Default | Purpose |
|---|---|---|
| `--as-of` | today (UTC) | Date to age against. Pass a fixed date to reproduce a past snapshot; omit it to get a true "as of right now" run. |
| `--sandbox` | `o2c-open-items` | Reuses a named `refinery` sandbox instead of spinning up a new one each run. |
| `--out` | `aging-ledger.html` | Output path. |

Total cost of a rerun: **3 `refinery` CLI calls** (2 SQL queries + 1 aggregation script)
plus one local templating pass. No sandbox file writes, no downloads, no palette
iteration, no skill loads.

## What made the first build slow — and what the script now does instead

| Slow thing (first build) | Why it happened | What the fast path does |
|---|---|---|
| `refinery info`, `refinery context --paths-only`, then pulling the **full** org ontology (63KB) just to grep it for relevance | Followed the refinery skill's "mandatory first step" literally, before knowing the org's ontology had nothing MSI-specific in it | Skip it. This project's `CLAUDE.md` is already the verified, dataset-specific source of truth — the generic org ontology doesn't apply here. Only worth re-checking if the *org's* ontology changes, not on every rerun of this page. |
| 6+ separate SQL queries (open-item summary, top-100, full aging by bucket, full customer concentration, distinct customer count, DSO, partial-payment check) each as its own round trip | Explored the data interactively, one question at a time, which is the right way to explore but the wrong way to rerun | Pull the **entire 918-row open-item population once** (one query), plus 2 small lookups (paid-population DSO, top-5 revenue). Every other number — aging buckets, concentration, register, KPI tiles — is computed locally from that one dataframe in a single `exec python` call. |
| Writing results to a file in the sandbox, then downloading via a signed URL with `curl` | Used the "write file + read artifact" pattern by default | The aggregated JSON (~15KB) is well under the CLI's 400,000-char output cap, so the script just prints it to stdout with a `@@RESULT@@` marker and parses it directly. No file round-trip. |
| Iterating on the aging-ramp color palette (4 failed `validate_palette.js` attempts before finding hex values that passed the ordinal checks) | Designed the palette from scratch, by trial and error, against the validator | The passing hex values are now baked into the template's CSS (`--age-1` … `--age-6`, one ordinal ramp validated in both light and dark). A rerun never touches color — it only refreshes data. |
| A hand-written placeholder swap for one JSON blob (`top100.json`), done as an ad hoc one-off | Built the page once, not designed for reruns | The template (`aging-ledger.template.html`) has **29 named placeholders** — every mechanically-derived number, JS data block, and even several narrative sentences — filled by one script in one pass. |
| A real bug this exercise surfaced: grouping customers by `PARTY_NAME` undercounted (134 → 132) because a handful of `HZ_PARTIES` names are duplicated across distinct `PARTY_ID`s (e.g. two different companies both named "Pulse Automation SA") | Not previously documented anywhere, including this project's `CLAUDE.md` | The query and script now carry `PARTY_ID` through and group by it, never by name alone. Worth adding to `CLAUDE.md`'s data-quality notes if this comes up again. |

Net effect: **~25 tool calls → 3 CLI calls + 1 local script run.**

## What the script does NOT auto-update

The page's prose is templated for every number, but a few things are still worth a human
glance after a rerun, especially if you change `--as-of` by more than a few weeks:

- **Whether the story is still true.** The current narrative ("the same accounts drive
  revenue and AR risk") holds because it happens to be true of this snapshot. If a future
  run shows different customers at the top, the callout text will *say* the right numbers
  (it's data-driven now) but double-check it still reads naturally.
- **The `~45–47 day top-quartile benchmark`** in Exhibit 4, callout 04 — that's an external
  APQC/Hackett-style reference figure, not something in the warehouse. It won't go stale
  from data changes, but if you ever want to update the benchmark itself, it's hardcoded
  in the template.
- **`DATA_WINDOW`** ("Jan 2024 – May 2026, 28 GL periods") is hardcoded in
  `build_aging_ledger.py` — update it there if the source data's window changes.

## Files

- `aging-ledger.template.html` — the page with placeholders (`__LIKE_THIS__`) instead of
  data. Edit this file for design/copy changes; never hand-edit the generated
  `aging-ledger.html` directly, since the next rebuild will overwrite it.
- `build_aging_ledger.py` — runs the 3 `refinery` calls, computes every KPI/chart/table
  value, fills the template, writes `aging-ledger.html`.
- `aging-ledger.html` — the generated, publish-ready output.

## Requirements

- `refinery` CLI installed and authenticated (`refinery auth status`).
- Read access to connector 7357 ("Oracle EBS") in this org.
- Python 3 with `pandas` — but only *locally* isn't required; the aggregation itself runs
  remotely in the `refinery` sandbox, which already has `pandas` preinstalled. The local
  half of the script (`build_aging_ledger.py`) uses only the standard library.
