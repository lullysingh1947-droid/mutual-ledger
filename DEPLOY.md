# Mutual Ledger — public HTTPS deployment (pilot only)

This repository includes a Render Blueprint (`render.yaml`) that runs one FastAPI worker and stores the SQLite database on a paid, persistent disk. Render supplies an HTTPS `*.onrender.com` address after deployment. **No live website has been deployed by this package alone.**

## Publish

1. Sign into GitHub and create a **private** repository. Upload `app.py`, `requirements.txt`, `render.yaml`, `static/index.html`, and `.gitignore` from this folder (do not upload any `.db` file).
2. Sign into Render and select **New → Blueprint**. Connect the GitHub repository and approve the proposed `mutual-ledger` web service.
3. Render provisions the service and a **paid persistent disk**. On completion, open the HTTPS URL shown in the Render dashboard.
4. Create two **test** accounts using different email addresses. Create a supplier ledger, accept an invitation, confirm opening balance, approve an invoice, and approve a partial delivery. Repeat with an accountant ledger.
5. Configure and test offsite database backups before entering any real financial records.

## Operational warnings

- **Pilot only — do not use with real business financial data yet.** Login brute-force protection/rate limiting, email address verification, MFA, password recovery, forced logout and device management, external security review, backup restoration drills, proper migration management, transactional concurrency controls, automated email invitations, and a complete accounting audit/security review are still required.
- Session bearer tokens are kept in the browser's sessionStorage and expire after seven days on the server, which is not a final production-grade session strategy. No credit-card information should be stored.
- **Anyone can create an account**, although only invited parties can see existing ledgers. Account owners should verify invited counterparties independently.
- The starting balance and financial entries must be independently reconciled against official records; this pilot does not replace an accountant or double-entry bookkeeping.
- The SQLite database MUST live on persistent storage at `LEDGER_DB=/var/data/ledger.db`. A free Render instance without a disk will lose records on redeploy. Use exactly one worker/instance on this configuration.
- Do not post invite links publicly. The app does not send invitation emails: copy the invitation link privately.
- For a production rollout, move to PostgreSQL with robust database transactions, backups, audit integrity, and an independent security assessment before onboarding vendors.
