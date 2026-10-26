# Egress and proxies

By default the container downloads directly. To route source fetches through a proxy, for example a VPN, set one of two proxies. Only `http` and `https` proxy URLs are accepted.

## Global proxy

An admin sets `proxy` in Settings (rip settings). It is used for all downloads. A global proxy may be on a private address, which is what you need for a sidecar such as gluetun.

## Per-source proxy

A source can set its own `proxy`. It is validated like the global one, but a private proxy host is rejected unless the admin has enabled `allow_private_hosts`. A per-source proxy overrides the global one for that source.

## gluetun VPN override

[`deploy/compose.gluetun.yml`](https://github.com/metril/immich-hoarder/blob/main/deploy/compose.gluetun.yml) adds a gluetun container that exposes an HTTP proxy on port 8888 and makes the app wait for it to be healthy:

```bash
export VPN_SERVICE_PROVIDER=<provider>   # required; VPN_TYPE defaults to wireguard
docker compose -f compose.example.yml -f deploy/compose.gluetun.yml up -d
```

Add your provider's variables (keys, regions) to the `gluetun` service environment; see the gluetun wiki. Then set the **global** proxy in Settings to `http://gluetun:8888`. gluetun is on the default network only and is not exposed through Traefik.

## What the proxy does and does not cover

- Only downloads from the sites go through the proxy. Uploads to Immich do not.
- Without a proxy, the private-address guard checks every address a download host resolves to.
- With a proxy, the proxy resolves and connects to the site, so protection against a download host that points at an internal address is the proxy's job. Restrict the proxy's own network access.
