# Security lens: 2026-11-16-security

| Kind | Found | Confirmed |
| :- | -: | -: |
| breach | 8 | 5 |
| unproven | 7 | 7 |
| all | 15 | 12 |

Suppressed: 11. Tracked in the backlog: 0.

## Ratchet (0)


## Fix (1)

| Location | Requirement | Claim | Proposal |
| :- | :- | :- | :- |
| `tests/e2e/test_site_settings.py:test_the_seeds_switches_are_fields_the_guide_names` | REQ-002-PRS-NF013 | The guide's document-sharing switch keeps drafts-only, because a share with submit gives the agent user's key submit on that document past its role. No test checks that the switch closes this: the new tests only check that `disable_document_sharing` exists as a field and that the seed sets it to 1. | Add an e2e test to test_site_settings.py or test_ceiling.py. With the seed's switches set, a non-Administrator desk user with share rights on Sales Invoice calls frappe.share.add for one of the agent user's drafts with submit=1, and it is refused with PermissionError. After that, the agent's key still gets a PermissionError from frappe.client.submit on that draft. Also add a test that the seed holds no DocShare for the agent user (site.get_list('DocShare', {'user': AGENT}) == \[]). Then add a line to the guide's sharing bullet: turning the switch off doesn't revoke shares that already exist (remove any DocShare for the agent user), and Administrator can still share. |

## Proposal (0)

