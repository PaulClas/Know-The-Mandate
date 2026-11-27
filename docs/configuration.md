# Configuration

KYM is configured only through environment variables (see [.env.example](../.env.example)). Defaults are chosen so `make demo` works without any file. All values shown are demo values.

| Variable | Default | Purpose |
|---|---|---|
| `KYM_ENV` | `demo` | `demo` enables no-password sessions, `POST /api/demo/reset` and the red-team endpoints. **Any other value disables them (fail closed).** KYM has no production mode; see the [security review](security/security-review.md) |
| `KYM_DATA_DIR` | `.kym-data` | SQLite file, signing keys (`keys/`), exported ledger checkpoints, demo agent credentials |
| `KYM_DATABASE_URL` | `sqlite:///$KYM_DATA_DIR/kym.db` | SQLAlchemy URL. PostgreSQL: `postgresql+psycopg://user:pass@host:5432/kym` (needs the `postgres` extra: `pip install -e ".[postgres]"`; `make install` includes it) |
| `KYM_ISSUER` | `https://bank.example` | OAuth issuer identifier placed in tokens and metadata |
| `KYM_PUBLIC_BASE_URL` | empty | Set when behind a proxy so the DPoP `htu` claim is validated against the public URL |
| `KYM_DEMO_SESSION_SECRET` | random per install | Signs demo sessions. Unset means a random secret is generated into `KYM_DATA_DIR/keys/session-secret` |
| `KYM_RATE_LIMIT_PER_MIN` | `1200` | Per-client request budget |
| `KYM_FAILED_AUTH_PER_MIN` | `20` | Failed OAuth client authentications per minute before 429 |
| `KYM_REJECT_EVENTS_PER_MIN` | `60` | Cap on `TOKEN_REJECTED` evidence events written per minute (a burst is counted, not written, so an attacker cannot flood the ledger) |
| `KYM_POSTGRES_PASSWORD` | `kym-demo-only` | Compose only; password of the bundled PostgreSQL |
| `KYM_API_URL` | `http://localhost:8000` | Web app only: where the Next.js server proxies `/api`, `/bank`, `/oauth` |

## Bank policy

Bank-wide limits (maximum single payment, maximum mandate validity, forbidden agent actions, risk thresholds) are in [policies/bank-policy-1.0.0.json](../policies/bank-policy-1.0.0.json) (loaded by `config.policy_config()`), versioned as `bank-policy-1.0.0`, and every decision records the policy version it used.

## Secrets

Never commit real credentials. `.kym-data/` and `.env` are git-ignored. Demo keys are generated locally on first start and are not secret-grade: they exist so the sandbox can sign things.
