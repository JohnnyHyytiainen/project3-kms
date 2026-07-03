# models.py script, här jag deklarerar mina models
# Kod: Engelska
# Kommentarer: Svenska

# Imports
import enum
from datetime import datetime

# SQLAlchemy imports
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class DocumentStatus(str, enum.Enum):
    """String-based state machine, new values should never require a schema migration, only a code change."""

    PENDING = "pending"
    EXTRACTED = "extracted"
    EMBEDDED = "embedded"
    FAILED = "failed"


# SQLAlchemy baseclass för Document
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 1024 = S3's faktiska maxlängd för nycklar
    # Unik, namespace {course_tag}/{repo}/{path} garanterar det per design
    # en dubblett vore en bug, inte ett giltigt tillstånd
    s3_key: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))

    # Sträng, inte enum - beslut 4/5: kod-filtyper (.py/.sql/.ipynb) läggs
    # till som framtida iteration utan schemaändring
    source_type: Mapped[str] = mapped_column(String(20))
    course_tag: Mapped[str] = mapped_column(String(50), index=True)

    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus, native_enum=False, length=20, validate_strings=True),
        default=DocumentStatus.PENDING,
    )

    # Indexed, INTE UNIK, samma innehåll (exempel, en delad README mall)
    # Kan finnas i flera repon med olika s3_keys
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Server_default, inte python default. Postgres egen NOW()
    # Vald nu i mvp v1 för att underlätta när Airflow kör parallella tasks i v5
    # Samma anledning till att status blev en tillståndsmaskin per rad
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


# SQLAlchemy baseclass för Chunks
class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)

    # Nullable, fyller i först i MVP v3 när mina chunks faktiskt har embeddats
    vector_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # JSONB(JSONL), inte för separata columns, platsdata skiljer sig per source_type
    # exempel: Sidnummer för PDF, row intervall för markdown, tidsintervall för YT transkript.
    # Postgres specifik typ, inte generisk JSON, bättre indexerbar
    source_location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    char_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="chunks")


# SQLAlchemy baseclass för User(Säkerhetstänk för kommande mvp versioner)
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # HASH, ALDRIG I KLARTEXT!!!! Även i privat repo, samma säkerhetstänk som redan syns i .env och .gitignore
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
