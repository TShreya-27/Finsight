from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from app.db.models import Base


class User(Base):
    """Local Postgres user used by the authentication service."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True))
    last_sign_in_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
