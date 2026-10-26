# Notifications

Notifications are sent with [Apprise](https://github.com/caronc/apprise), so any Apprise URL works, for example:

```text
discord://<webhook_id>/<webhook_token>
tgram://<bot_token>/<chat_id>
mailtos://user:password@mail.example.com?to=you@example.com
ntfy://ntfy.example.com/my-topic
```

See the Apprise documentation for the full list. URLs that Apprise cannot parse are rejected when saved.

## Global notifications

An admin sets `urls` and `on` under Settings (settings key `notify`). They apply to every job. The default is `on: ["failure"]`.

## Per-source notifications

Store each Apprise URL as a credential of kind `apprise`, then pick those credentials in the source's notification settings (`notify.credential_ids`) together with its own `on` list. Apprise URLs often embed secrets, which is why they live in encrypted credentials rather than in the source.

## Events

`on` is a list of any of:

| Event | Sent when |
|---|---|
| `failure` | The job failed |
| `success` | The job succeeded |
| `new_items` | At least one image was uploaded or linked |

The message has the source name and job status, the job counters and any error. Credentials and URLs are scrubbed from it. A failed send is logged as a warning and never fails the job; each send times out after 15 seconds.

## Private addresses

Per-source (user) notification URLs cannot point at private or loopback addresses: this is checked when you save the source and again when the job finishes, and the connection itself is also blocked from resolving to a private address. `allow_private_hosts` lifts this. Global URLs set by an admin are exempt. Because the connection check applies to every connection of a gated send, a private `HTTP_PROXY` / `HTTPS_PROXY` environment variable on the container also blocks gated sends; see [Security](security.md).
