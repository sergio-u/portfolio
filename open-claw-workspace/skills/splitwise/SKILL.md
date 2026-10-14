---
name: "splitwise"
description: "Splitwise safety, FX lessons, frequent IDs"
---

# Splitwise

Interact with Splitwise using the Python SDK in a local uv venv.

## When to use

Use this skill for Splitwise balances, expenses, groups, direct transfers, settlements, and Splitwise account cleanup.

## Execution

Use the authenticated REPL helper in the skill directory for all SDK operations. The helper initializes `s` as the Splitwise client and imports the common SDK classes.

Keep outputs readable: format IDs, names, balances, expense dates, payment flags, deleted timestamps, and paid/owed shares explicitly instead of dumping raw SDK objects.

## API Reference

See `references/api.md` for SDK methods and common patterns.

## Local defaults and cached IDs

Default currency for new expenses/transfers: USD, unless the user specifies a currency or the existing context clearly uses another currency.

Frequent IDs (cache your own user, friends, and groups here):

- Me: `<user-id>`
- Example group: `<group-id>`

Do not keep completed one-off trip groups in the cache. Discover old trip groups dynamically when needed.

## Safety rules

- Confirm before writes such as creating, deleting, editing, or settling expenses unless the user just explicitly asked for that exact write.
- Before creating expenses, verify IDs by listing friends/group members or by using the cached IDs above with a quick sanity check.
- For multi-entry settlements/cleanup, capture a before snapshot of relevant friend balances, group debts, expense IDs, and deleted status.
- Track new entry IDs during multi-entry writes. If verification fails, delete only the newly-created entries in reverse order.
- After writes, verify the smallest meaningful state: relevant friend balances, group original debts, and active/deleted state for changed expenses.

## Important Splitwise semantics

Friend aggregate balances and group debts are different views:

- Friend balances show the aggregate relationship across visible Splitwise contexts/currencies.
- Group original debts show the simplified debt graph inside one group.
- A user-described balance may refer to the aggregate view, not a specific group-pair debt.

When reconciling confusing ledgers:

1. Inspect current friend aggregate balances for the relevant friend.
2. Inspect group original debts only if the user says the balance is in a group.
3. Inspect recent active and deleted expenses around the suspected time window.
4. Reconstruct from active entries before proposing cleanup.

Deleted expenses can still be fetched by ID. Always check deleted status when auditing or reconstructing.

Payment/settlement entries are direction-sensitive. For payment entries, inspect the resulting repayment direction before trusting the effect.

## Cross-currency lessons

Splitwise does not auto-convert or net currencies. This applies inside groups and to direct/non-group friendship entries.

Avoid trying to cancel one currency with another by creating paired cross-currency payments. In testing, that increased both currency balances instead of producing true netting.

For cross-currency settlement:

1. Keep each source currency balance intact until the user agrees on a rate.
2. Compute conversion externally with an explicit rate and date.
3. Decide which ledger should hold the final single-currency remainder.
4. Prefer one clearly-noted carryover/adjustment in the settlement currency, or one same-currency payment after the real-world transfer.
5. Include a note with original amount, rate, converted amount, and date/agreement.

If balances exist in multiple places, do not collapse based only on group debts. Reconcile against friend aggregate balances and recent expense history first, because a direct payment may already have changed the aggregate.

## Historical FX rates

If the user asks about historical rates, check a live/historical source before answering. Report whether using the historical rate materially changes the settlement.

## Audit/reconstruction recipe

Use this when a cleanup may have partially applied or the user is unsure of the original ledger.

1. Identify target user/group IDs.
2. Print current friend balances.
3. Print relevant group pair debts.
4. Inspect known expense IDs and recent expenses around the time window, including deleted status.
5. Separate active entries from deleted test entries.
6. Reconstruct the clean state from active entries only.
7. Present proposed cleanup and ask before further writes.

## Authentication and troubleshooting

Credentials are loaded from the skill `.env` file. If authentication fails, verify the `.env` values and whether the Splitwise API credentials are still valid.

If SDK methods return empty or `None`, check authentication and permissions first.

If the SDK package is missing, reinstall the skill venv dependencies before retrying.

Respect Splitwise API rate limits during bulk work.
