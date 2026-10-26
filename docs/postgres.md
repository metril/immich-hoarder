# PostgreSQL

SQLite is the default and is enough for most installs. Use PostgreSQL if you want an external database or heavy concurrent use.

**PostgreSQL 14 or later is required.** Near-duplicate matching uses the `bit_count` function, which was added in 14.

## Compose override

Use [`deploy/compose.postgres.yml`](https://github.com/metril/immich-hoarder/blob/main/deploy/compose.postgres.yml) on top of the base file:

```bash
openssl rand -base64 32 | tr -d '\n' > secrets/ih_pg_password
# secrets/ih_db_url holds the full database URL, with that password:
printf 'postgresql://hoarder:<password>@postgres:5432/hoarder' > secrets/ih_db_url
sudo chown 10001:10001 secrets/ih_db_url && chmod 600 secrets/ih_db_url
docker compose -f compose.example.yml -f deploy/compose.postgres.yml up -d
```

The override adds a `postgres` service (data in the `ih_pg` volume) and sets `IH_DATABASE_URL_FILE` so the password stays in a Docker secret rather than in an environment variable. Use a URL-safe password (or percent-encode it), because it sits inside the URL.

## Database URL

`postgresql://` and `postgres://` URLs are normalized to the asyncpg driver; other SQLAlchemy URLs are passed through unchanged. TLS parameters such as `?ssl=require` are supported.

## Schema and migrations

The same schema is used as for SQLite. Alembic migrations run automatically on every start.

## Moving from SQLite

There is no SQLite to PostgreSQL migration tool. Either start fresh and re-create your configuration with a [config export and import](backups.md#config-export-and-import), or re-run your sources. Dedupe history does not carry over, so existing images are matched again against Immich's own duplicate check rather than the local history.

## Backups

Use `pg_dump`; see [Backups](backups.md#postgresql).
