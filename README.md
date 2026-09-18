# MSI Oracle EBS — Context Pack

A small context pack for building applications against the **Meridian Silicon Inc. (MSI)**
Oracle EBS estate without a semantic layer in front of it.

| File | Purpose |
|---|---|
| `README.md` | This file — orientation. |
| `MSI Oracle EBS Working Notes.md` | The full brief: grounding, table dictionaries, business processes, connectivity gotchas. |

---

## 1. The Claude context

`MSI Oracle EBS Working Notes.md` is written to be dropped into a Claude Code project as
`CLAUDE.md` (or imported from one). It replaces the semantic layer with prose: the things an
ontology would normally enforce — which date column is real, which join is two hops, which
metric definition is defensible — are stated explicitly so the model doesn't have to guess.

**How to use it**

```
your-project/
├── CLAUDE.md          # ← MSI Oracle EBS Working Notes.md
└── src/
```

It is organised in the order you need it:

1. **Grounding** — who MSI is, what they sell, their two concentration risks.
2. **Tables & schemas** — 153 tables, row counts, column dictionaries, join map.
3. **Business processes** — P2P, O2C, R2R, plus the semiconductor-specific flows.
4. **Data & connectivity** — Oracle dialect notes, empty tables, and the traps.

**Why §4 exists.** Almost every wrong answer produced on this dataset came from SQL that
looked correct: using `creation_date` (a load artefact) as a business date, filtering by
`org_id` (one value for the whole company), or joining receipts to open invoices (returns
zero rows by design). Read it before the first query, not after the first bug.

---

## 2. TextQL Refinery

**Refinery is headless TextQL** — the TextQL engine without the TextQL UI, integrated
directly into Claude Code. Claude Code stays your working surface; Refinery is what gives it
governed access to the MSI Oracle EBS estate.

The practical split:

| Layer | Responsibility |
|---|---|
| **Claude Code** | Where you write and iterate — the agent loop, your repo, your files. |
| **Refinery (headless TextQL)** | Connector access and query execution against Oracle EBS, plus the sandbox the results land in. No credentials in your project, no direct DB driver to wire up. |
| **This context pack** | The domain knowledge. Refinery reaches the data; `CLAUDE.md` is what makes the agent query it *correctly*. |

### Why the context pack still matters

Refinery solves reach, not comprehension. Point an agent at 153 raw EBS tables with no
semantic layer and it will produce SQL that runs cleanly and answers the wrong question —
`creation_date` looks like a business date, `org_id` looks like an entity dimension, and
"open invoices with applied receipts" looks like a sensible join. All three are traps here.

That is the gap this pack fills: the notes are the hand-written stand-in for an ontology,
so the agent inherits the conventions instead of rediscovering them per session.

### How the notes were built

Grounded from two sources and reconciled, so the pack starts trustworthy:

1. **Prior work mined** — six MSI threads by David Dixon (3–18 May 2026): financial and
   process performance, two DQ & process-mining assessments, an AR/AP reflagging run, a
   demo-data realism fix, and the Quad A+ deliverable design.
2. **Re-grounded live** — every structural and numeric claim re-executed against Oracle EBS
   on 2026-09-17.
3. **Conflicts documented** — where prior findings and live data disagree, live data wins
   and the divergence is written down rather than silently overwritten. For example: DSO
   appears as 45, 68.6, and 136 days across those threads (all correct under their own
   window and method), and two headline DQ defects — supplier `segment1` and item
   `list_price_per_unit`, both reported 100% NULL in May — are fully populated today.

The rule the pack carries forward: **re-derive, don't quote.** This estate is rebuilt in
phases, and `XX_QUALTERA.XX_BUILD_LOG` is the audit trail of what moved.

---

## 3. Available tables

**153 business tables across 16 schemas** on Oracle Autonomous Data Warehouse. This is a
trimmed EBS — each table carries only the columns the estate needs, so verify against
`ALL_TAB_COLUMNS` before referencing a column you remember from production EBS.

| Schema | Tables | Domain | Key tables |
|---|---:|---|---|
| `AP` | 15 | Accounts Payable | `AP_INVOICES_ALL` (3,000), `AP_HOLDS_ALL` (387), `AP_CHECKS_ALL` (2,600), `AP_SUPPLIERS` (155) |
| `AR` | 10 | Accounts Receivable | `RA_CUSTOMER_TRX_ALL` (5,672), `RA_CUSTOMER_TRX_LINES_ALL` (13,368), `AR_PAYMENT_SCHEDULES_ALL` (5,672) |
| `PO` | 15 | Purchasing | `PO_HEADERS_ALL` (5,000), `PO_LINES_ALL` (11,216), `PO_ACTION_HISTORY` (10,972) |
| `RCV` | 3 | Receiving | `RCV_TRANSACTIONS` (17,002) |
| `INV` | 8 | Inventory | `MTL_SYSTEM_ITEMS_B` (1,000), `MTL_MATERIAL_TRANSACTIONS` (8,501) |
| `OE` | 7 | Order Entry | `OE_ORDER_HEADERS_ALL` (6,000), `OE_ORDER_LINES_ALL` (14,149) |
| `WSH` | 5 | Shipping | `WSH_DELIVERY_DETAILS` (13,368), `WSH_TRIPS` (1,921) |
| `HZ` | 8 | Customers | `HZ_PARTIES` (250), `HZ_CUST_ACCOUNTS` (250) |
| `GL` | 13 | General Ledger | `GL_JE_HEADERS` (8,850), `GL_JE_LINES` (49,753), `GL_LEDGERS` (4), `GL_PERIODS` (28) |
| `XLA` | 5 | Subledger Accounting | `XLA_AE_HEADERS` (8,373), `XLA_AE_LINES` (43,693) |
| `CE` | 4 | Cash Management | `CE_BANK_ACCOUNTS` (4) — **statement tables empty** |
| `HR` | 5 | Org / people | `HR_ALL_ORGANIZATION_UNITS` (44), `PER_ALL_PEOPLE_F` (498) |
| `FND` | 11 | Applications foundation | `FND_USER` (80), `FND_LOOKUP_VALUES` (113) |
| `XX_QUALTERA` | 22 | **MSI customisations** | `XX_EVENT_LOG` (127,679), `XX_ZOBJECT_INVENTORY` (1,847), `XX_FOUNDRY_QUALIFICATIONS` (48) |
| `FIN_CLOSE` | 19 | Separate close mart | **Do not join to EBS** — different demo, keys don't reconcile |
| `TEST_EBS` | 3 | Scratch | Ignore |

**Start here.** `XX_QUALTERA.XX_EVENT_LOG` is the highest-leverage table in the estate: a
pre-conformed process-mining event log of 127,679 events across 8 case types (`PO`, `SO`,
`AR`, `JE`, `XLA`, `PR`, `INV`, `GLPER`), each row carrying case, activity, timestamp,
resource, and lineage back to the source EBS row. Don't rebuild cycle times from base tables
— they're already here, and `event_ts` is the only trustworthy timeline in the database.

**Three facts that shape every query**

- One operating unit: `ORG_ID = 204` on 100% of transaction rows, despite four ledgers.
- Four ledgers (USD / SGD / EUR / INR) but 8,794 of 8,850 journals sit in the US primary.
- Data window: **Jan 2024 → May 2026**, 28 GL periods.

---

*Grounded against the live Oracle EBS connection on 2026-09-17. Prior findings sourced from
six MSI threads by david@textql.com, May 2026.*
