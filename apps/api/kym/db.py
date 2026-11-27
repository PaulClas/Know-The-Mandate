from __future__ import annotations

import threading
from contextlib import contextmanager

from sqlalchemy import JSON, BigInteger, Boolean, Integer, String, Text, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from . import config

WRITE_LOCK = threading.RLock()
_local = threading.local()
_engine = None
_Session = None


class Base(DeclarativeBase):
    pass


def j(**kw):
    return mapped_column(JSON, **kw)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String)  # individual | business
    name: Mapped[str] = mapped_column(String)
    jurisdiction: Mapped[str] = mapped_column(String)
    kyc_status: Mapped[str] = mapped_column(String)  # VERIFIED | PENDING | FAILED
    kyc_date: Mapped[str | None] = mapped_column(String, nullable=True)
    kyc_evidence_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_class: Mapped[str] = mapped_column(String, default="LOW")
    restrictions: Mapped[list] = j(default=list)
    cnl_ref: Mapped[str] = mapped_column(String, default="")
    preferred_language: Mapped[str] = mapped_column(String, default="en")


class Representative(Base):
    __tablename__ = "representatives"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(String)
    person_id: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    can_sign: Mapped[bool] = mapped_column(Boolean, default=True)
    account_ids: Mapped[list] = j(default=list)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True)  # None => bank-internal GL account
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String)
    balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String, default="OPEN")  # OPEN | FROZEN | CLOSED
    restrictions: Mapped[list] = j(default=list)
    cnl_ref: Mapped[str] = mapped_column(String, default="")


class Payee(Base):
    __tablename__ = "payees"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)  # beneficiary | merchant
    name: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    cnl_ref: Mapped[str] = mapped_column(String, default="")
    watchlist: Mapped[bool] = mapped_column(Boolean, default=False)  # synthetic sanctions list


class HistoryEntry(Base):
    __tablename__ = "history"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True)
    posted_at: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    payee_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    cnl_ref: Mapped[str] = mapped_column(String, default="")
    display_name: Mapped[str] = mapped_column(String)
    declared: Mapped[dict] = j()  # agent-declared metadata (NOT verified facts)
    verified: Mapped[dict] = j(default=dict)  # facts established by the bank
    client_id: Mapped[str] = mapped_column(String, unique=True)
    client_secret_hash: Mapped[str] = mapped_column(String, default="")
    public_key_jwk: Mapped[dict] = j(default=dict)
    status: Mapped[str] = mapped_column(String, default="PENDING_VERIFICATION")
    registered_at: Mapped[str] = mapped_column(String)
    attestation: Mapped[dict] = j(default=dict)
    security_posture: Mapped[dict] = j(default=dict)
    incidents: Mapped[list] = j(default=list)
    stats: Mapped[dict] = j(default=dict)


class MandateRow(Base):
    __tablename__ = "mandates"
    mandate_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[dict] = j()
    digest: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    created_by: Mapped[str] = mapped_column(String)
    principal_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    parent_mandate_id: Mapped[str | None] = mapped_column(String, nullable=True)
    compile_artifacts: Mapped[dict] = j(default=dict)


class MandateState(Base):
    """Lifecycle status is authoritative mutable state, separate from signed immutable mandate content."""

    __tablename__ = "mandate_states"
    mandate_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String, default="")
    history: Mapped[list] = j(default=list)
    validation: Mapped[dict] = j(default=dict)


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    mandate_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String)
    customer_id: Mapped[str] = mapped_column(String)
    receipt: Mapped[dict] = j()
    signature: Mapped[str] = mapped_column(String)
    key_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class DelegationRow(Base):
    __tablename__ = "delegations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    parent_id: Mapped[str] = mapped_column(String, index=True)
    parent_version: Mapped[int] = mapped_column(Integer)
    child_id: Mapped[str] = mapped_column(String, index=True)
    child_version: Mapped[int] = mapped_column(Integer)
    validated_at: Mapped[str] = mapped_column(String)
    validated_by: Mapped[str] = mapped_column(String)


class Token(Base):
    __tablename__ = "tokens"
    jti: Mapped[str] = mapped_column(String, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String)
    mandate_id: Mapped[str] = mapped_column(String, index=True)
    mandate_version: Mapped[int] = mapped_column(Integer)
    client_id: Mapped[str] = mapped_column(String)
    sub: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    scope: Mapped[str] = mapped_column(String)
    aud: Mapped[str] = mapped_column(String)
    cnf_jkt: Mapped[str | None] = mapped_column(String, nullable=True)
    issued_at: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)
    revoked_at: Mapped[str | None] = mapped_column(String, nullable=True)
    authorization_details: Mapped[list] = j(default=list)


class DpopSeen(Base):
    __tablename__ = "dpop_seen"
    jti: Mapped[str] = mapped_column(String, primary_key=True)
    seen_at: Mapped[str] = mapped_column(String)


class OAuthRequest(Base):
    """Pushed authorization request and authorization code state (sandbox authorization server)."""

    __tablename__ = "oauth_requests"
    request_uri: Mapped[str] = mapped_column(String, primary_key=True)
    client_id: Mapped[str] = mapped_column(String)
    params: Mapped[dict] = j()
    expires_at: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING")  # PENDING | APPROVED | CODE_USED | DENIED
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    code_hash: Mapped[str | None] = mapped_column(String, nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String)  # READ | PAYMENT | TRANSFER | DELEGATION
    action: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    principal_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    mandate_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    mandate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mandate_chain: Mapped[list] = j(default=list)
    operation: Mapped[dict] = j(default=dict)
    op_hash: Mapped[str] = mapped_column(String, default="")
    amount_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String, default="")
    account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payee_id: Mapped[str | None] = mapped_column(String, nullable=True)
    decision_id: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str] = mapped_column(String, default="")  # ALLOW | DENY | REQUIRE_HUMAN_APPROVAL | REFER_TO_RISK_REVIEW
    reason_codes: Mapped[list] = j(default=list)
    risk: Mapped[dict] = j(default=dict)
    approval_id: Mapped[str | None] = mapped_column(String, nullable=True)
    token_jti: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    executed_at: Mapped[str | None] = mapped_column(String, nullable=True)  # when funds were reserved/moved; budgets are counted by this, not by creation time
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    dispute: Mapped[dict | None] = j(nullable=True)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tx_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String)
    reason_codes: Mapped[list] = j(default=list)
    trace: Mapped[list] = j(default=list)
    inputs: Mapped[dict] = j(default=dict)  # full snapshot enabling historical replay
    inputs_digest: Mapped[str] = mapped_column(String)
    policy_version: Mapped[str] = mapped_column(String)
    op_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)
    signature: Mapped[str] = mapped_column(String, default="")
    key_id: Mapped[str] = mapped_column(String, default="")
    consumed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tx_id: Mapped[str] = mapped_column(String, index=True)
    op_hash: Mapped[str] = mapped_column(String)
    mandate_id: Mapped[str] = mapped_column(String)
    mandate_version: Mapped[int] = mapped_column(Integer)
    principal_id: Mapped[str] = mapped_column(String, index=True)
    required_count: Mapped[int] = mapped_column(Integer, default=1)
    eligible_approvers: Mapped[list] = j(default=list)
    grants: Mapped[list] = j(default=list)
    status: Mapped[str] = mapped_column(String)  # PENDING | APPROVED | REJECTED | EXPIRED | CONSUMED | CANCELLED
    reason: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)
    display: Mapped[dict] = j(default=dict)
    consumed_at: Mapped[str | None] = mapped_column(String, nullable=True)


class Posting(Base):
    """Double-entry accounting ledger (money movement). Distinct from the KYM evidence ledger."""

    __tablename__ = "postings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tx_id: Mapped[str] = mapped_column(String, index=True)
    account_id: Mapped[str] = mapped_column(String)
    debit_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    credit_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="EXECUTION")  # EXECUTION | REVERSAL
    created_at: Mapped[str] = mapped_column(String)


class EvidenceEvent(Base):
    __tablename__ = "evidence_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String, unique=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    body: Mapped[dict] = j()  # all signed fields except hash and signature
    event_hash: Mapped[str] = mapped_column(String)
    signature: Mapped[str] = mapped_column(String)
    correlation_id: Mapped[str] = mapped_column(String, index=True)
    mandate_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    transaction_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class EvidencePayload(Base):
    """Protected payload store. Content may be erased (crypto-shredding) without breaking the hash chain."""

    __tablename__ = "evidence_payloads"
    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict | None] = j(nullable=True)
    digest: Mapped[str] = mapped_column(String)
    redacted: Mapped[bool] = mapped_column(Boolean, default=False)


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    body: Mapped[dict] = j()
    signature: Mapped[str] = mapped_column(String)
    key_id: Mapped[str] = mapped_column(String)
    witness_signature: Mapped[str] = mapped_column(String, default="")
    witness_key_id: Mapped[str] = mapped_column(String, default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text)


def get_engine():
    global _engine, _Session
    if _engine is None:
        config.ensure_dirs()
        sqlite = config.DATABASE_URL.startswith("sqlite")
        _engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {}, future=True, pool_pre_ping=not sqlite)

        if sqlite:

            @event.listens_for(_engine, "connect")
            def _pragmas(conn, _):  # noqa: ANN001
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.close()

        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    Base.metadata.create_all(get_engine())


def dispose() -> None:
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None


PG_WRITE_LOCK_ID = 0x4B594D01  # arbitrary constant: "KYM" + 1


def _lock_database(s: Session) -> None:
    """Serialize writers across processes, not just threads. Budget checks read-then-write, so two workers must never interleave them.
    SQLite: BEGIN IMMEDIATE takes the database write lock up front. PostgreSQL: a transaction-scoped advisory lock (released at commit/rollback)."""
    name = s.get_bind().dialect.name
    if name == "sqlite":
        s.connection().exec_driver_sql("BEGIN IMMEDIATE")
    elif name == "postgresql":
        s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": PG_WRITE_LOCK_ID})


@contextmanager
def write():
    """Serialized write transaction. All state changes, including evidence events, commit atomically."""
    get_engine()
    with WRITE_LOCK:
        existing = getattr(_local, "session", None)
        if existing is not None:
            yield existing
            return
        s: Session = _Session()
        _local.session = s
        try:
            _lock_database(s)
            yield s
            s.commit()
        except BaseException:
            s.rollback()
            raise
        finally:
            _local.session = None
            s.close()


@contextmanager
def read():
    get_engine()
    existing = getattr(_local, "session", None)
    if existing is not None:
        yield existing
        return
    s: Session = _Session()
    try:
        yield s
    finally:
        s.close()
