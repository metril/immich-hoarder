# Backups

## SQLite snapshots

With the default SQLite database, the app writes consistent snapshots with `VACUUM INTO` to `/data/backups` (`IH_BACKUP_DIR`) as `hoarder-<UTC timestamp>.db`. They run on the `backup_cron` runtime setting (default `0 3 * * *`, evaluated in UTC) and the newest `backup_keep` (default 7) are kept; older ones are deleted. Setting `backup_keep` to `0` turns scheduled backups off. Both settings are in Settings and the [configuration reference](reference/configuration.md).

An admin can take a snapshot on demand with **Backup now** in Settings, or `POST /api/v1/admin/backup`; `GET /api/v1/admin/backups` lists the files. `POST /api/v1/admin/maintenance/prune` removes finished jobs older than `retention_days` and ephemeral (ad-hoc) sources with no jobs (this also runs daily at 04:00 UTC).

The `/data` volume holds both the live database and the snapshots, so also copy the snapshots off the host.

## Restore

```bash
docker compose stop immich-hoarder
# copy the snapshot into the data volume as the live database
docker compose run --rm --no-deps --entrypoint sh -v "$PWD:/restore:ro" immich-hoarder \
  -c 'cp /restore/hoarder-20260101-030000.db /data/hoarder.db && rm -f /data/hoarder.db-wal /data/hoarder.db-shm'
docker compose start immich-hoarder
```

The point is: stop the container, put the snapshot at `/data/hoarder.db`, delete any `hoarder.db-wal` and `hoarder.db-shm`, then start. Migrations run automatically on start. Use the same `MASTER_KEY` as when the snapshot was taken.

## Config export and import

Admins can export sources, targets, credentials, sharing and settings as YAML and import it elsewhere (Settings, or `GET /api/v1/admin/export` and `POST /api/v1/admin/import`).

- `secrets=omit` (default): secrets are left out. After import, re-enter credentials, target API keys and notification URLs.
- `secrets=encrypted`: secrets are included, encrypted with `MASTER_KEY`. They import only into an instance with the same key.

```bash
curl -H "X-API-Key: ih_..." "https://hoarder.example.com/api/v1/admin/export?secrets=encrypted" -o hoarder.yaml
curl -H "X-API-Key: ih_..." -H 'Content-Type: application/yaml' --data-binary @hoarder.yaml \
  "https://hoarder.example.com/api/v1/admin/import?dry_run=true"
```

`dry_run=true` validates and reports what would be created or skipped without changing anything. Imports are limited to 5 MiB. Existing items are skipped, not overwritten. The export holds configuration only, not the dedupe history.

!!! warning "Keep MASTER_KEY"
    Stored credentials, target API keys and encrypted exports are unrecoverable without `MASTER_KEY`. Back it up separately from the database.

## Litestream (optional)

[Litestream](https://litestream.io) can continuously replicate the SQLite file to S3. This is optional and not tested by CI. Run it as a sidecar on the same `/data` volume:

```yaml
  litestream:
    image: litestream/litestream:0.3.13
    restart: unless-stopped
    command: replicate /data/hoarder.db s3://my-bucket/hoarder
    environment:
      LITESTREAM_ACCESS_KEY_ID_FILE: /run/secrets/ls_key_id   # or plain env vars
      LITESTREAM_SECRET_ACCESS_KEY_FILE: /run/secrets/ls_secret
    volumes:
      - ih_data:/data
```

Check the Litestream docs for the options of your version, pin it by digest, and restore with `litestream restore` while the app is stopped.

## PostgreSQL

The app's snapshots (`VACUUM INTO`) and the backup button do not apply to PostgreSQL: the API returns 409 "backups are not supported for this database". Back up the database with `pg_dump`:

```bash
docker compose exec postgres pg_dump -U hoarder -Fc hoarder > hoarder.dump
```

Restore with `pg_restore` into an empty database while the app is stopped. See [PostgreSQL](postgres.md).
