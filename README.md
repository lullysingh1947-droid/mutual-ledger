# Mutual Ledger — private pilot v0.1

A runnable **two-business, shared-ledger pilot**: supplier ledgers support multi-line invoices and quantity-based partial deliveries; accountant ledgers support credits and debits only. All opening balances, transactions and delivery receipts must be approved by both counterparties. Pending changes do not affect the agreed balance or confirmed quantities.

## Run locally

Requires Python 3.10+. From this folder:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ in your browser.

## Test together

1. Register as Business A (use a real-looking email; mail is not sent).
2. Create a supplier or accountant ledger, specify Business B's exact email, and copy the invitation URL.
3. Use a separate browser/private window to register as Business B. Visit the invitation URL and accept it.
4. As B, confirm the proposed opening balance. A or B can then create credits/debits (or supplier invoices). The other account must approve each entry.
5. In a supplier ledger, create an invoice with one or more item lines, approve the invoice from the other account, then propose deliveries and mutually approve them. Incomplete lines remain highlighted amber.
6. Test that an initiator cannot approve their own transaction, and that proposed or unconfirmed amounts/quantities do not change agreed totals.

## Accounting conventions

- Amounts are stored in integer currency minor units. UI uses currency formatting.
- **Debit increases** the balance; **credit reduces** it. Supplier invoices count as debits (increase amount due to supplier). Positive opening balance means amount owed to supplier. Negative balances are allowed.
- **Approved invoice value and fulfilled merchandise value are separate.** The difference is shown as unfulfilled value. For multi-line invoices, fulfilled value is prorated by confirmed pieces for each line. This convention assumes equal unit values within a line.
- Unapproved deliveries reserve quantities to avoid over-allocation, but do not increase confirmed quantities. Those can get stuck if the recipient never confirms; a cancel/dispute workflow is planned.
- Opening balance is proposed/approved by the creator and must be explicitly confirmed by the invited party.

## Security and deployment status

**This is a private local pilot, not a production or Internet-ready financial system.**

Already included: scrypt password hashes, opaque session tokens, per-ledger permissions, strict invited-email matching, separate initiator/other approval, SQLite transaction integrity, server-side quantity limits, audit trail. Tokens are stored in browser sessionStorage, and the application uses HTTPS only if deployed behind a separately configured TLS proxy.

**Before using real commercial data online:** add TLS, secure HttpOnly session cookies and CSRF protection, email verification and actual mail invites, production identity/authentication and MFA, rate limits, input normalization, proper admin permissions, PostgreSQL with migrations, backups, monitoring, approval notifications, explicit reject/cancel/dispute and correction workflows, non-editable exportable audit log, and a formal ledger policy reviewed by your accountant. Consider invoice tax treatment, multi-currency FX rules, and separate purchase-order vs invoicing semantics. A private deployment and security review are required.

## Pilot limitations

- Invitations are **copyable links**, not automatically emailed.
- No permanent admin overview, PDF/Excel export, document uploads, notifications or mobile store apps yet.
- No rejection/cancel/reversal UI yet (avoid entering real financial transactions).
- Ledger permissions are two users per ledger in this pilot; production should allow granular business teams.
- Database data lives in `ledger.db` beside the server. Do not commit it or share it.
