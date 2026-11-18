from __future__ import annotations

import json
import hashlib
import time
import uuid
from contextlib import contextmanager

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    event,
    insert,
    select,
    update,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateSchema

metadata = MetaData()
records = Table(
    "workspace_records",
    metadata,
    Column("tenant", String(40), primary_key=True),
    Column("kind", String(32), primary_key=True),
    Column("id", String(100), primary_key=True),
    Column("body", Text, nullable=False),
    Column("created", Float, nullable=False),
)
jobs = Table(
    "workspace_jobs",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("tenant", String(40), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("dedupe", String(180), nullable=False),
    Column("payload", Text, nullable=False),
    Column("status", String(30), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("due", Float, nullable=False, index=True),
    Column("lease_until", Float),
    Column("lease_token", String(40)),
    Column("error", String(160)),
    Column("created", Float, nullable=False),
    UniqueConstraint("tenant", "dedupe"),
)
sessions = Table(
    "workspace_sessions",
    metadata,
    Column("hash", String(64), primary_key=True),
    Column("tenant", String(40), nullable=False),
    Column("role", String(20), nullable=False),
    Column("subject", String(100), nullable=False),
    Column("expires", Float, nullable=False),
)


class Database:
    def __init__(self, url: str):
        kwargs = (
            {"connect_args": {"check_same_thread": False, "timeout": 30}}
            if url.startswith("sqlite")
            else {"pool_pre_ping": True}
        )
        self.engine = create_engine(url, **kwargs)
        if self.engine.dialect.name == "postgresql":
            # Keep operational PII/session tables out of Supabase's exposed public schema.
            with self.engine.begin() as conn:
                conn.execute(CreateSchema("workspace_private", if_not_exists=True))
            self.engine = self.engine.execution_options(
                schema_translate_map={None: "workspace_private"}
            )
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def sqlite_setup(conn, _):
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")

        metadata.create_all(self.engine)

    @contextmanager
    def transaction(self, tenant=None):
        # Acquire the write lock before reading: read/modify/write is one unit.
        # Network calls must stay outside these short transactions.
        with self.engine.connect() as conn:
            if self.engine.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                conn.begin()
                if tenant is not None:
                    key = int.from_bytes(
                        hashlib.sha256(tenant.encode()).digest()[:8], "big", signed=True
                    )
                    conn.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"), {"key": key}
                    )
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def get(self, tenant, kind, key, conn=None):
        if conn is None:
            with self.engine.connect() as c:
                return self.get(tenant, kind, key, c)
        value = conn.execute(
            select(records.c.body).where(
                records.c.tenant == tenant, records.c.kind == kind, records.c.id == key
            )
        ).scalar_one_or_none()
        return json.loads(value) if value is not None else None

    def list(self, tenant, kind, conn=None):
        if conn is None:
            with self.engine.connect() as c:
                return self.list(tenant, kind, c)
        return [
            json.loads(v)
            for v in conn.execute(
                select(records.c.body)
                .where(records.c.tenant == tenant, records.c.kind == kind)
                .order_by(records.c.created.desc())
            ).scalars()
        ]

    def put(self, tenant, kind, key, body, conn=None):
        if conn is None:
            with self.transaction(tenant) as c:
                return self.put(tenant, kind, key, body, c)
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        make = sqlite_insert if self.engine.dialect.name == "sqlite" else pg_insert
        stmt = make(records).values(
            tenant=tenant,
            kind=kind,
            id=key,
            body=json.dumps(body, ensure_ascii=False),
            created=time.time(),
        )
        conn.execute(
            stmt.on_conflict_do_update(
                index_elements=["tenant", "kind", "id"],
                set_={"body": stmt.excluded.body},
            )
        )
        return body

    def remove(self, tenant, kind, key, conn=None):
        if conn is None:
            with self.transaction(tenant) as c:
                return self.remove(tenant, kind, key, c)
        conn.execute(
            delete(records).where(
                records.c.tenant == tenant, records.c.kind == kind, records.c.id == key
            )
        )

    def create_once(self, tenant, kind, key, body):
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        make = sqlite_insert if self.engine.dialect.name == "sqlite" else pg_insert
        with self.transaction(tenant) as c:
            stmt = (
                make(records)
                .values(
                    tenant=tenant,
                    kind=kind,
                    id=key,
                    body=json.dumps(body),
                    created=time.time(),
                )
                .on_conflict_do_nothing(index_elements=["tenant", "kind", "id"])
            )
            return c.execute(stmt).rowcount == 1

    def enqueue(self, tenant, kind, dedupe, payload, delay=0, conn=None):
        if conn is None:
            with self.transaction(tenant) as c:
                return self.enqueue(tenant, kind, dedupe, payload, delay, c)
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        make = sqlite_insert if self.engine.dialect.name == "sqlite" else pg_insert
        stmt = make(jobs).values(
            id=uuid.uuid4().hex,
            tenant=tenant,
            kind=kind,
            dedupe=dedupe,
            payload=json.dumps(payload),
            status="pending",
            attempts=0,
            due=time.time() + delay,
            created=time.time(),
        )
        conn.execute(stmt.on_conflict_do_nothing(index_elements=["tenant", "dedupe"]))

    def list_jobs(self, tenant):
        with self.engine.connect() as c:
            return [
                dict(r._mapping)
                for r in c.execute(
                    select(jobs)
                    .where(jobs.c.tenant == tenant)
                    .order_by(jobs.c.created.desc())
                    .limit(200)
                )
            ]

    def claim_job(self, tenant=None):
        now = time.time()
        with self.transaction() as c:
            available = ((jobs.c.status == "pending") & (jobs.c.due <= now)) | (
                (jobs.c.status == "running") & (jobs.c.lease_until < now)
            )
            if tenant is not None:
                available = available & (jobs.c.tenant == tenant)
            candidate = c.execute(
                select(jobs.c.id).where(available).order_by(jobs.c.due).limit(1)
            ).scalar_one_or_none()
            if not candidate:
                return None
            token = uuid.uuid4().hex
            row = c.execute(
                update(jobs)
                .where(jobs.c.id == candidate, available)
                .values(
                    status="running",
                    lease_until=now + 120,
                    lease_token=token,
                    attempts=jobs.c.attempts + 1,
                )
                .returning(jobs)
            ).first()
            return dict(row._mapping) if row else None

    def finish_job(self, job, status, error=None):
        with self.transaction() as c:
            c.execute(
                update(jobs)
                .where(jobs.c.id == job["id"], jobs.c.lease_token == job["lease_token"])
                .values(
                    status=status,
                    error=error,
                    due=time.time() + min(3600, 30 * 2 ** job["attempts"]),
                    lease_until=None,
                )
            )
