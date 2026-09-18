# MSI (Meridian Silicon Inc.) — Oracle EBS Working Notes

> **What this file is.** A hand-off brief for anyone building against the MSI Oracle EBS
> database *without* a semantic layer or ontology in front of it. Everything below was
> verified against the live database on **2026-09-17**, and cross-read against the six MSI
> analysis threads authored by **David Dixon (david@textql.com, 3–18 May 2026)**.
>
> **How to use it.** Read §1 for what MSI is, §2 for what tables exist, §3 for how the
> business actually runs, §4 before you write a single query. §4 exists because most of
> the wrong answers produced on this dataset came from plausible-looking SQL, not from
> broken SQL.
>
> **How to actually run a query.** This repository holds no code and no direct database
> credentials — it is reference documentation only. Query the live Oracle EBS connector
> through the `refinery` CLI (see `~/.claude/skills/refinery/SKILL.md`); do not attempt to
> connect with a raw DB driver or invent connection strings.

---

## 1. Grounding — what is MSI?

**Meridian Silicon Inc. (MSI) is a fictional-but-production-shaped fabless semiconductor
company**, modelled in an Oracle EBS schema on Oracle Autonomous Data Warehouse. It is a
demo/reference estate, not a real customer system — but the data volumes, process defects,
and control weaknesses are deliberately realistic, so treat it as production when you build.

### 1.1 Who they are

| Attribute | Value |
|---|---|
| Legal top node | `Meridian Silicon Inc.` (business group + legal entity, in `HR_ALL_ORGANIZATION_UNITS`) |
| Subsidiaries | Meridian Silicon US Corp, Singapore, Ireland, India |
| Ledgers | 4 — MSI Primary **USD**, Singapore **SGD**, Ireland **EUR**, India **INR** |
| Model | **Fabless** — designs chips, outsources wafer fab, packaging, and test |
| Business units | Sales–Mobile, Sales–Auto & IoT, Sales–AI & Compute |
| Finance orgs | Office of the CFO, Controllership, Treasury, Tax, Internal Audit, AP Ops, AR Ops |
| Procurement orgs | Direct–Foundry, Direct–EDA & IP, Indirect |
| Data window | **Jan 2024 → May 2026**, 28 GL periods |
| Scale in-window | ~$5.64B billed revenue, ~$3.33B AP invoice spend |

The org structure is the giveaway that this is a semiconductor company rather than a generic
manufacturer: a dedicated **Direct Procurement – Foundry** org and a **Direct Procurement –
EDA & IP** org only exist in companies that buy wafers and design tooling.

### 1.2 What they sell

Five product pillars, visible in `INV.MTL_SYSTEM_ITEMS_B` where the item code encodes
family and process node (`MSM-3nm-7700` = modem, 3nm; `MRF-55nm-8927` = RF front-end, 55nm):

| Family | Prefix | Typical nodes | Competes with |
|---|---|---|---|
| Cellular modems | `MSM-` | 3nm / 4nm / 5nm | Qualcomm Snapdragon X-series, MediaTek |
| AI accelerators | `MAI-` | 3nm / 4nm | edge-AI / NPU players |
| Automotive SoC | `MAU-` | 3nm / 4nm / 7nm | Snapdragon Ride, NVIDIA DRIVE, Mobileye |
| RF front-end | `MRF-` | 55nm / 28nm / 16nm / 7nm | Qorvo, Skyworks, Broadcom RF |
| IoT connectivity | `MIO-` | 7nm / 16nm / 28nm | Silicon Labs, NXP, Nordic |

Dixon's read, which holds up: **a portfolio that mirrors Qualcomm's at roughly 5% of the
scale** — unusual, and the reason MSI is interesting as a case study. Positioned as a
~$2.4–2.5B specialty fabless designer, peer band = Lattice / Silicon Labs / Synaptics /
Marvell, with Qualcomm, Broadcom, NVIDIA, AMD as watched benchmarks.

### 1.3 Who they buy from and sell to — the two concentration facts

These two numbers drive most of the analysis anyone will ask you for.

**Supply side** (share of AP invoice amount, all history):

| Supplier | Spend | Share | Role |
|---|---:|---:|---|
| TaiwanFab Corp | $1,177.6M | **35.3%** | wafer foundry (the TSMC analogue) |
| Unimicron Technology | $159.2M | 4.8% | substrates |
| Powertech Technology | $149.1M | 4.5% | assembly & test (OSAT) |
| SUMCO Corporation | $147.9M | 4.4% | silicon wafers |
| Ibiden Co Ltd | $114.9M | 3.4% | substrates |
| Amkor Technology | $111.3M | 3.3% | OSAT |
| ASE Technology Holding | $90.1M | 2.7% | OSAT |
| Shin-Etsu Chemical | $89.4M | 2.7% | materials |

Everything else is indirect (FedEx, AWS, Cisco, AT&T). Note that Dixon's threads quote
TaiwanFab at **49% and 54%** — those were computed on narrower windows (TTM, named-vendor
only). On full history it is 35.3%. **Always state your window.**

**Demand side** (share of billed revenue):

| Customer | Revenue | Share |
|---|---:|---:|
| Apex Mobile Inc | $1,304.4M | **21.8%** |
| Helia Devices Co Ltd | $716.2M | 12.0% |
| Aurion Distribution Inc | $582.5M | 9.7% |
| Vantek Components LLC | $548.3M | 9.2% |
| Cipher Computing Corp | $151.9M | 2.5% |

**Top 4 = 52.7% of revenue.** Losing Apex Mobile is the single largest modelled risk in the
dataset, and it is the finding every executive-facing deliverable has led with.

---

## 2. Available tables, schemas, and what each is for

**153 business tables across 16 schemas.** This is a *trimmed* EBS — each table carries only
the columns the demo needs, so do not assume the full Oracle EBS column set exists. Always
check `ALL_TAB_COLUMNS` before referencing a column you remember from real EBS.

```sql
-- your first query in any new session
SELECT owner, table_name, num_rows
FROM   all_tables
WHERE  owner IN ('GL','AP','AR','PO','INV','OE','HZ','FND','XLA','CE','RCV','WSH','HR',
                 'XX_QUALTERA','FIN_CLOSE')
ORDER  BY owner, table_name;
```

### 2.1 Schema map

| Schema | Tables | What it is | Use it for |
|---|---:|---|---|
| `AP` | 15 | Accounts Payable | supplier invoices, holds, payments, DPO, 3-way match |
| `AR` | 10 | Accounts Receivable | customer invoices, receipts, aging, DSO |
| `PO` | 15 | Purchasing | requisitions, POs, approvals, releases, archives |
| `RCV` | 3 | Receiving | goods receipt — the middle leg of the 3-way match |
| `INV` | 8 | Inventory | item master, on-hand, material transactions |
| `OE` | 7 | Order Entry | sales orders, lines, holds, sales credits |
| `WSH` | 5 | Shipping | deliveries, trips, trip stops |
| `HZ` | 8 | Trading Community | customer parties, accounts, sites, credit profiles |
| `GL` | 13 | General Ledger | journals, balances, periods, code combinations, FX |
| `XLA` | 5 | Subledger Accounting | sub-ledger → GL bridge, audit trail |
| `CE` | 4 | Cash Management | bank accounts (**statement tables are empty**) |
| `HR` | 5 | HR / org | org units, locations, people, assignments |
| `FND` | 11 | Applications foundation | users, lookups, concurrent requests |
| `XX_QUALTERA` | 22 | **MSI custom schema** | event log, custom-object inventory, semiconductor extensions, build snapshots |
| `FIN_CLOSE` | 19 | Separate close mart | unrelated star schema — see §4.7 |
| `TEST_EBS` | 3 | Scratch | ignore |

### 2.2 Row counts — full inventory

| Table | Rows |
|---|---:|
| `AP_BANK_ACCOUNTS_ALL` | 4 |
| `AP_BATCHES_ALL` | 29 |
| `AP_CHECKS_ALL` | 2,600 |
| `AP_HOLDS_ALL` | 387 |
| `AP_INVOICES_ALL` | 3,000 |
| `AP_INVOICE_DISTRIBUTIONS_ALL` | 5,066 |
| `AP_INVOICE_LINES_ALL` | 5,066 |
| `AP_INVOICE_PAYMENTS_ALL` | 2,600 |
| `AP_INV_APRVL_HIST_ALL` | 6,000 |
| `AP_PAYMENT_SCHEDULES_ALL` | 3,000 |
| `AP_SUPPLIERS` | 155 |
| `AP_SUPPLIERS_ATTRIBUTES` | 155 |
| `AP_SUPPLIER_CONTACTS` | 0 |
| `AP_SUPPLIER_SITES_ALL` | 155 |
| `AP_TERMS` | 6 |
| `AR_ADJUSTMENTS_ALL` | 269 |
| `AR_CASH_RECEIPTS_ALL` | 5,150 |
| `AR_CASH_RECEIPT_HISTORY_ALL` | 4,358 |
| `AR_COLLECTORS` | 10 |
| `AR_CORRESPONDENCE_PAY_SCHED` | 1,731 |
| `AR_PAYMENT_SCHEDULES_ALL` | 5,672 |
| `AR_RECEIVABLE_APPLICATIONS_ALL` | 5,150 |
| `RA_CM_REQUESTS` | 457 |
| `RA_CUSTOMER_TRX_ALL` | 5,672 |
| `RA_CUSTOMER_TRX_LINES_ALL` | 13,368 |
| `PO_ACTION_HISTORY` | 10,972 |
| `PO_AGENTS` | 20 |
| `PO_DISTRIBUTIONS_ALL` | 11,216 |
| `PO_HEADERS_ALL` | 5,000 |
| `PO_HEADERS_ARCHIVE_ALL` | 3,026 |
| `PO_LINES_ALL` | 11,216 |
| `PO_LINES_ARCHIVE_ALL` | 6,780 |
| `PO_LINE_LOCATIONS_ALL` | 11,216 |
| `PO_LINE_LOCATIONS_ARCHIVE_ALL` | 6,780 |
| `PO_LINE_TYPES_B` | 4 |
| `PO_RELEASES_ALL` | 1,192 |
| `PO_RELEASES_ARCHIVE_ALL` | 744 |
| `PO_REQUISITION_HEADERS_ALL` | 4,000 |
| `PO_REQUISITION_LINES_ALL` | 6,707 |
| `PO_REQ_DISTRIBUTIONS_ALL` | 6,707 |
| `RCV_SHIPMENT_HEADERS` | 8,501 |
| `RCV_SHIPMENT_LINES` | 8,501 |
| `RCV_TRANSACTIONS` | 17,002 |
| `MTL_CATEGORIES_B` | 7 |
| `MTL_ITEM_CATEGORIES` | 1,000 |
| `MTL_MATERIAL_TRANSACTIONS` | 8,501 |
| `MTL_ONHAND_QUANTITIES_DETAIL` | 2,740 |
| `MTL_PARAMETERS` | 7 |
| `MTL_SYSTEM_ITEMS_B` | 1,000 |
| `MTL_SYSTEM_ITEMS_TL` | 0 |
| `MTL_UNITS_OF_MEASURE` | 13 |
| `OE_ORDER_HEADERS_ALL` | 6,000 |
| `OE_ORDER_HOLDS_ALL` | 452 |
| `OE_ORDER_LINES_ALL` | 14,149 |
| `OE_ORDER_SOURCES` | 5 |
| `OE_PRICE_ADJUSTMENTS` | 562 |
| `OE_SALES_CREDITS` | 6,000 |
| `OE_TRANSACTION_TYPES_ALL` | 11 |
| `WSH_DELIVERY_ASSIGNMENTS` | 13,368 |
| `WSH_DELIVERY_DETAILS` | 13,368 |
| `WSH_NEW_DELIVERIES` | 5,672 |
| `WSH_TRIPS` | 1,921 |
| `WSH_TRIP_STOPS` | 3,842 |
| `HZ_CUSTOMER_PROFILES` | 250 |
| `HZ_CUST_ACCOUNTS` | 250 |
| `HZ_CUST_ACCT_SITES_ALL` | 250 |
| `HZ_CUST_PROFILE_AMTS` | 250 |
| `HZ_CUST_SITE_USES_ALL` | 500 |
| `HZ_LOCATIONS` | 250 |
| `HZ_PARTIES` | 250 |
| `HZ_PARTY_SITES` | 250 |
| `GL_BALANCES` | 4,168 |
| `GL_CODE_COMBINATIONS` | 256 |
| `GL_CONSOLIDATION` | 1 |
| `GL_DAILY_RATES` | 2,428 |
| `GL_IMPORT_REFERENCES` | 43,487 |
| `GL_INTERCOMPANY_ACC_SETS` | 1 |
| `GL_INTERFACE` | 200 |
| `GL_JE_BATCHES` | 163 |
| `GL_JE_HEADERS` | 8,850 |
| `GL_JE_LINES` | 49,753 |
| `GL_LEDGERS` | 4 |
| `GL_PERIODS` | 28 |
| `GL_SETS_OF_BOOKS` | 1 |
| `XLA_AE_HEADERS` | 8,373 |
| `XLA_AE_LINES` | 43,693 |
| `XLA_DISTRIBUTION_LINKS` | 43,693 |
| `XLA_EVENTS` | 8,373 |
| `XLA_TRANSACTION_ENTITIES` | 8,373 |
| `CE_BANK_ACCOUNTS` | 4 |
| `CE_BANK_ACCT_USES_ALL` | 0 |
| `CE_STATEMENT_HEADERS` | 0 |
| `CE_STATEMENT_LINES` | 0 |
| `HR_ALL_ORGANIZATION_UNITS` | 44 |
| `HR_LOCATIONS_ALL` | 11 |
| `PER_ADDRESSES` | 0 |
| `PER_ALL_ASSIGNMENTS_F` | 498 |
| `PER_ALL_PEOPLE_F` | 498 |
| `FND_APPLICATION` | 16 |
| `FND_CONCURRENT_REQUESTS` | 463 |
| `FND_CURRENCIES` | 12 |
| `FND_FLEX_VALUES` | 0 |
| `FND_FLEX_VALUE_SETS` | 0 |
| `FND_LOOKUP_TYPES` | 18 |
| `FND_LOOKUP_VALUES` | 113 |
| `FND_RESPONSIBILITY_TL` | 0 |
| `FND_TERRITORIES_TL` | 0 |
| `FND_USER` | 80 |
| `FND_USER_RESP_GROUPS_DIRECT` | 0 |
| `XX_BUILD_LOG` | 22 |
| `XX_CMRT_ATTESTATIONS` | 242 |
| `XX_DESIGN_REGISTRATIONS` | 679 |
| `XX_DQ_PROFILE` | 0 |
| `XX_EVENT_LOG` | 127,679 |
| `XX_EXPORT_CONTROL_CLASS` | 641 |
| `XX_FOUNDRY_QUALIFICATIONS` | 48 |
| `XX_PHASE10_B1_PAY_SNAPSHOT` | 2,600 |
| `XX_PHASE10_B1_SNAPSHOT` | 3,000 |
| `XX_PHASE10_B2_SNAPSHOT` | 6,000 |
| `XX_PHASE10_B3_SNAPSHOT` | 5,000 |
| `XX_PHASE10_B4_AP_SNAPSHOT` | 2,600 |
| `XX_PHASE10_B4_MISC_SNAPSHOT` | 21,781 |
| `XX_PHASE10_B4_OE_SNAPSHOT` | 6,000 |
| `XX_PHASE10_B5_JELINES_SNAPSHOT` | 14,610 |
| `XX_PHASE10_B6_XLA_SNAPSHOT` | 15,255 |
| `XX_PHASE10_B7_CCID_SNAPSHOT` | 256 |
| `XX_REVENUE_RESERVE_LEDGER` | 28 |
| `XX_STAGE_POSTBUILD_SNAPSHOT` | 122 |
| `XX_STAGE_PREBUILD_SNAPSHOT` | 125 |
| `XX_STAGE_USER_MAP` | 80 |
| `XX_ZOBJECT_INVENTORY` | 1,847 |
| `DAILY_METRICS` | 900 |
| `DIM_ACCOUNT` | 32 |
| `DIM_CALENDAR` | 13 |
| `DIM_COST_CENTER` | 12 |
| `DIM_ENTITY` | 4 |
| `DIM_VENDOR` | 8 |
| `FX_RATES` | 78 |
| `GL_BALANCES` | 4,524 |
| `GL_JOURNAL_LINES` | 12 |
| `HEADCOUNT` | 28 |
| `JE_LINES` | 18 |
| `PAY_RATES` | 276 |
| `PL_ACTUALS` | 360 |
| `PROPOSED_JOURNAL_ENTRIES` | 9 |
| `RECON_ITEMS` | 52 |
| `REVENUE_CONTRACTS` | 52 |
| `SCENARIO_DRIVERS` | 12 |
| `SOURCE_SUPPORT` | 8 |
| `SUBLEDGER_BALANCES` | 52 |

### 2.3 Column dictionaries — the tables you will actually touch

#### Accounts Payable

**`AP.AP_INVOICES_ALL`** — the AP spine. 3,000 rows. `po_header_id` NULL = non-PO invoice (709 rows, 23.6%)

| Column | Type | Null? |
|---|---|---|
| `INVOICE_ID` | NUMBER | NO |
| `INVOICE_NUM` | VARCHAR2 | NO |
| `VENDOR_ID` | NUMBER | yes |
| `VENDOR_SITE_ID` | NUMBER | yes |
| `INVOICE_DATE` | DATE | yes |
| `INVOICE_AMOUNT` | NUMBER | yes |
| `INVOICE_CURRENCY_CODE` | VARCHAR2 | yes |
| `EXCHANGE_RATE` | NUMBER | yes |
| `EXCHANGE_DATE` | DATE | yes |
| `PAYMENT_CURRENCY_CODE` | VARCHAR2 | yes |
| `TERMS_ID` | NUMBER | yes |
| `TERMS_DATE` | DATE | yes |
| `DESCRIPTION` | VARCHAR2 | yes |
| `BATCH_ID` | NUMBER | yes |
| `INVOICE_TYPE_LOOKUP_CODE` | VARCHAR2 | yes |
| `PAYMENT_STATUS_FLAG` | VARCHAR2 | yes |
| `APPROVAL_STATUS` | VARCHAR2 | yes |
| `CANCELLED_DATE` | DATE | yes |
| `CANCELLED_AMOUNT` | NUMBER | yes |
| `GL_DATE` | DATE | yes |
| `SET_OF_BOOKS_ID` | NUMBER | yes |
| `SOURCE` | VARCHAR2 | yes |
| `PO_HEADER_ID` | NUMBER | yes |
| `QUICK_PO_HEADER_ID` | NUMBER | yes |
| `ORG_ID` | NUMBER | yes |
| `AMOUNT_PAID` | NUMBER | yes |
| `DISCOUNT_AMOUNT_TAKEN` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |
| `APPROVED_AMOUNT` | NUMBER | yes |

**`AP.AP_INVOICE_LINES_ALL`** — 5,066 lines

| Column | Type | Null? |
|---|---|---|
| `INVOICE_ID` | NUMBER | NO |
| `LINE_NUMBER` | NUMBER | NO |
| `LINE_TYPE_LOOKUP_CODE` | VARCHAR2 | yes |
| `AMOUNT` | NUMBER | yes |
| `QUANTITY_INVOICED` | NUMBER | yes |
| `UNIT_PRICE` | NUMBER | yes |
| `DESCRIPTION` | VARCHAR2 | yes |
| `PO_HEADER_ID` | NUMBER | yes |
| `PO_LINE_ID` | NUMBER | yes |
| `PO_LINE_LOCATION_ID` | NUMBER | yes |
| `PO_DISTRIBUTION_ID` | NUMBER | yes |
| `MATCH_TYPE` | VARCHAR2 | yes |
| `ACCOUNTING_DATE` | DATE | yes |
| `DIST_CODE_COMBINATION_ID` | NUMBER | yes |
| `DISCARDED_FLAG` | VARCHAR2 | yes |
| `CANCELLED_FLAG` | VARCHAR2 | yes |
| `ORG_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`AP.AP_HOLDS_ALL`** — 387 rows, one per held invoice. `hold_lookup_code` = Quantity / Price / Freight / …

| Column | Type | Null? |
|---|---|---|
| `HOLD_ID` | NUMBER | NO |
| `INVOICE_ID` | NUMBER | NO |
| `LINE_LOCATION_ID` | NUMBER | yes |
| `HOLD_LOOKUP_CODE` | VARCHAR2 | yes |
| `HOLD_TYPE` | VARCHAR2 | yes |
| `HOLD_DATE` | DATE | yes |
| `HOLD_REASON` | VARCHAR2 | yes |
| `RELEASE_LOOKUP_CODE` | VARCHAR2 | yes |
| `RELEASE_REASON` | VARCHAR2 | yes |
| `STATUS_FLAG` | VARCHAR2 | yes |
| `HELD_BY` | NUMBER | yes |
| `RELEASED_BY` | NUMBER | yes |
| `ORG_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |
| `RELEASE_DATE` | DATE | yes |

**`AP.AP_CHECKS_ALL`** — payment documents. Join via AP_INVOICE_PAYMENTS_ALL, never directly to invoices

| Column | Type | Null? |
|---|---|---|
| `CHECK_ID` | NUMBER | NO |
| `CHECK_NUMBER` | NUMBER | NO |
| `CHECK_DATE` | DATE | yes |
| `VENDOR_ID` | NUMBER | yes |
| `VENDOR_SITE_ID` | NUMBER | yes |
| `AMOUNT` | NUMBER | yes |
| `CURRENCY_CODE` | VARCHAR2 | yes |
| `BANK_ACCOUNT_ID` | NUMBER | yes |
| `PAYMENT_METHOD_CODE` | VARCHAR2 | yes |
| `STATUS_LOOKUP_CODE` | VARCHAR2 | yes |
| `CLEARED_DATE` | DATE | yes |
| `CLEARED_AMOUNT` | NUMBER | yes |
| `VOID_DATE` | DATE | yes |
| `ORG_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`AP.AP_INVOICE_PAYMENTS_ALL`** — the invoice ↔ check bridge

| Column | Type | Null? |
|---|---|---|
| `INVOICE_PAYMENT_ID` | NUMBER | NO |
| `INVOICE_ID` | NUMBER | NO |
| `CHECK_ID` | NUMBER | NO |
| `PAYMENT_NUM` | NUMBER | yes |
| `AMOUNT` | NUMBER | yes |
| `DISCOUNT_TAKEN` | NUMBER | yes |
| `DISCOUNT_LOST` | NUMBER | yes |
| `PAYMENT_BASE_AMOUNT` | NUMBER | yes |
| `ACCOUNTING_DATE` | DATE | yes |
| `PERIOD_NAME` | VARCHAR2 | yes |
| `SET_OF_BOOKS_ID` | NUMBER | yes |
| `POSTED_FLAG` | VARCHAR2 | yes |
| `ACCRUAL_POSTED_FLAG` | VARCHAR2 | yes |
| `CASH_POSTED_FLAG` | VARCHAR2 | yes |
| `ORG_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`AP.AP_SUPPLIERS`** — 155 suppliers. `segment1` = supplier code (populated as of Sep 2026 — was 100% NULL in May)

| Column | Type | Null? |
|---|---|---|
| `VENDOR_ID` | NUMBER | NO |
| `VENDOR_NAME` | VARCHAR2 | NO |
| `SEGMENT1` | VARCHAR2 | yes |
| `VENDOR_TYPE_LOOKUP_CODE` | VARCHAR2 | yes |
| `ENABLED_FLAG` | VARCHAR2 | yes |
| `START_DATE_ACTIVE` | DATE | yes |
| `END_DATE_ACTIVE` | DATE | yes |
| `NUM_1099` | VARCHAR2 | yes |
| `TYPE_1099` | VARCHAR2 | yes |
| `PAYMENT_METHOD_LOOKUP_CODE` | VARCHAR2 | yes |
| `PAYMENT_PRIORITY` | NUMBER | yes |
| `TERMS_ID` | NUMBER | yes |
| `ALWAYS_TAKE_DISC_FLAG` | VARCHAR2 | yes |
| `PAY_GROUP_LOOKUP_CODE` | VARCHAR2 | yes |
| `WOMEN_OWNED_FLAG` | VARCHAR2 | yes |
| `SMALL_BUSINESS_FLAG` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |


#### Accounts Receivable

**`AR.RA_CUSTOMER_TRX_ALL`** — customer invoice headers, 5,672

| Column | Type | Null? |
|---|---|---|
| `CUSTOMER_TRX_ID` | NUMBER | NO |
| `TRX_NUMBER` | VARCHAR2 | NO |
| `TRX_DATE` | DATE | yes |
| `BILL_TO_CUSTOMER_ID` | NUMBER | yes |
| `BILL_TO_SITE_USE_ID` | NUMBER | yes |
| `SHIP_TO_CUSTOMER_ID` | NUMBER | yes |
| `SHIP_TO_SITE_USE_ID` | NUMBER | yes |
| `CUST_TRX_TYPE_ID` | NUMBER | yes |
| `COMPLETE_FLAG` | VARCHAR2 | yes |
| `INVOICE_CURRENCY_CODE` | VARCHAR2 | yes |
| `EXCHANGE_RATE` | NUMBER | yes |
| `EXCHANGE_DATE` | DATE | yes |
| `SALESREP_ID` | NUMBER | yes |
| `PAYMENT_TERM_ID` | NUMBER | yes |
| `PRINTING_COUNT` | NUMBER | yes |
| `PRINTING_LAST_PRINTED` | DATE | yes |
| `STATUS_TRX` | VARCHAR2 | yes |
| `SET_OF_BOOKS_ID` | NUMBER | yes |
| `ORG_ID` | NUMBER | yes |
| `INTERFACE_HEADER_ATTRIBUTE1` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`AR.RA_CUSTOMER_TRX_LINES_ALL`** — 13,368 lines. `extended_amount` is the revenue column

| Column | Type | Null? |
|---|---|---|
| `CUSTOMER_TRX_LINE_ID` | NUMBER | NO |
| `CUSTOMER_TRX_ID` | NUMBER | NO |
| `LINE_NUMBER` | NUMBER | yes |
| `LINE_TYPE` | VARCHAR2 | yes |
| `QUANTITY_INVOICED` | NUMBER | yes |
| `UNIT_SELLING_PRICE` | NUMBER | yes |
| `UNIT_STANDARD_PRICE` | NUMBER | yes |
| `EXTENDED_AMOUNT` | NUMBER | yes |
| `TAX_RATE` | NUMBER | yes |
| `REVENUE_AMOUNT` | NUMBER | yes |
| `INVENTORY_ITEM_ID` | NUMBER | yes |
| `DESCRIPTION` | VARCHAR2 | yes |
| `SALES_ORDER` | VARCHAR2 | yes |
| `SALES_ORDER_LINE` | VARCHAR2 | yes |
| `INTERFACE_LINE_ATTRIBUTE6` | VARCHAR2 | yes |
| `ORG_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`AR.AR_PAYMENT_SCHEDULES_ALL`** — open/closed AR. `status` OP/CL, `amount_due_remaining` = open balance

| Column | Type | Null? |
|---|---|---|
| `PAYMENT_SCHEDULE_ID` | NUMBER | NO |
| `CUSTOMER_TRX_ID` | NUMBER | yes |
| `CASH_RECEIPT_ID` | NUMBER | yes |
| `CLASS` | VARCHAR2 | yes |
| `DUE_DATE` | DATE | yes |
| `AMOUNT_DUE_ORIGINAL` | NUMBER | yes |
| `AMOUNT_DUE_REMAINING` | NUMBER | yes |
| `AMOUNT_APPLIED` | NUMBER | yes |
| `AMOUNT_CREDITED` | NUMBER | yes |
| `AMOUNT_ADJUSTED` | NUMBER | yes |
| `STATUS` | VARCHAR2 | yes |
| `NUMBER_OF_DUE_DATES` | NUMBER | yes |
| `TERMS_SEQUENCE_NUMBER` | NUMBER | yes |
| `GL_DATE` | DATE | yes |
| `GL_DATE_CLOSED` | DATE | yes |
| `ACTUAL_DATE_CLOSED` | DATE | yes |
| `ORG_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |
| `TRX_DATE` | DATE | yes |
| `CUSTOMER_ID` | NUMBER | yes |

**`AR.AR_CASH_RECEIPTS_ALL`** — cash in, 5,150

| Column | Type | Null? |
|---|---|---|
| `CASH_RECEIPT_ID` | NUMBER | NO |
| `RECEIPT_NUMBER` | VARCHAR2 | NO |
| `AMOUNT` | NUMBER | yes |
| `CURRENCY_CODE` | VARCHAR2 | yes |
| `PAY_FROM_CUSTOMER` | NUMBER | yes |
| `CUSTOMER_SITE_USE_ID` | NUMBER | yes |
| `RECEIPT_DATE` | DATE | yes |
| `RECEIPT_METHOD_ID` | NUMBER | yes |
| `STATUS` | VARCHAR2 | yes |
| `TYPE` | VARCHAR2 | yes |
| `DEPOSIT_DATE` | DATE | yes |
| `GL_DATE` | DATE | yes |
| `ORG_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`AR.AR_RECEIVABLE_APPLICATIONS_ALL`** — receipt → schedule application. See §4.4 — only ever points at CLOSED schedules

| Column | Type | Null? |
|---|---|---|
| `RECEIVABLE_APPLICATION_ID` | NUMBER | NO |
| `CASH_RECEIPT_ID` | NUMBER | yes |
| `APPLIED_CUSTOMER_TRX_ID` | NUMBER | yes |
| `APPLIED_PAYMENT_SCHEDULE_ID` | NUMBER | yes |
| `AMOUNT_APPLIED` | NUMBER | yes |
| `STATUS` | VARCHAR2 | yes |
| `APPLICATION_TYPE` | VARCHAR2 | yes |
| `APPLY_DATE` | DATE | yes |
| `GL_DATE` | DATE | yes |
| `DISPLAY` | VARCHAR2 | yes |
| `ORG_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |


#### Purchasing and receiving

**`PO.PO_HEADERS_ALL`** — 5,000 POs. `approved_date` NULL = never approved (121 rows)

| Column | Type | Null? |
|---|---|---|
| `PO_HEADER_ID` | NUMBER | NO |
| `SEGMENT1` | VARCHAR2 | NO |
| `TYPE_LOOKUP_CODE` | VARCHAR2 | yes |
| `VENDOR_ID` | NUMBER | yes |
| `VENDOR_SITE_ID` | NUMBER | yes |
| `VENDOR_CONTACT_ID` | NUMBER | yes |
| `AGENT_ID` | NUMBER | yes |
| `AUTHORIZATION_STATUS` | VARCHAR2 | yes |
| `APPROVED_DATE` | DATE | yes |
| `CURRENCY_CODE` | VARCHAR2 | yes |
| `RATE` | NUMBER | yes |
| `RATE_DATE` | DATE | yes |
| `RATE_TYPE` | VARCHAR2 | yes |
| `TERMS_ID` | NUMBER | yes |
| `SHIP_TO_LOCATION_ID` | NUMBER | yes |
| `BILL_TO_LOCATION_ID` | NUMBER | yes |
| `CLOSED_CODE` | VARCHAR2 | yes |
| `CANCEL_FLAG` | VARCHAR2 | yes |
| `FROZEN_FLAG` | VARCHAR2 | yes |
| `ORG_ID` | NUMBER | yes |
| `BLANKET_TOTAL_AMOUNT` | NUMBER | yes |
| `AMOUNT_LIMIT` | NUMBER | yes |
| `COMMENTS` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`PO.PO_LINES_ALL`** — 11,216 lines — the item/node detail that reveals the product portfolio

| Column | Type | Null? |
|---|---|---|
| `PO_LINE_ID` | NUMBER | NO |
| `PO_HEADER_ID` | NUMBER | NO |
| `LINE_NUM` | NUMBER | yes |
| `LINE_TYPE_ID` | NUMBER | yes |
| `ITEM_ID` | NUMBER | yes |
| `ITEM_DESCRIPTION` | VARCHAR2 | yes |
| `CATEGORY_ID` | NUMBER | yes |
| `UNIT_MEAS_LOOKUP_CODE` | VARCHAR2 | yes |
| `QUANTITY` | NUMBER | yes |
| `UNIT_PRICE` | NUMBER | yes |
| `AMOUNT` | NUMBER | yes |
| `CLOSED_CODE` | VARCHAR2 | yes |
| `CANCEL_FLAG` | VARCHAR2 | yes |
| `ORG_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`PO.PO_ACTION_HISTORY`** — 10,972 approval actions — the audit trail for PO approvals

| Column | Type | Null? |
|---|---|---|
| `OBJECT_ID` | NUMBER | NO |
| `OBJECT_TYPE_CODE` | VARCHAR2 | yes |
| `OBJECT_SUB_TYPE_CODE` | VARCHAR2 | yes |
| `SEQUENCE_NUM` | NUMBER | NO |
| `ACTION_CODE` | VARCHAR2 | yes |
| `ACTION_DATE` | DATE | yes |
| `EMPLOYEE_ID` | NUMBER | yes |
| `APPROVAL_PATH_ID` | NUMBER | yes |
| `NOTE` | VARCHAR2 | yes |
| `OBJECT_REVISION_NUM` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`RCV.RCV_TRANSACTIONS`** — 17,002 = 8,501 receipts × RECEIVE + DELIVER

| Column | Type | Null? |
|---|---|---|
| `TRANSACTION_ID` | NUMBER | NO |
| `SHIPMENT_HEADER_ID` | NUMBER | yes |
| `SHIPMENT_LINE_ID` | NUMBER | yes |
| `PO_HEADER_ID` | NUMBER | yes |
| `PO_LINE_ID` | NUMBER | yes |
| `PO_LINE_LOCATION_ID` | NUMBER | yes |
| `PO_DISTRIBUTION_ID` | NUMBER | yes |
| `TRANSACTION_TYPE` | VARCHAR2 | yes |
| `TRANSACTION_DATE` | DATE | yes |
| `QUANTITY` | NUMBER | yes |
| `UNIT_OF_MEASURE` | VARCHAR2 | yes |
| `PRIMARY_QUANTITY` | NUMBER | yes |
| `ORGANIZATION_ID` | NUMBER | yes |
| `DESTINATION_TYPE_CODE` | VARCHAR2 | yes |
| `INSPECTION_STATUS_CODE` | VARCHAR2 | yes |
| `PARENT_TRANSACTION_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |


#### Order to cash

**`OE.OE_ORDER_HEADERS_ALL`** — 6,000 orders. `booked_date` NULL = never booked (249 = cancelled)

| Column | Type | Null? |
|---|---|---|
| `HEADER_ID` | NUMBER | NO |
| `ORDER_NUMBER` | NUMBER | NO |
| `ORG_ID` | NUMBER | yes |
| `ORDER_TYPE_ID` | NUMBER | yes |
| `SOLD_TO_ORG_ID` | NUMBER | yes |
| `SHIP_TO_ORG_ID` | NUMBER | yes |
| `INVOICE_TO_ORG_ID` | NUMBER | yes |
| `ORDER_SOURCE_ID` | NUMBER | yes |
| `ORDERED_DATE` | DATE | yes |
| `BOOKED_DATE` | DATE | yes |
| `BOOKED_FLAG` | VARCHAR2 | yes |
| `CANCELLED_FLAG` | VARCHAR2 | yes |
| `OPEN_FLAG` | VARCHAR2 | yes |
| `FLOW_STATUS_CODE` | VARCHAR2 | yes |
| `TRANSACTIONAL_CURR_CODE` | VARCHAR2 | yes |
| `SALESREP_ID` | NUMBER | yes |
| `PRICE_LIST_ID` | NUMBER | yes |
| `PAYMENT_TERM_ID` | NUMBER | yes |
| `FREIGHT_TERMS_CODE` | VARCHAR2 | yes |
| `SHIPPING_METHOD_CODE` | VARCHAR2 | yes |
| `REQUEST_DATE` | DATE | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |
| `TRANSACTION_PHASE_CODE` | VARCHAR2 | yes |

**`OE.OE_ORDER_LINES_ALL`** — 14,149 lines

| Column | Type | Null? |
|---|---|---|
| `LINE_ID` | NUMBER | NO |
| `HEADER_ID` | NUMBER | NO |
| `LINE_NUMBER` | NUMBER | yes |
| `ORDERED_ITEM` | VARCHAR2 | yes |
| `INVENTORY_ITEM_ID` | NUMBER | yes |
| `ORDERED_QUANTITY` | NUMBER | yes |
| `ORDER_QUANTITY_UOM` | VARCHAR2 | yes |
| `UNIT_SELLING_PRICE` | NUMBER | yes |
| `UNIT_LIST_PRICE` | NUMBER | yes |
| `SCHEDULE_SHIP_DATE` | DATE | yes |
| `ACTUAL_SHIPMENT_DATE` | DATE | yes |
| `ACTUAL_FULFILLMENT_DATE` | DATE | yes |
| `FULFILLED_FLAG` | VARCHAR2 | yes |
| `CANCELLED_FLAG` | VARCHAR2 | yes |
| `OPEN_FLAG` | VARCHAR2 | yes |
| `FLOW_STATUS_CODE` | VARCHAR2 | yes |
| `LINE_CATEGORY_CODE` | VARCHAR2 | yes |
| `SHIP_TO_ORG_ID` | NUMBER | yes |
| `INVOICE_TO_ORG_ID` | NUMBER | yes |
| `ORG_ID` | NUMBER | yes |
| `TAX_VALUE` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |


#### General Ledger and subledger

**`GL.GL_JE_HEADERS`** — 8,850 journals. Use `default_effective_date` / `period_name`, NOT `creation_date` (§4.1)

| Column | Type | Null? |
|---|---|---|
| `JE_HEADER_ID` | NUMBER | NO |
| `JE_BATCH_ID` | NUMBER | NO |
| `LEDGER_ID` | NUMBER | yes |
| `SET_OF_BOOKS_ID` | NUMBER | yes |
| `JE_CATEGORY` | VARCHAR2 | NO |
| `JE_SOURCE` | VARCHAR2 | NO |
| `PERIOD_NAME` | VARCHAR2 | yes |
| `NAME` | VARCHAR2 | NO |
| `DESCRIPTION` | VARCHAR2 | yes |
| `STATUS` | VARCHAR2 | yes |
| `CURRENCY_CODE` | VARCHAR2 | yes |
| `CURRENCY_CONVERSION_RATE` | NUMBER | yes |
| `CURRENCY_CONVERSION_TYPE` | VARCHAR2 | yes |
| `CURRENCY_CONVERSION_DATE` | DATE | yes |
| `ACTUAL_FLAG` | VARCHAR2 | yes |
| `DEFAULT_EFFECTIVE_DATE` | DATE | yes |
| `POSTED_DATE` | DATE | yes |
| `RUNNING_TOTAL_DR` | NUMBER | yes |
| `RUNNING_TOTAL_CR` | NUMBER | yes |
| `RUNNING_TOTAL_ACCOUNTED_DR` | NUMBER | yes |
| `RUNNING_TOTAL_ACCOUNTED_CR` | NUMBER | yes |
| `REVERSED_JE_HEADER_ID` | NUMBER | yes |
| `ACCRUAL_REV_FLAG` | VARCHAR2 | yes |
| `EXTERNAL_REFERENCE` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`GL.GL_JE_LINES`** — 49,753 lines

| Column | Type | Null? |
|---|---|---|
| `JE_HEADER_ID` | NUMBER | NO |
| `JE_LINE_NUM` | NUMBER | NO |
| `LEDGER_ID` | NUMBER | yes |
| `SET_OF_BOOKS_ID` | NUMBER | yes |
| `CODE_COMBINATION_ID` | NUMBER | yes |
| `PERIOD_NAME` | VARCHAR2 | yes |
| `EFFECTIVE_DATE` | DATE | yes |
| `STATUS` | VARCHAR2 | yes |
| `ENTERED_DR` | NUMBER | yes |
| `ENTERED_CR` | NUMBER | yes |
| `ACCOUNTED_DR` | NUMBER | yes |
| `ACCOUNTED_CR` | NUMBER | yes |
| `CURRENCY_CODE` | VARCHAR2 | yes |
| `CURRENCY_CONVERSION_RATE` | NUMBER | yes |
| `DESCRIPTION` | VARCHAR2 | yes |
| `REFERENCE_1` | VARCHAR2 | yes |
| `REFERENCE_2` | VARCHAR2 | yes |
| `REFERENCE_4` | VARCHAR2 | yes |
| `REFERENCE_5` | VARCHAR2 | yes |
| `SUBLEDGER_DOC_SEQUENCE_VALUE` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`GL.GL_CODE_COMBINATIONS`** — 256 accounts — segment1=company, segment2=cost centre, segment3=natural account

| Column | Type | Null? |
|---|---|---|
| `CODE_COMBINATION_ID` | NUMBER | NO |
| `CHART_OF_ACCOUNTS_ID` | NUMBER | yes |
| `SEGMENT1` | VARCHAR2 | yes |
| `SEGMENT2` | VARCHAR2 | yes |
| `SEGMENT3` | VARCHAR2 | yes |
| `SEGMENT4` | VARCHAR2 | yes |
| `SEGMENT5` | VARCHAR2 | yes |
| `SEGMENT6` | VARCHAR2 | yes |
| `ENABLED_FLAG` | VARCHAR2 | yes |
| `SUMMARY_FLAG` | VARCHAR2 | yes |
| `DETAIL_POSTING_ALLOWED_FLAG` | VARCHAR2 | yes |
| `DETAIL_BUDGETING_ALLOWED_FLAG` | VARCHAR2 | yes |
| `ACCOUNT_TYPE` | VARCHAR2 | yes |
| `START_DATE_ACTIVE` | DATE | yes |
| `END_DATE_ACTIVE` | DATE | yes |
| `DESCRIPTION` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`GL.GL_PERIODS`** — 28 periods, Jan 2024 → Apr 2026

| Column | Type | Null? |
|---|---|---|
| `PERIOD_SET_NAME` | VARCHAR2 | NO |
| `PERIOD_NAME` | VARCHAR2 | NO |
| `PERIOD_TYPE` | VARCHAR2 | yes |
| `PERIOD_YEAR` | NUMBER | yes |
| `PERIOD_NUM` | NUMBER | yes |
| `START_DATE` | DATE | NO |
| `END_DATE` | DATE | NO |
| `CLOSING_STATUS` | VARCHAR2 | yes |
| `ADJUSTMENT_PERIOD_FLAG` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`XLA.XLA_AE_HEADERS`** — 8,373 accounting events — the subledger→GL audit bridge (43,693 lines)

| Column | Type | Null? |
|---|---|---|
| `AE_HEADER_ID` | NUMBER | NO |
| `APPLICATION_ID` | NUMBER | NO |
| `LEDGER_ID` | NUMBER | yes |
| `ENTITY_ID` | NUMBER | yes |
| `EVENT_ID` | NUMBER | yes |
| `ACCOUNTING_DATE` | DATE | yes |
| `PERIOD_NAME` | VARCHAR2 | yes |
| `GL_TRANSFER_STATUS_CODE` | VARCHAR2 | yes |
| `GL_TRANSFER_DATE` | DATE | yes |
| `JE_CATEGORY_NAME` | VARCHAR2 | yes |
| `ACCOUNTING_ENTRY_STATUS_CODE` | VARCHAR2 | yes |
| `ACCOUNTING_ENTRY_TYPE_CODE` | VARCHAR2 | yes |
| `DESCRIPTION` | VARCHAR2 | yes |
| `BALANCE_TYPE_CODE` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |


#### Inventory / item master

**`INV.MTL_SYSTEM_ITEMS_B`** — 1,000 items. `segment1` encodes family+node. `list_price_per_unit` now populated (§4.5)

| Column | Type | Null? |
|---|---|---|
| `INVENTORY_ITEM_ID` | NUMBER | NO |
| `ORGANIZATION_ID` | NUMBER | NO |
| `SEGMENT1` | VARCHAR2 | yes |
| `DESCRIPTION` | VARCHAR2 | yes |
| `PRIMARY_UOM_CODE` | VARCHAR2 | yes |
| `ITEM_TYPE` | VARCHAR2 | yes |
| `INVENTORY_ITEM_STATUS_CODE` | VARCHAR2 | yes |
| `LIST_PRICE_PER_UNIT` | NUMBER | yes |
| `PURCHASING_ENABLED_FLAG` | VARCHAR2 | yes |
| `CUSTOMER_ORDER_ENABLED_FLAG` | VARCHAR2 | yes |
| `INTERNAL_ORDER_ENABLED_FLAG` | VARCHAR2 | yes |
| `SHIPPABLE_ITEM_FLAG` | VARCHAR2 | yes |
| `COSTING_ENABLED_FLAG` | VARCHAR2 | yes |
| `INVENTORY_ASSET_FLAG` | VARCHAR2 | yes |
| `BUYER_ID` | NUMBER | yes |
| `PLANNER_CODE` | VARCHAR2 | yes |
| `WEIGHT_UOM_CODE` | VARCHAR2 | yes |
| `UNIT_WEIGHT` | NUMBER | yes |
| `VOLUME_UOM_CODE` | VARCHAR2 | yes |
| `UNIT_VOLUME` | NUMBER | yes |
| `EXPENSE_ACCOUNT` | NUMBER | yes |
| `ENCUMBRANCE_ACCOUNT` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`INV.MTL_MATERIAL_TRANSACTIONS`** — 8,501 movements

| Column | Type | Null? |
|---|---|---|
| `TRANSACTION_ID` | NUMBER | NO |
| `INVENTORY_ITEM_ID` | NUMBER | NO |
| `ORGANIZATION_ID` | NUMBER | NO |
| `TRANSACTION_TYPE_ID` | NUMBER | yes |
| `TRANSACTION_ACTION_ID` | NUMBER | yes |
| `TRANSACTION_SOURCE_TYPE_ID` | NUMBER | yes |
| `TRANSACTION_SOURCE_ID` | NUMBER | yes |
| `TRANSACTION_DATE` | DATE | yes |
| `TRANSACTION_QUANTITY` | NUMBER | yes |
| `TRANSACTION_UOM` | VARCHAR2 | yes |
| `PRIMARY_QUANTITY` | NUMBER | yes |
| `TRANSACTION_COST` | NUMBER | yes |
| `SUBINVENTORY_CODE` | VARCHAR2 | yes |
| `TRANSFER_ORGANIZATION_ID` | NUMBER | yes |
| `TRANSFER_SUBINVENTORY` | VARCHAR2 | yes |
| `SHIPMENT_NUMBER` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |


#### Customers

**`HZ.HZ_PARTIES`** — 250 parties — `party_name` is the display name for customers

| Column | Type | Null? |
|---|---|---|
| `PARTY_ID` | NUMBER | NO |
| `PARTY_NUMBER` | VARCHAR2 | NO |
| `PARTY_NAME` | VARCHAR2 | NO |
| `PARTY_TYPE` | VARCHAR2 | NO |
| `STATUS` | VARCHAR2 | yes |
| `CATEGORY_CODE` | VARCHAR2 | yes |
| `DUNS_NUMBER` | NUMBER | yes |
| `SIC_CODE` | VARCHAR2 | yes |
| `TAX_REFERENCE` | VARCHAR2 | yes |
| `COUNTRY` | VARCHAR2 | yes |
| `ADDRESS1` | VARCHAR2 | yes |
| `CITY` | VARCHAR2 | yes |
| `STATE` | VARCHAR2 | yes |
| `POSTAL_CODE` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |

**`HZ.HZ_CUST_ACCOUNTS`** — 250 accounts; bridges HZ_PARTIES to AR via `cust_account_id`

| Column | Type | Null? |
|---|---|---|
| `CUST_ACCOUNT_ID` | NUMBER | NO |
| `PARTY_ID` | NUMBER | NO |
| `ACCOUNT_NUMBER` | VARCHAR2 | NO |
| `ACCOUNT_NAME` | VARCHAR2 | yes |
| `STATUS` | VARCHAR2 | yes |
| `CUSTOMER_TYPE` | VARCHAR2 | yes |
| `CUSTOMER_CLASS_CODE` | VARCHAR2 | yes |
| `ACCOUNT_ESTABLISHED_DATE` | DATE | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |
| `LAST_UPDATED_BY` | NUMBER | yes |
| `LAST_UPDATE_DATE` | DATE | yes |


### 2.4 The custom schema — `XX_QUALTERA`

This is where MSI stops looking like stock EBS. Note the spelling: **QUALTERA**, not
QUALTERRA.

**`XX_QUALTERA.XX_EVENT_LOG`** — **127,679 events — the single most valuable table in the estate.** Pre-built process-mining event log across 8 case types

| Column | Type | Null? |
|---|---|---|
| `EVENT_ID` | NUMBER | NO |
| `CASE_ID` | VARCHAR2 | NO |
| `CASE_TYPE` | VARCHAR2 | NO |
| `ACTIVITY` | VARCHAR2 | NO |
| `EVENT_TS` | TIMESTAMP(6) | NO |
| `RESOURCE_USER_ID` | NUMBER | yes |
| `RESOURCE_NAME` | VARCHAR2 | yes |
| `SOURCE_TABLE` | VARCHAR2 | yes |
| `SOURCE_PK` | VARCHAR2 | yes |
| `ATTR1_KEY` | VARCHAR2 | yes |
| `ATTR1_VAL` | VARCHAR2 | yes |
| `ATTR2_KEY` | VARCHAR2 | yes |
| `ATTR2_VAL` | VARCHAR2 | yes |
| `CREATED_TS` | TIMESTAMP(6) | yes |

**`XX_QUALTERA.XX_ZOBJECT_INVENTORY`** — 1,847 custom objects — the customisation-debt catalogue

| Column | Type | Null? |
|---|---|---|
| `ZOBJECT_ID` | NUMBER | NO |
| `OBJECT_TYPE` | VARCHAR2 | NO |
| `OBJECT_NAME` | VARCHAR2 | NO |
| `OWNER_SCHEMA` | VARCHAR2 | yes |
| `REFERENCES_DEPRECATED` | VARCHAR2 | yes |
| `REFERENCED_TABLE` | VARCHAR2 | yes |
| `CREATED_DATE` | DATE | yes |
| `LAST_MODIFIED` | DATE | yes |
| `STATUS` | VARCHAR2 | yes |

**`XX_QUALTERA.XX_FOUNDRY_QUALIFICATIONS`** — 48 rows = 8 suppliers × 6 process nodes, with qualification status

| Column | Type | Null? |
|---|---|---|
| `QUAL_ID` | NUMBER | NO |
| `SUPPLIER_ID` | NUMBER | NO |
| `PROCESS_NODE` | VARCHAR2 | NO |
| `QUAL_STATUS` | VARCHAR2 | yes |
| `QUAL_START_DATE` | DATE | yes |
| `QUAL_COMPLETE_DATE` | DATE | yes |
| `FIRST_QUAL_PO_HEADER_ID` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |

**`XX_QUALTERA.XX_DESIGN_REGISTRATIONS`** — 679 design wins registered to customers, with estimated annual revenue

| Column | Type | Null? |
|---|---|---|
| `REGISTRATION_ID` | NUMBER | NO |
| `CUSTOMER_PARTY_ID` | NUMBER | NO |
| `PROJECT_CODE` | VARCHAR2 | NO |
| `ITEM_FAMILY` | VARCHAR2 | yes |
| `PROCESS_NODE` | VARCHAR2 | yes |
| `REGISTRATION_DATE` | DATE | NO |
| `STATUS` | VARCHAR2 | yes |
| `ESTIMATED_ANNUAL_REVENUE_USD` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |

**`XX_QUALTERA.XX_EXPORT_CONTROL_CLASS`** — 641 items classified with ECCN / CCATS — export-control compliance

| Column | Type | Null? |
|---|---|---|
| `ECCN_RECORD_ID` | NUMBER | NO |
| `INVENTORY_ITEM_ID` | NUMBER | NO |
| `ECCN_CODE` | VARCHAR2 | yes |
| `CCATS_NUMBER` | VARCHAR2 | yes |
| `CLASSIFICATION_DATE` | DATE | yes |
| `CLASSIFIED_BY` | NUMBER | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |

**`XX_QUALTERA.XX_CMRT_ATTESTATIONS`** — 242 conflict-minerals attestations (3TG flags) by supplier and year

| Column | Type | Null? |
|---|---|---|
| `ATTESTATION_ID` | NUMBER | NO |
| `SUPPLIER_ID` | NUMBER | NO |
| `REPORTING_YEAR` | NUMBER | yes |
| `ATTESTATION_DATE` | DATE | yes |
| `STATUS` | VARCHAR2 | yes |
| `TANTALUM_FLAG` | VARCHAR2 | yes |
| `TIN_FLAG` | VARCHAR2 | yes |
| `TUNGSTEN_FLAG` | VARCHAR2 | yes |
| `GOLD_FLAG` | VARCHAR2 | yes |
| `CREATED_BY` | NUMBER | yes |
| `CREATION_DATE` | DATE | yes |


**Z-object inventory breakdown** (`XX_ZOBJECT_INVENTORY`, 1,847 rows):

| Object type | Active | Deprecated | Refactored | Unknown | Total |
|---|---:|---:|---:|---:|---:|
| Z_TABLE | 781 | 76 | 78 | 45 | 980 |
| PACKAGE | 423 | 50 | 38 | 29 | 540 |
| FORM_PERSONALIZATION | 164 | 14 | 12 | 10 | 200 |
| REPORT | 101 | 11 | 5 | 10 | 127 |
| **Total** | **1,469** | **151** | **133** | **94** | **1,847** |

This table is the anchor for any ERP-migration or clean-core deliverable: the interesting
cohort is *active* objects that reference deprecated EBS objects, because those are the ones
that must be rebuilt rather than retired.

---

## 3. Business processes — what actually happens at MSI

Three classic cycles plus a set of semiconductor-specific processes. The headline point:
**the accounting spine is excellent and the operational edges are weak.** Any deliverable
that treats MSI as uniformly good or uniformly bad is wrong.

### 3.1 The event log is the shortcut

`XX_QUALTERA.XX_EVENT_LOG` is a conformed, mined-ready log. Do not rebuild it from base
tables — 127,679 rows already carry `case_id`, `case_type`, `activity`, `event_ts`,
`resource_name`, plus `source_table`/`source_pk` for lineage back to EBS.

| `case_type` | Events | Cases | Activities | Meaning |
|---|---:|---:|---:|---|
| `PO` | 40,151 | 5,000 | 14 | procure-to-pay, PO-backed |
| `XLA` | 25,119 | 8,373 | 3 | subledger → GL |
| `SO` | 18,509 | 6,000 | 6 | order-to-cash, order side |
| `JE` | 17,787 | 8,850 | 3 | journal entry lifecycle |
| `AR` | 14,388 | 5,672 | 3 | billing → cash |
| `PR` | 7,805 | 4,000 | 2 | requisitioning |
| `INV` | 3,457 | 709 | 7 | **non-PO invoices** (the maverick-spend cohort) |
| `GLPER` | 463 | 28 | 3 | period-close program runs |

### 3.2 Procure-to-Pay (P2P)

**Designed path:** `PR_SUBMITTED → PR_APPROVED → PO_SUBMIT → PO_APPROVE → (PO_RELEASED) →
RECEIPT_RECEIVED → RECEIPT_DELIVERED → INVOICE_SUBMITTED → INVOICE_VALIDATED →
INVOICE_APPROVED → PAYMENT_ISSUED → PAYMENT_APPLIED`

**What the log shows instead:**

| Observation | Figure | Why it matters |
|---|---|---|
| POs never approved | 200 of 5,000 submitted (`PO_APPROVE` 4,800) | 4% abandoned at create |
| Rejection/rework loop | 586 `PO_REJECT` → 586 `PO_RESUBMIT` | a full rework cycle, ~12% of POs |
| Invoice holds | 387 invoices (12.9%) — Quantity 191, Price 125, Freight 34 | the **3-way match is leaking**; top quartile ≈3% |
| Non-PO spend | 709 of 3,000 invoices (23.6%) arrive with no `po_header_id` | off-contract / maverick spend |
| PO self-approval | **683 of 4,800 (14.2%)** submitter = approver | segregation-of-duties exposure |
| Early-pay discount capture | **$0** across 2,600 payments | median performers capture ~35% |
| Median pay time | 42.5 days (avg 43.6) | MSI pays *faster* than the ~70–80d peer band |

The last two combine into the most defensible P2P finding: MSI pays early **and** captures
no discount for it — that is pure foregone margin, not a policy trade-off.

### 3.3 Order-to-Cash (O2C)

**Path:** `ORDER_ENTERED → ORDER_BOOKED → SHIP_CONFIRMED → INVOICE_GENERATED →
CASH_RECEIPT → AR_PAYMENT_APPLIED`, with `ORDER_HOLD_PLACED/RELEASED` and
`ORDER_CANCELLED` as side paths.

| Observation | Figure |
|---|---|
| Orders entered → booked | 6,000 → 5,751 (249 cancelled, 4.2%) |
| Order holds | 452 placed, 385 released → **67 still held** |
| Billed revenue (all history) | $5,637.7M |
| Open AR | $853.0M |
| AR over 90 days past due | **$749.2M — 87.8% of open AR** |
| Days to collect (closed invoices) | **69.3 days** |

The aging profile is the story: almost nothing sits in the 0–90 bucket, because the dataset
deliberately seeds an aged pool. 69 days to collect against a ~45–47 day top-quartile
benchmark is the working-capital lever every MSI deliverable has sized.

### 3.4 Record-to-Report (R2R) — the genuine strength

| Metric | MSI | Benchmark | Verdict |
|---|---|---|---|
| Journal posting lag | ~3.5 days | Hackett world-class 4.5d | **better than world-class** |
| Manual / spreadsheet JEs | ~4–5% | APQC world-class ≤5–10% | good |
| Unbalanced journals | 0 across 28 periods | 0 | clean |
| JE reversals | 87 of 8,850 (~1%) | — | normal |
| Close program runs | 151 `PERIOD_CLOSE_RUN` over 28 periods (~5.4 attempts/period) | 1 | **fragmented** |

Read those last two rows together. The *accounting* is clean; the *close operation* is
retry-heavy and involves many operators per period. Dixon's threads disagree on how to score
this (one reports a 3.5-day close as best-in-class, another reports a 28-day close-cycle
duration with 5.4 retries) — they are measuring different things: **posting lag** vs
**period-close program elapsed window**. Pick one, define it in your output, and don't mix.

### 3.5 Control weaknesses worth knowing before you present

- **Self-approval**: PO 14.2%; AP self-approval reported at ~15.5% in May. Both far above
  any sensible SOX threshold.
- **Out-of-order control events**: cases where `INVOICE_APPROVED` precedes
  `INVOICE_VALIDATED`, and payments recorded before issuance. These are seeded control
  violations — find them with a self-join on the event log ordered by `event_ts`.
- **Resource concentration**: `PAYMENT_ISSUED` / `PAYMENT_APPLIED` show **1** distinct
  resource; `RECEIPT_*` and `PO_APPROVE` show 4–5. A handful of user IDs carry the whole
  transaction volume — realistic for batch/interface users, but it means resource-level
  workload analysis needs `XX_STAGE_USER_MAP` and `FND_USER` (80 users) for context.

### 3.6 Semiconductor-specific processes

These have no stock-EBS equivalent and are what make MSI feel authentic:

1. **Foundry qualification** — `XX_FOUNDRY_QUALIFICATIONS`: each supplier × process node
   carries a status and start/complete dates, linked to the first qualification PO. The
   leading-edge risk is visible here: only a small number of suppliers reach
   mass-production status at 3nm.
2. **Design registration** — `XX_DESIGN_REGISTRATIONS`: 679 design wins tied to customer
   parties, item family, process node, and estimated annual revenue. This is the demand
   pipeline *ahead* of any AR transaction.
3. **Export control** — `XX_EXPORT_CONTROL_CLASS`: 641 items with ECCN/CCATS codes.
4. **Conflict minerals** — `XX_CMRT_ATTESTATIONS`: 242 supplier-year attestations with
   tantalum/tin/tungsten/gold flags.
5. **Revenue reserve** — `XX_REVENUE_RESERVE_LEDGER`: 28 monthly rows; distributor
   price-protection and stock-rotation reserves, standard in chip distribution.

---

## 4. Data and connectivity — read this before writing SQL

### 4.0 Connection facts

| Item | Value |
|---|---|
| Platform | Oracle Autonomous Data Warehouse (Oracle dialect) |
| Access | single read-write connector named **Oracle EBS**; treat as read-only unless a build is explicitly scoped |
| Object naming | schema-qualified, e.g. `ap.ap_invoices_all`; unquoted identifiers fold to UPPERCASE |
| Row limiting | `FETCH FIRST n ROWS ONLY` or `ROWNUM <= n` — **no `LIMIT`** |
| Median | `MEDIAN(x)` works; `PERCENTILE_CONT` for other percentiles |
| Date maths | `date2 - date1` yields days as a NUMBER; `SYSDATE` is current timestamp |
| Reserved words | `rows`, `size`, `level`, `date` fail as aliases — Dixon lost a query to `AS rows` |
| Empty tables | `CE_STATEMENT_HEADERS/LINES`, `CE_BANK_ACCT_USES_ALL`, `MTL_SYSTEM_ITEMS_TL`, `FND_FLEX_VALUES`, `FND_RESPONSIBILITY_TL`, `AP_SUPPLIER_CONTACTS`, `XX_DQ_PROFILE`, `PER_ADDRESSES` — do not build a bank-reconciliation or flexfield feature on these |

### 4.1 `CREATION_DATE` is a load artefact — never use it as a business date

Every row was generated in a build run, so `creation_date` clusters on the load date
(large blocks on 2026-05-03). It tells you nothing about when business events happened.

| Instead of | Use |
|---|---|
| `gl_je_headers.creation_date` | `default_effective_date`, `period_name` |
| `ap_invoices_all.creation_date` | `invoice_date`, `gl_date` |
| `po_headers_all.creation_date` | `creation_date` is fine only for PO *entry* timing; prefer `approved_date` for approval |
| anything process-timing related | `XX_EVENT_LOG.event_ts` — the only trustworthy timeline |

### 4.2 There is exactly one operating unit

Despite four ledgers and four subsidiaries, **`ORG_ID = 204` on 100% of rows** in
`AP_INVOICES_ALL`, `PO_HEADERS_ALL`, `OE_ORDER_HEADERS_ALL`, and `RA_CUSTOMER_TRX_ALL`.
So:

- Do not build an operating-unit filter or a multi-OU comparison — it will return one bar.
- Entity analysis must come from the **GL side** (`ledger_id` 1–4) or from
  `HR_ALL_ORGANIZATION_UNITS`, not from transaction `org_id`.
- Sub-ledger volume is effectively **all in the US primary ledger**: 8,794 of 8,850 journals.
  Singapore has 7, Ireland 21, India 28. Any "global entity comparison" built on journal
  counts is a comparison of one entity against rounding error. Say so rather than charting it.

### 4.3 The join map that matters

```
PR → PO:      po_requisition_lines_all.requisition_header_id → po_requisition_headers_all
PO chain:     po_headers_all.po_header_id → po_lines_all → po_line_locations_all
                                                        → po_distributions_all
Receipt:      rcv_shipment_headers.shipment_header_id → rcv_shipment_lines → rcv_transactions
3-way match:  ap_invoices_all.po_header_id  (NULL 23.6% of the time — that IS the finding)
AP payment:   ap_invoices_all.invoice_id → ap_invoice_payments_all.invoice_id
                                        → ap_checks_all.check_id        (never join checks direct)
Supplier:     ap_invoices_all.vendor_id → ap_suppliers.vendor_id → ap_supplier_sites_all
O2C:          oe_order_headers_all.header_id → oe_order_lines_all
                → wsh_delivery_details / wsh_new_deliveries
                → ra_customer_trx_all.customer_trx_id → ra_customer_trx_lines_all
AR cash:      ar_payment_schedules_all.payment_schedule_id
                ← ar_receivable_applications_all.applied_payment_schedule_id
Customer name: ra_customer_trx_all.bill_to_customer_id → hz_cust_accounts.cust_account_id
                → hz_parties.party_id  ➜  party_name      (two hops — not one)
GL:           gl_je_headers.je_header_id → gl_je_lines → gl_code_combinations.code_combination_id
Subledger:    xla_ae_headers.ae_header_id → xla_ae_lines → xla_distribution_links
Event log:    xx_event_log.source_table + source_pk → back to any EBS row
```

### 4.4 The trap that cost a whole build phase

`AR_RECEIVABLE_APPLICATIONS_ALL` links **only to already-CLOSED payment schedules**
(4,358 of 4,358), and `AP_INVOICE_PAYMENTS_ALL` links **only to already-PAID invoices**.
The open AR/AP rows have **no payment activity at all** — they are deliberately unpaid, not
mis-flagged.

Practical consequences:

- A query of the form "open schedules that have applied receipts" returns **zero rows**. That
  is correct behaviour, not a broken join.
- You cannot compute realised DSO/DPO from the open population. Compute it from the **paid
  population** (weighted-paid method) and label it as such.
- Balance-method DSO and paid-method DSO differ enormously on this dataset (roughly 180d vs
  ~54–69d depending on window). State which you used, every time.

A May 2026 remediation ("Phase 10") was halted for exactly this reason: the fix assumed
sticky flags, the data had no payments to re-flag, and the correct fix was to *generate*
receipts — a data build, not an UPDATE.

### 4.5 Data-quality state has moved — May findings are stale

Verified today against the May assessment:

| Issue reported in May 2026 | State on 2026-09-17 |
|---|---|
| `AP_SUPPLIERS.segment1` 100% NULL (broke every spend cube) | **fixed** — 0 of 155 NULL |
| `MTL_SYSTEM_ITEMS_B.list_price_per_unit` 100% NULL (inventory unvaluable) | **fixed** — 0 of 1,000 NULL |
| `PO_HEADERS_ALL.approved_date` ~200 NULL | now **121** NULL |
| `OE_ORDER_HEADERS_ALL.booked_date` 249 NULL | unchanged — 249 (these are the cancelled orders; expected) |
| `XLA_AE_LINES` empty | was already wrong in May — 43,693 lines exist |

**Lesson to carry:** re-verify every DQ claim before you quote it. This estate is actively
rebuilt in phases, and the `XX_QUALTERA.XX_PHASE10_*_SNAPSHOT` tables plus `XX_BUILD_LOG`
(22 rows) are the audit trail of those builds. Check `XX_BUILD_LOG` at the start of a session
to see what moved.

### 4.6 Metric recipes that are known-good

```sql
-- Days to collect, paid population only (the defensible DSO)
SELECT ROUND(AVG(ps.gl_date - trx.trx_date), 1) AS days_to_collect
FROM   ar.ar_payment_schedules_all ps
JOIN   ar.ra_customer_trx_all      trx ON trx.customer_trx_id = ps.customer_trx_id
WHERE  ps.status = 'CL';                      -- → 69.3 days

-- DPO, realised payment behaviour
SELECT ROUND(MEDIAN(c.check_date - i.invoice_date), 1) AS dpo_median
FROM   ap.ap_invoice_payments_all p
JOIN   ap.ap_checks_all           c ON c.check_id   = p.check_id
JOIN   ap.ap_invoices_all         i ON i.invoice_id = p.invoice_id;   -- → 42.5 days

-- Revenue by customer (note the two-hop customer join)
SELECT p.party_name, SUM(l.extended_amount) AS revenue
FROM   ar.ra_customer_trx_lines_all l
JOIN   ar.ra_customer_trx_all       t ON t.customer_trx_id   = l.customer_trx_id
JOIN   hz.hz_cust_accounts          c ON c.cust_account_id   = t.bill_to_customer_id
JOIN   hz.hz_parties                p ON p.party_id          = c.party_id
GROUP  BY p.party_name
ORDER  BY revenue DESC;

-- Segregation of duties: PO submitted and approved by the same person
WITH po_sa AS (
  SELECT case_id,
         MAX(CASE WHEN activity = 'PO_SUBMIT'  THEN resource_name END) AS submitter,
         MAX(CASE WHEN activity = 'PO_APPROVE' THEN resource_name END) AS approver
  FROM   xx_qualtera.xx_event_log
  WHERE  case_type = 'PO'
  GROUP  BY case_id)
SELECT COUNT(*) AS evaluated,
       SUM(CASE WHEN submitter = approver THEN 1 ELSE 0 END) AS self_approved
FROM   po_sa
WHERE  submitter IS NOT NULL AND approver IS NOT NULL;   -- → 683 of 4,800 (14.2%)

-- Process variants (feed straight into pm4py)
SELECT variant, COUNT(*) AS cases
FROM ( SELECT case_id,
              LISTAGG(activity, ' → ') WITHIN GROUP (ORDER BY event_ts) AS variant
       FROM   xx_qualtera.xx_event_log
       WHERE  case_type = 'PO'
       GROUP  BY case_id )
GROUP BY variant
ORDER BY cases DESC
FETCH FIRST 20 ROWS ONLY;
```

### 4.7 `FIN_CLOSE` is a different dataset — do not join it to EBS

19 tables, star-schema shaped (`DIM_ENTITY`, `DIM_ACCOUNT`, `GL_BALANCES`, `PL_ACTUALS`,
`RECON_ITEMS`, `PROPOSED_JOURNAL_ENTRIES`…). Its `DIM_ENTITY` values are *Parent Co (US)*,
*International R&D Sub*, *EMEA Sub*, *APAC Sub* — **not** the MSI legal entities. It belongs
to a separate financial-close demo. Keys do not reconcile to EBS. Keep the two apart.

### 4.8 Reporting discipline for this estate

1. **Always print the window.** The same metric swings by a factor of 2–3 between "all
   history", "TTM", and "last 28 days". Most of the apparent contradictions across the May
   threads are window differences, not errors.
2. **Name the method.** Balance-method vs paid-method DSO/DPO. Full-history vs named-vendor
   concentration.
3. **Re-derive, don't quote.** Prior figures (DSO 45 / 68.6 / 136; TaiwanFab 35% / 49% / 54%)
   were all correct under their own definitions and windows. Re-run before you publish.
4. **Peer benchmarks are external.** APQC and Hackett thresholds are not in this database and
   APQC's own content is members-only. Cite them as public/canonical figures, not as
   something the warehouse told you.
5. **Lead with the asymmetry.** Clean accounting spine, weak operational edges, two extreme
   concentrations, and a large customisation estate. That framing has survived six threads.

---

## 5. Thirty-second orientation for a new session

```sql
SELECT * FROM xx_qualtera.xx_build_log ORDER BY 1 DESC FETCH FIRST 10 ROWS ONLY;   -- what changed
SELECT case_type, COUNT(*), MIN(event_ts), MAX(event_ts)
  FROM xx_qualtera.xx_event_log GROUP BY case_type;                                -- process coverage
SELECT name, currency_code FROM gl.gl_ledgers;                                     -- entity structure
SELECT MIN(period_name), MAX(period_name), COUNT(*) FROM gl.gl_periods;            -- time window
```

**Provenance.** Grounded in the live Oracle EBS connection on 2026-09-17; business framing
and prior findings drawn from the six MSI threads by david@textql.com (3–18 May 2026):
*Analyze MSI Financial & Process Performance*, *Assess MSI Oracle EBS Data Quality*,
*Execute MSI AR/AP Status Reflagging*, *Fix MSI demo data for production realism*,
*MSI EBS data quality and process mining assessment*, *Design Quad A+ MSI deliverables*.
Where those threads disagree with the live database, the live database wins and the
divergence is flagged above.
