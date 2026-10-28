# Sources

A source is a URL, an Immich target and options. Each run downloads the images, de-duplicates them and uploads the new ones to Immich.

## Supported sites

Supported sites are the [gallery-dl](https://github.com/mikf/gallery-dl) extractors. List them on your instance with `GET /api/v1/extractors`. A URL that no extractor matches is rejected when you create (or preview) the source with `unsupported url`. Only `http` and `https` URLs are accepted, and URLs pointing at private addresses are rejected with `private host not allowed` unless an admin enables `allow_private_hosts` (see [Security](security.md)).

## Images only

Only images are uploaded. Anything gallery-dl downloads that is not an image is counted as filtered (`not_an_image`). Animated images (animated GIF, APNG, animated WebP) are skipped as `animated` unless you turn on **Allow animated** (`allow_animated`) for the source.

## Filters

Filters are a JSON object on the source (`filters`). All keys are optional; unknown keys are rejected.

| Key | Meaning |
|---|---|
| `min_width`, `min_height` | Minimum pixel size (>= 0) |
| `min_bytes`, `max_bytes` | File size bounds in bytes (>= 0) |
| `aspect_min`, `aspect_max` | Width / height bounds (>= 0) |
| `title_include` | Regex (case-insensitive, max 200 chars); the title must match |
| `title_exclude` | Regex (case-insensitive, max 200 chars); the title must not match |
| `date_from`, `date_to` | Post date range, `YYYY-MM-DD`, inclusive |
| `max_items` | Stop after this many items (>= 1) |
| `phash_distance` | Near-duplicate threshold, 0 to 3 (default 3); `null` turns near-duplicate matching off |

Each minimum must not exceed its maximum. Items rejected by a filter are counted as `filtered`.

## Backfill and later runs

`backfill_mode` controls the first run:

| Mode | `backfill_value` | Behaviour |
|---|---|---|
| `full` | empty | Fetch everything the site returns |
| `last_n` | integer >= 1 | Fetch only the newest N posts |
| `since` | ISO date | Fetch only posts on or after that date |

Once a source has recorded items, later runs are incremental: the downloader skips what it has already seen and stops after a run of already-seen items, so only new items are fetched. The backfill setting applies to the first run only.

## Schedules

`schedule_cron` is a five-field cron expression, evaluated in UTC. Leave it empty for manual runs only. If a source already has an active job, a scheduled run is skipped.

## Albums

`album_template` decides which Immich album each image goes into. Albums are created when missing. Fields are written in braces, with no format specs or conversions:

| Field | Value |
|---|---|
| `{subreddit}` | Subreddit name |
| `{author}` | Post author |
| `{user}` | User (falls back to author) |
| `{site}` / `{category}` | The site (extractor) name |
| `{source}` | The source's name |
| `{date}` | Post month as `YYYY-MM` |

Examples: `Reddit/{subreddit}`, `{author}`, or fixed text like `Wallpapers`. If the template is empty or a field is missing from an item, the album falls back to the source name. Control characters are stripped and names are limited to 255 characters.

## De-duplication

De-duplication is per Immich target, so the same image from two sources goes to a target once:

1. **Exact:** the SHA-1 of the file is compared against what the target has seen. Immich's own duplicate check also runs.
2. **Near-duplicate:** the perceptual hash (pHash) is compared, and images within Hamming distance 3 (`phash_distance`, at most 3) count as the same.

A match is not uploaded again; the existing asset is linked into the album instead and counted as `linked`. If a match was deleted or trashed in Immich, the image is not re-uploaded: it is counted as `deleted_in_immich`.

## Dry-run preview

**Preview** in the source editor runs the source's URL, filters and credential against the site and lists up to 50 items without uploading anything (`POST /api/v1/sources/preview`, limit 1 to 50, 60 second timeout).

## Sharing

`visibility` is `private` (owner and admins), `everyone` (any signed-in user can use it) or `restricted` (only listed users and groups). Restricted shares grant `use` (run it) or `edit` (change it; implies `use`). Targets and credentials share the same way.

## Log levels

A source can set `log_level` (`trace`, `debug`, `info`, `warn`, `error`) and a single run can override it. Per-run: pass `{"log_level": "debug"}` to the run endpoint, or choose a level in the GUI. The job log viewer filters by level.

## Rate limits

Rate limits are per site and set by an admin in Settings (`rate_limits`, keyed by extractor name, or `default`): `sleep_request` (seconds between requests, default 1.0), `sleep` (seconds between file downloads) and `retries` (default 4). Per-source `gdl_options` cannot weaken the sleeps below these limits; allowed keys are `sleep`, `sleep-request`, `retries`, `timeout`, `include`, `recursion` and `previews`.

## Reddit setup

Reddit blocks anonymous gallery-dl requests ("blocked by network security"). Use one of:

- **Cookies with `token_v2` (kind `cookies`, site `reddit`).** Export your logged-in reddit.com cookies as Netscape `cookies.txt`, or just paste the `token_v2` value (a `token_v2=...; ...` cookie header also works); `token_v2` is required. It is sent as a bearer token to `oauth.reddit.com`. It lasts about 24 hours, then runs fail with "Reddit token_v2 expired; re-export cookies". There is no automatic refresh.
- **Your own OAuth app (kind `oauth`, site `reddit`).** JSON with `client-id`, `client-secret` and `refresh-token`, plus an optional `user-agent` (default `immich-hoarder/<version>`). It does not expire, but Reddit now requires approval for new apps.

## Ad-hoc rips

`POST /api/v1/rip` takes the same body as a source and runs it once as a private, ephemeral source. Ephemeral sources are pruned automatically.
