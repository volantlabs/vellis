# Minimal Example

```md
---
id: component.billing.invoice_preview
type: Component
status: draft
owner: billing
code:
  roots:
    - src/app/components/invoice_preview
---

# Invoice Preview

## Purpose

Produce a read-only preview of expected invoice charges before invoice finalization.

## Responsibilities

- Aggregate billable usage for an account and billing period.
- Apply the current tax policy.
- Produce line items, subtotal, tax, and total.
- Expose preview behavior through the billing API.

## Non-responsibilities

- Does not create final invoice records.
- Does not capture payment.
- Does not mutate account balance.
- Does not define tax policy.
- Does not own account identity or account lifecycle.

## Provided contracts

### `InvoicePreviewService.preview`

Kind:

- function

Inputs:

- `InvoicePreviewRequest`

Outputs:

- `InvoicePreviewResponse`

Errors:

- `AccountNotFound`
- `BillingPeriodInvalid`
- `TaxPolicyUnavailable`

Semantics:

- Returns a preview only.
- Calling this operation must not create durable financial state.
- The response must be safe to discard.

## Required contracts

May consume:

- `component.billing.account_reader`
- `component.billing.usage_reader`
- `component.billing.tax_policy`

Must not consume:

- `component.billing.invoice_finalizer`
- `component.payments.capture`
- `component.ledger.account_balance_writer`

## Owned state

- None. This component is read-only and derives its behavior from other components.

## Invariants

### `read_only`

Preview must not create invoices, capture payment, or mutate account balance.

### `current_tax_policy`

Preview must use the current active tax policy.

## Related components

- Part of `component.billing`.

## Verification

Required checks:

- contract test for the preview operation against the public boundary
- integration test proving the preview is served through the billing API
- architecture check proving no forbidden dependency is imported
- side-effect check proving no invoice, account-balance, or payment write occurs

Required evidence:

- API contract test
- golden input/output fixture
- no-write side-effect test

## Change rules

Agents may:

- Modify implementation inside `src/app/components/invoice_preview`.
- Add private helper modules inside the component.
- Add or update tests that validate the public contract.
- Refactor internals while preserving contracts and invariants.

Agents may not:

- Change `InvoicePreviewRequest` or `InvoicePreviewResponse` without explicit approval.
- Add new cross-component dependencies without approval.
- Touch invoice finalization, payment capture, or account balance code.
- Move tax policy logic into this component.
- Introduce shared utilities unless there are existing approved callers.

## Open questions

- Should preview results be cached, or must they always be recomputed?
- Is tax policy failure a hard error or should the response include an unavailable-tax marker?
```
