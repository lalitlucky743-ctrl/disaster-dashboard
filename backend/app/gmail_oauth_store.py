
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, MetaData, Table, Text, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .database import Base, engine

gmail_oauth_tokens = Table(
    "gmail_oauth_tokens",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("credentials_encrypted", Text, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)


def save_encrypted_credentials(encrypted_value: str) -> None:
    with engine.begin() as connection:
        existing = connection.execute(
            select(gmail_oauth_tokens.c.id).where(
                gmail_oauth_tokens.c.id == 1
            )
        ).first()

        if existing:
            connection.execute(
                gmail_oauth_tokens.update()
                .where(gmail_oauth_tokens.c.id == 1)
                .values(
                    credentials_encrypted=encrypted_value,
                    updated_at=datetime.utcnow(),
                )
            )
        else:
            connection.execute(
                gmail_oauth_tokens.insert().values(
                    id=1,
                    credentials_encrypted=encrypted_value,
                    updated_at=datetime.utcnow(),
                )
            )


def get_encrypted_credentials():
    with engine.connect() as connection:
        return connection.execute(
            select(gmail_oauth_tokens.c.credentials_encrypted).where(
                gmail_oauth_tokens.c.id == 1
            )
        ).scalar_one_or_none()
