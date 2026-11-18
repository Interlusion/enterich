# ITEM-011: Amounts at the company currency's precision

| Meta | Value |
| :- | :- |
| **Status** | IDEA |
| **Type** | improvement |
| **Origin** | Contract review of the specs, 2026-11-18: the 2-decimal limit on journal entry debits and credits |
| **Created** | 2026-11-18 |
| **Author** | loxy (drafted with Claude) |

## Summary

Journal entry debits and credits (REQ-001's common inputs) and payment amounts (REQ-007) take at most 2 decimal places, whatever the company's currency. A company in a currency of 3 places, such as KWD, BHD or OMR, can't draft an amount in fils, and REQ-006 and REQ-007 rule such amounts out of scope. Instead, Enterich could take as many decimal places as the company currency has, and refuse more.

## Context / Motivation

- ERPNext rounds a journal entry's rows, and a payment's totals, to the currency's precision. Places beyond it leave rows that balance as given unbalanced once saved, or totals that differ from the allocations. The fixed limit of 2 avoids this for currencies of 2 places or more.
- For a currency without decimal places, such as JPY, 2 places are still too many. REQ-006-PRS-F008's warning catches the journal entries ERPNext saves unbalanced, but the agent learns of it only after the save.
- The limit at the currency's precision would remove both: amounts in fils where a currency has them, and no rounding apart where it has none. The rounding warning, and the note in REQ-006-PRS-F007 that a repeated create in such a currency isn't matched, could then go.

## Open Questions

- Where does Enterich read the precision? The company's `default_currency`, then the Currency's `smallest_currency_fraction_value` or number format, or System Settings' `currency_precision` where a site sets it. That means one more ERPNext call at each write, or at start, with the right it needs (Company, Currency: read) listed in the area specs.
- Does an input schema that depends on the site still meet REQ-001's fixed input schemas? The schema would keep its bounds, and the precision check would be a refusal naming the input, as other checks against ERPNext's data are.
- Raising the limit from 2 to 3 places for a 3-place currency loosens an input, which ADR-004 counts as a minor change. Lowering it to 0 for JPY tightens one, which is breaking.

## Notes

- Today's limit: `Cents` in `src/enterich/shapes.py`, used by `Amount` (journal entries) and `Money` (payment entries).
