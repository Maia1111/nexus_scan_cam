from __future__ import annotations

from datetime import datetime
from pathlib import Path

import bcrypt
from peewee import (
    AutoField,
    BlobField,
    BooleanField,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
)


DB_PATH = Path(__file__).parent / "scanner.db"
database = SqliteDatabase(
    DB_PATH,
    pragmas={
        "journal_mode": "wal",
        "cache_size": -1024 * 64,
        "foreign_keys": 1,
        "synchronous": 1,
    },
)


class BaseModel(Model):
    class Meta:
        database = database


class User(BaseModel):
    id = AutoField()
    username = CharField(unique=True, index=True)
    password_hash = BlobField()
    role = CharField(default="VIEWER", index=True)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)


class CameraGroup(BaseModel):
    id = AutoField()
    name = CharField(unique=True, index=True)
    description = CharField(default="")
    latitude = FloatField(null=True)
    longitude = FloatField(null=True)
    created_at = DateTimeField(default=datetime.utcnow)


class Camera(BaseModel):
    id = AutoField()
    name = CharField(default="")
    username = CharField(null=True)
    password = CharField(null=True)
    brand = CharField(default="Desconhecida", index=True)
    ip_address = CharField(unique=True, index=True)
    mac_address = CharField(null=True, index=True)
    location = CharField(null=True)
    group = ForeignKeyField(CameraGroup, null=True, backref="cameras", on_delete="SET NULL")
    open_ports_csv = CharField(default="")
    score = IntegerField(default=0)
    is_online = BooleanField(default=False)
    latency_ms = FloatField(null=True)
    last_seen_at = DateTimeField(null=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)


def hash_password(plain_password: str) -> bytes:
    if not plain_password:
        raise ValueError("Senha não pode ser vazia.")
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=12))


def verify_password(plain_password: str, password_hash: bytes) -> bool:
    if not plain_password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash)
    except ValueError:
        return False


def create_user(username: str, plain_password: str, role: str = "VIEWER") -> User:
    normalized_role = role.upper()
    if normalized_role not in {"ADMIN", "VIEWER"}:
        raise ValueError("Role inválida. Use ADMIN ou VIEWER.")

    return User.create(
        username=username.strip(),
        password_hash=hash_password(plain_password),
        role=normalized_role,
    )


def initialize_database() -> None:
    database.connect(reuse_if_open=True)
    database.create_tables([User, CameraGroup, Camera], safe=True)
    ensure_schema_migrations()


def _table_columns(table_name: str) -> set[str]:
    rows = database.execute_sql(f"PRAGMA table_info('{table_name}')").fetchall()
    return {row[1] for row in rows}


def ensure_schema_migrations() -> None:
    camera_columns = _table_columns("camera")

    if "location" not in camera_columns:
        database.execute_sql("ALTER TABLE camera ADD COLUMN location VARCHAR(255)")

    if "group_id" not in camera_columns:
        database.execute_sql(
            "ALTER TABLE camera ADD COLUMN group_id INTEGER REFERENCES cameragroup(id) ON DELETE SET NULL"
        )

    if "name" not in camera_columns:
        database.execute_sql("ALTER TABLE camera ADD COLUMN name VARCHAR(255) NOT NULL DEFAULT ''")

    if "username" not in camera_columns:
        database.execute_sql("ALTER TABLE camera ADD COLUMN username VARCHAR(255)")

    if "password" not in camera_columns:
        database.execute_sql("ALTER TABLE camera ADD COLUMN password VARCHAR(255)")

    group_columns = _table_columns("cameragroup")
    if "description" not in group_columns:
        database.execute_sql("ALTER TABLE cameragroup ADD COLUMN description VARCHAR(255) NOT NULL DEFAULT ''")
    if "latitude" not in group_columns:
        database.execute_sql("ALTER TABLE cameragroup ADD COLUMN latitude REAL")
    if "longitude" not in group_columns:
        database.execute_sql("ALTER TABLE cameragroup ADD COLUMN longitude REAL")


def has_any_user() -> bool:
    initialize_database()
    return User.select().exists()


def ensure_default_camera_group() -> CameraGroup:
    initialize_database()
    group, _created = CameraGroup.get_or_create(name="Minhas Câmeras")
    return group


def ensure_default_admin(username: str = "admin", password: str = "admin123") -> None:
    """Opcional: cria o admin padrão se chamado explicitamente."""
    initialize_database()
    if not User.select().where(User.username == username).exists():
        create_user(username=username, plain_password=password, role="ADMIN")
