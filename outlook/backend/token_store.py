"""Encrypted per-Microsoft-user MSAL cache and backend sessions."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TokenStore:
    def __init__(self, database_path, encryption_key):
        if len(encryption_key) != 32:
            raise ValueError("The token encryption key must be 32 bytes.")
        self.database_path = str(database_path)
        self._cipher = AESGCM(encryption_key)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().parent.mkdir(
                parents=True, exist_ok=True
            )
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outlook_accounts (
                    owner_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    encrypted_cache BLOB NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outlook_sessions (
                    token_hash TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    FOREIGN KEY(owner_id) REFERENCES outlook_accounts(owner_id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS outlook_oauth_transactions (
                    transaction_id TEXT PRIMARY KEY,
                    secret_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    encrypted_flow BLOB NOT NULL,
                    status TEXT NOT NULL,
                    owner_id TEXT,
                    email TEXT,
                    encrypted_session_token BLOB,
                    expires_at INTEGER NOT NULL
                );
                """
            )

    def _encrypt(self, value, associated_data):
        nonce = secrets.token_bytes(12)
        return nonce + self._cipher.encrypt(nonce, value, associated_data)

    def _decrypt(self, value, associated_data):
        nonce, ciphertext = value[:12], value[12:]
        return self._cipher.decrypt(nonce, ciphertext, associated_data)

    @staticmethod
    def _token_hash(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _aad(label):
        return label.encode("utf-8")

    def create_oauth_transaction(self, transaction_id, secret, state, flow, ttl):
        flow_bytes = flow.encode("utf-8")
        encrypted_flow = self._encrypt(
            flow_bytes, self._aad(f"oauth-flow:{transaction_id}")
        )
        now = int(time.time())
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM outlook_oauth_transactions WHERE expires_at < ?",
                (now,),
            )
            connection.execute(
                "DELETE FROM outlook_sessions WHERE expires_at < ?", (now,)
            )
            connection.execute(
                """
                INSERT INTO outlook_oauth_transactions (
                    transaction_id, secret_hash, state, encrypted_flow,
                    status, expires_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (
                    transaction_id,
                    self._token_hash(secret),
                    state,
                    encrypted_flow,
                    now + ttl,
                ),
            )

    def load_oauth_flow(self, transaction_id, state):
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT state, encrypted_flow, expires_at, status
                FROM outlook_oauth_transactions
                WHERE transaction_id = ?
                """,
                (transaction_id,),
            ).fetchone()
        if (
            row is None
            or row["status"] != "pending"
            or row["expires_at"] < int(time.time())
            or not hmac.compare_digest(row["state"], str(state or ""))
        ):
            return None
        encrypted_flow = bytes(row["encrypted_flow"])
        return self._decrypt(
            encrypted_flow, self._aad(f"oauth-flow:{transaction_id}")
        ).decode("utf-8")

    def find_transaction_id(self, state):
        if not state:
            return None
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT transaction_id FROM outlook_oauth_transactions
                WHERE state = ? AND status = 'pending' AND expires_at >= ?
                """,
                (str(state), int(time.time())),
            ).fetchone()
        return row["transaction_id"] if row else None

    def complete_oauth_transaction(
        self, transaction_id, owner_id, tenant_id, object_id, email, serialized_cache
    ):
        encrypted_cache = self._encrypt(
            serialized_cache.encode("utf-8"),
            self._aad(f"msal-cache:{owner_id}"),
        )
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            transaction = connection.execute(
                """
                SELECT status, expires_at FROM outlook_oauth_transactions
                WHERE transaction_id = ?
                """,
                (transaction_id,),
            ).fetchone()
            if (
                transaction is None
                or transaction["status"] != "pending"
                or transaction["expires_at"] < now
            ):
                raise ValueError("OAuth transaction is no longer active.")
            connection.execute(
                """
                INSERT INTO outlook_accounts (
                    owner_id, tenant_id, object_id, email, encrypted_cache, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    object_id = excluded.object_id,
                    email = excluded.email,
                    encrypted_cache = excluded.encrypted_cache,
                    updated_at = excluded.updated_at
                """,
                (owner_id, tenant_id, object_id, email, encrypted_cache, now),
            )
            updated = connection.execute(
                """
                UPDATE outlook_oauth_transactions
                SET status = 'complete', owner_id = ?, email = ?
                WHERE transaction_id = ? AND status = 'pending'
                """,
                (owner_id, email, transaction_id),
            )
            if updated.rowcount != 1:
                raise ValueError("OAuth transaction could not be completed.")

    def fail_oauth_transaction(self, transaction_id):
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE outlook_oauth_transactions SET status = 'failed'
                WHERE transaction_id = ? AND status = 'pending'
                """,
                (transaction_id,),
            )

    def poll_oauth_transaction(self, transaction_id, secret, session_ttl):
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT secret_hash, status, owner_id, email, expires_at,
                       encrypted_session_token
                FROM outlook_oauth_transactions
                WHERE transaction_id = ?
                """,
                (transaction_id,),
            ).fetchone()
            if (
                row is None
                or row["expires_at"] < now
                or not hmac.compare_digest(
                    row["secret_hash"], self._token_hash(str(secret or ""))
                )
            ):
                return {"status": "invalid"}
            if row["status"] == "pending":
                return {"status": "pending"}
            if row["status"] != "complete" or not row["owner_id"]:
                return {"status": "failed"}

            encrypted_session = row["encrypted_session_token"]
            if encrypted_session is not None:
                token = self._decrypt(
                    bytes(encrypted_session),
                    self._aad(f"oauth-session:{transaction_id}"),
                ).decode("utf-8")
            else:
                token = secrets.token_urlsafe(32)
                encrypted_session = self._encrypt(
                    token.encode("utf-8"),
                    self._aad(f"oauth-session:{transaction_id}"),
                )
                connection.execute(
                    "DELETE FROM outlook_sessions WHERE owner_id = ?",
                    (row["owner_id"],),
                )
                connection.execute(
                    """
                    INSERT INTO outlook_sessions (token_hash, owner_id, expires_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        self._token_hash(token),
                        row["owner_id"],
                        now + session_ttl,
                    ),
                )
                connection.execute(
                    """
                    UPDATE outlook_oauth_transactions
                    SET encrypted_session_token = ?
                    WHERE transaction_id = ?
                    """,
                    (encrypted_session, transaction_id),
                )
            return {
                "status": "complete",
                "session_token": token,
                "email": row["email"],
            }

    def resolve_session(self, token):
        if not token:
            return None
        token_hash = self._token_hash(token)
        now = int(time.time())
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT owner_id FROM outlook_sessions
                WHERE token_hash = ? AND expires_at >= ?
                """,
                (token_hash, now),
            ).fetchone()
        return row["owner_id"] if row else None

    def get_account(self, owner_id):
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT tenant_id, object_id, email, encrypted_cache
                FROM outlook_accounts WHERE owner_id = ?
                """,
                (owner_id,),
            ).fetchone()
        if row is None:
            return None
        encrypted_cache = bytes(row["encrypted_cache"])
        cache = self._decrypt(
            encrypted_cache, self._aad(f"msal-cache:{owner_id}")
        ).decode("utf-8")
        return {
            "tenant_id": row["tenant_id"],
            "object_id": row["object_id"],
            "email": row["email"],
            "cache": cache,
        }

    def update_cache(self, owner_id, serialized_cache):
        encrypted_cache = self._encrypt(
            serialized_cache.encode("utf-8"),
            self._aad(f"msal-cache:{owner_id}"),
        )
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE outlook_accounts
                SET encrypted_cache = ?, updated_at = ?
                WHERE owner_id = ?
                """,
                (encrypted_cache, int(time.time()), owner_id),
            )
            return cursor.rowcount == 1

    def disconnect(self, owner_id):
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM outlook_sessions WHERE owner_id = ?", (owner_id,)
            )
            connection.execute(
                "DELETE FROM outlook_accounts WHERE owner_id = ?", (owner_id,)
            )
            connection.execute(
                """
                UPDATE outlook_oauth_transactions SET status = 'failed'
                WHERE owner_id = ?
                """,
                (owner_id,),
            )
