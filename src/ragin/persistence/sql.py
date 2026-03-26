from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from ragin.persistence.base import BaseBackend
from ragin.persistence.schema import model_to_table


class SqlBackend(BaseBackend):
    """
    SQLAlchemy Core backend (no ORM).
    Works with any database supported by SQLAlchemy:
    - SQLite (dev/test): sqlite:///./dev.db  or  sqlite:///:memory:
    - PostgreSQL (prod): postgresql+psycopg2://user:pass@host/db
    """

    def __init__(self, url: str) -> None:
        self._engine = sa.create_engine(url)
        self._metadata = sa.MetaData()
        self._tables: dict[str, sa.Table] = {}

    def register(self, model_cls: type) -> None:
        table = model_to_table(model_cls, self._metadata)
        self._tables[model_cls.__name__] = table
        self._metadata.create_all(self._engine)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _table(self, model_cls: type) -> sa.Table:
        name = model_cls.__name__
        if name not in self._tables:
            # Auto-register on first use so callers don't need to call
            # register() explicitly if they use configure_backend() early.
            self.register(model_cls)
        return self._tables[name]

    @staticmethod
    def _pk_column(table: sa.Table) -> sa.Column:
        for col in table.primary_key:
            return col
        raise ValueError(f"Table {table.name!r} has no primary key column")

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def insert(self, model_cls: type, data: dict) -> dict:
        table = self._table(model_cls)
        stmt = sa.insert(table).values(**data).returning(*table.c)
        with self._engine.connect() as conn:
            result = conn.execute(stmt)
            row = dict(result.mappings().fetchone())  # fetch BEFORE commit
            conn.commit()
            return row

    def select(self, model_cls: type, filters: dict, limit: int = 100, offset: int = 0) -> list[dict]:
        table = self._table(model_cls)
        query = sa.select(table)
        for k, v in filters.items():
            if k in table.c:
                query = query.where(table.c[k] == v)
        query = query.limit(limit).offset(offset)
        with self._engine.connect() as conn:
            result = conn.execute(query)
            return [dict(row._mapping) for row in result.fetchall()]

    def get(self, model_cls: type, pk_value: Any) -> dict | None:
        table = self._table(model_cls)
        pk_col = self._pk_column(table)
        query = sa.select(table).where(pk_col == pk_value)
        with self._engine.connect() as conn:
            result = conn.execute(query)
            row = result.mappings().fetchone()
            return dict(row) if row else None

    def update(self, model_cls: type, pk_value: Any, data: dict) -> dict | None:
        table = self._table(model_cls)
        pk_col = self._pk_column(table)
        # Only update columns that exist in the table (ignore unknown keys)
        clean_data = {k: v for k, v in data.items() if k in table.c and k != pk_col.name}
        if not clean_data:
            return self.get(model_cls, pk_value)
        stmt = (
            sa.update(table)
            .where(pk_col == pk_value)
            .values(**clean_data)
            .returning(*table.c)
        )
        with self._engine.connect() as conn:
            result = conn.execute(stmt)
            row = result.mappings().fetchone()  # fetch BEFORE commit
            conn.commit()
            return dict(row) if row else None

    def delete(self, model_cls: type, pk_value: Any) -> bool:
        table = self._table(model_cls)
        pk_col = self._pk_column(table)
        stmt = sa.delete(table).where(pk_col == pk_value)
        with self._engine.connect() as conn:
            result = conn.execute(stmt)
            rowcount = result.rowcount  # read BEFORE commit
            conn.commit()
            return rowcount > 0
