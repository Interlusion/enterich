# Tests lens: 2026-11-14-tests-2

| Kind | Found | Confirmed |
| :- | -: | -: |
| dod-gap | 0 | 0 |
| mutant-gap | 4 | 3 |
| weak-test | 0 | 0 |
| all | 4 | 3 |

Suppressed: 0. Tracked in the backlog: 0.

## Ratchet (0)


## Fix (3)

| Location | Requirement | Claim | Proposal |
| :- | :- | :- | :- |
| `src/enterich/tools/procure_to_pay.py:create_draft_purchase_invoice` | REQ-005-PRS-F006 | No test checks that a purchase invoice create's duplicate refusal and warning say which of the two matches of REQ-005-PRS-F006 fired (bill number against a draft or submitted purchase invoice, or supplier, posting date and items against a draft); they check only the matching document's name. | In tests/integration/test_procure_to_pay_drafts.py assert the full text for both branches, refused and allowed: with bill_no R-4711, the error equals "allow_duplicate: a purchase invoice with the same supplier and bill_no exists (ACC-PINV-2026-00001). Check it first; ..." and the warning with allow_duplicate equals "Possible duplicate of ACC-PINV-2026-00001: a purchase invoice with the same supplier and bill_no."; with items=DRAFT_ITEMS and no bill_no, the same with "a draft with the same supplier, posting date and items". |
| `src/enterich/tools/returns.py:create` | REQ-005-PRS-F009 | No test checks that a return create's duplicate refusal or warning says what matched and what the match is (a draft return against the same invoice, or a purchase invoice with the same supplier and bill_no). | In tests/integration/test_return_drafts.py assert the whole text: the sales and purchase refusals equal "allow_duplicate: a draft return with the same invoice (return_against) exists (<draft name>). Check it first; ...", the allowed create's warning equals "Possible duplicate of <draft name>: a draft return with the same invoice (return_against).", and the debit note with bill_no CN-77 is refused with "a purchase invoice with the same supplier and bill_no exists (ACC-PINV-2026-00009)". |
| `src/enterich/tools/procure_to_pay.py:update_draft_purchase_invoice` | REQ-005-PRS-F006 | No test checks that the warning of an update giving an already recorded bill_no (purchase invoice and purchase return) says it is a purchase invoice with the same supplier and bill_no; only the other document's name is asserted. | In both tests assert the warning in full: warning == "Possible duplicate of ACC-PINV-2026-00001: a purchase invoice with the same supplier and bill_no." for update_draft_purchase_invoice, and the same with ACC-PINV-2026-00009 for update_draft_purchase_return. |

## Proposal (0)

