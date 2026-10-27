# Changelog

## [0.5.0](https://github.com/metril/immich-hoarder/compare/v0.4.0...v0.5.0) (2026-10-27)


### ⚠ BREAKING CHANGES

* **auth:** OIDC env vars are deprecated (imported once); existing sessions must log in again.

### Features

* **auth:** configure OIDC and auth in the web UI with minimal env ([ae881ad](https://github.com/metril/immich-hoarder/commit/ae881ad4cfcbfa23b67e57194018d12db12ba983))

## [0.4.0](https://github.com/metril/immich-hoarder/compare/v0.3.0...v0.4.0) (2026-10-26)


### Features

* **sources:** friendly schedule builder with local-time and next runs ([ee75179](https://github.com/metril/immich-hoarder/commit/ee7517983fd5bd37349f638282a59715a39f4e32))
* **ui:** immich blue colour scheme and clearer concurrency hints ([5ac6aa4](https://github.com/metril/immich-hoarder/commit/5ac6aa44f0e1ff72f520cb311e8f6268bc99da90))


### Bug Fixes

* **sources:** timezone-correct hourly/monthly schedules and stricter cron validation ([ee14a43](https://github.com/metril/immich-hoarder/commit/ee14a43770ee23979e939338a39043dbd2ef201e))

## [0.3.0](https://github.com/metril/immich-hoarder/compare/v0.2.1...v0.3.0) (2026-10-26)


### Features

* **ui:** darkroom tokens, fonts and ui primitives ([5d638a5](https://github.com/metril/immich-hoarder/commit/5d638a5467ca5d006d4f250354ea31d19cb8e3b2))
* **ui:** live active-jobs badge in navigation ([f671045](https://github.com/metril/immich-hoarder/commit/f67104510b885277a994b09041fc166e1fba2446))
* **ui:** redesign dashboard and jobs ([e29dd15](https://github.com/metril/immich-hoarder/commit/e29dd1551c6a9826073e9c00cac470b4d522e36c))
* **ui:** redesign shell, navigation and login ([3755e6d](https://github.com/metril/immich-hoarder/commit/3755e6d9b1be4d799f95a9e5b2bd1d8c9ed058ce))
* **ui:** redesign sources ([b4bb0d4](https://github.com/metril/immich-hoarder/commit/b4bb0d461af50d40a712c7305801710e3941c8c8))
* **ui:** redesign targets, credentials, keys, users and settings ([99a3159](https://github.com/metril/immich-hoarder/commit/99a31593abf679de2fcf1cd79f6214f9dea47e25))


### Bug Fixes

* **ui:** accessible dropdown menus and review fixes ([2a207b2](https://github.com/metril/immich-hoarder/commit/2a207b29fbba0469ffcd6180deaf278fce8ed217))
* **ui:** switch, table alignment and mobile polish ([b39e10c](https://github.com/metril/immich-hoarder/commit/b39e10c5d6d9a510b0354daefb01e18b3eee896a))
* **ui:** visual polish and refreshed screenshots ([f5d83ca](https://github.com/metril/immich-hoarder/commit/f5d83caeab18d57673e825e63277d976eb8884e3))

## [0.2.1](https://github.com/metril/immich-hoarder/compare/v0.2.0...v0.2.1) (2026-10-26)


### Bug Fixes

* **a11y:** single h1 per page; topbar title is not a heading ([c9dc935](https://github.com/metril/immich-hoarder/commit/c9dc9355c25f67b9a7b7f1895f18f5603d92e32a))
* **frontend:** type-check e2e specs via tsconfig.node instead of default project ([4654d68](https://github.com/metril/immich-hoarder/commit/4654d68a720d6f4327551cb6ff276c0e80ea4ebb))

## [0.2.0](https://github.com/metril/immich-hoarder/compare/v0.1.0...v0.2.0) (2026-10-26)


### Features

* **admin:** add YAML config export and import ([c605e96](https://github.com/metril/immich-hoarder/commit/c605e9676342f3a073d6be6a863a5330d2aae975))
* **api:** add CRUD for targets, credentials, sources, shares, keys, users, settings ([10d3b94](https://github.com/metril/immich-hoarder/commit/10d3b94ded7983adf7853c5017b223881de38cb6))
* **api:** add Immich target test and album listing ([f3c47a9](https://github.com/metril/immich-hoarder/commit/f3c47a9d74a3ae32c36e151d01e44a46501f7dcc))
* **api:** add jobs, run, ad-hoc rip, cancel and retry endpoints ([efcacd4](https://github.com/metril/immich-hoarder/commit/efcacd4e66418033b5930cdef66a1b40af69d5a8))
* **api:** add live job and dashboard SSE streams ([c6ef4ff](https://github.com/metril/immich-hoarder/commit/c6ef4ff418a4efd00d6bcc092edcb1c2c555ffd9))
* **api:** add recent uploads and thumbnail proxy ([2dd80b6](https://github.com/metril/immich-hoarder/commit/2dd80b6278741d54b3119c92b114b21d6279a334))
* **api:** add source can_use, single-query access flags, drop dead scope check ([a9fa060](https://github.com/metril/immich-hoarder/commit/a9fa060767d5e142c375057d1c2190c8807ea355))
* **api:** type responses, enrich live events, add user directory and job phase ([1681ab2](https://github.com/metril/immich-hoarder/commit/1681ab23561ea1d4fe3c5647eb41985be0e6741a))
* **auth:** add OIDC, bearer JWT and API-key authentication ([a6cd9b8](https://github.com/metril/immich-hoarder/commit/a6cd9b8df2fbfb3b0e2200407a9a7ca6cbd41482))
* **auth:** add ownership and sharing authorization ([f9ef5c3](https://github.com/metril/immich-hoarder/commit/f9ef5c35256fd4a0948593199e07bd9831d5703e))
* **config:** describe settings, IH_DATABASE_URL_FILE, generated config reference ([2ba4c37](https://github.com/metril/immich-hoarder/commit/2ba4c375046874aafa8a650977d9d73c72f25191))
* **core:** add encrypted secret box ([f17b7a5](https://github.com/metril/immich-hoarder/commit/f17b7a52b88b04ec3a27e934493b38cf51eb1a13))
* **db:** add schema, SQLite tuning and initial migration ([ad19323](https://github.com/metril/immich-hoarder/commit/ad19323308261a11d1704a77e193f7ff245ffe52))
* **deploy:** production Traefik compose with postgres and gluetun overrides ([106c1e1](https://github.com/metril/immich-hoarder/commit/106c1e11b6ec18c2d5a87acd769c2aeb2a1ab869))
* **immich:** add sync Immich API client with retries ([e626aff](https://github.com/metril/immich-hoarder/commit/e626aff3d7b35e4212c3214f645d461d0cf9b9e4))
* **rip:** add album template rendering and resolver ([d34b8d9](https://github.com/metril/immich-hoarder/commit/d34b8d9a3d100fb4ee432b1dea3eb55c43859e27))
* **rip:** add dry-run preview endpoint and CLI runner ([cb91543](https://github.com/metril/immich-hoarder/commit/cb91543ca504adfa74dfbb1eecb0f5e19a2f5788))
* **rip:** add filter spec, backfill mapping and rip settings ([af401e8](https://github.com/metril/immich-hoarder/commit/af401e839f8d09e5227e538ccb5f1d24d8065fad))
* **rip:** add gallery-dl runner with own archive and hooks ([dbae541](https://github.com/metril/immich-hoarder/commit/dbae5419742f0e4bbf6fbb7f6a839be6d629aaf8))
* **rip:** add media analysis and perceptual hash helpers ([c6cec05](https://github.com/metril/immich-hoarder/commit/c6cec05bd2cec4342c69d65c9161afa2fbe400c3))
* **rip:** add per-target dedupe store with multi-index pHash ([a0dedfe](https://github.com/metril/immich-hoarder/commit/a0dedfea0276847741b88cc8f9f87f548180bdb9))
* **rip:** add rip pipeline with dedupe, linking and back-pressure ([1f9a4b3](https://github.com/metril/immich-hoarder/commit/1f9a4b384fe3788ad52dd608e013fdc9a1bcabcc))
* **rip:** validate URLs via gallery-dl and allow-list source options ([7025493](https://github.com/metril/immich-hoarder/commit/7025493d81c87a3fea676159240f45d71c3f9dad))
* **runtime:** add event bus and batched job writer ([338b1a2](https://github.com/metril/immich-hoarder/commit/338b1a218b3975ac68a3f9266cc63d9292da5f00))
* **runtime:** add Prometheus metrics, readiness and API-key bearer ([8a8e8a2](https://github.com/metril/immich-hoarder/commit/8a8e8a27bb3cb3cd2c63af95bddbcc7c4bdbd937))
* **runtime:** add retention, backups and admin maintenance ([358dd40](https://github.com/metril/immich-hoarder/commit/358dd40fc2ed6a43b05bf2f74c0d27cf69f7ceba))
* **runtime:** add runtime and notify settings with strict keys ([8bc0eac](https://github.com/metril/immich-hoarder/commit/8bc0eac4920c5ab0e06e67990b8485ceb2b6c937))
* **runtime:** add worker processes and job supervisor ([283cf1e](https://github.com/metril/immich-hoarder/commit/283cf1e33c7bc4c1ee60fe580bd9cec34accb3bc))
* **runtime:** schedule sources with cron triggers ([3d57e6e](https://github.com/metril/immich-hoarder/commit/3d57e6ed57fa9e7a2d84f6be49fc174c753dacf6))
* **runtime:** send job notifications via apprise ([2d6e02e](https://github.com/metril/immich-hoarder/commit/2d6e02e5bbde4cae39db7cd67b338e49854d8077))
* **web:** add API keys and users pages ([2ebec8f](https://github.com/metril/immich-hoarder/commit/2ebec8f01adf9887c5b14048848387e3ea8fbb4d))
* **web:** add app shell with auth gate, role-aware nav, theme, palette and shortcuts ([4d99bb7](https://github.com/metril/immich-hoarder/commit/4d99bb75963e50154249afeccf18818c527ee15a))
* **web:** add generated typed API client with CSRF and error mapping ([9269759](https://github.com/metril/immich-hoarder/commit/9269759b1129d5f1302f8fbf0aa74caa26e8cba1))
* **web:** add jobs list and live job detail ([1b8ee73](https://github.com/metril/immich-hoarder/commit/1b8ee7303de9345ff87a24a6c0c8334925c610da))
* **web:** add live dashboard with recent uploads gallery ([e3d5460](https://github.com/metril/immich-hoarder/commit/e3d5460d158f5d8663cf400b1b006c823d0f38b6))
* **web:** add settings page with admin backup, prune and config transfer ([6c20876](https://github.com/metril/immich-hoarder/commit/6c208768b77dda396babcba08d7479f1dce210dd))
* **web:** add source editor with filter builder, cron helper, backfill and notify ([ef36d0c](https://github.com/metril/immich-hoarder/commit/ef36d0cdb02de3a8e30d4d78378c379ce5f85f3f))
* **web:** add sources page with dry-run preview and run controls ([df56989](https://github.com/metril/immich-hoarder/commit/df569894408826ea6c335ba221d8092b9492c6f1))
* **web:** add SSE live layer feeding the query cache ([8e61506](https://github.com/metril/immich-hoarder/commit/8e61506a26bf75eab6282675e5c7971b9d7742cf))
* **web:** add targets and credentials pages ([2a2d27c](https://github.com/metril/immich-hoarder/commit/2a2d27c3315c0da1c55f335cba19fd3f67544dff))
* **web:** add virtual table, cursor lists, api forms, sharing and secret inputs ([880dcd5](https://github.com/metril/immich-hoarder/commit/880dcd506779f17a6b1836ae5098e43035ba5c61))
* **web:** add virtualized job log viewer with filter, search and download ([173ccd7](https://github.com/metril/immich-hoarder/commit/173ccd797a1ce4e594674c31e07f59128c1b2e3c))
* **web:** scaffold frontend toolchain, test harness and build budgets ([69f8e6d](https://github.com/metril/immich-hoarder/commit/69f8e6df158a6e4cf8722ef0ab1d526c64ab2f7c))
* **web:** serve SPA with precompressed immutable assets and CSP ([554f621](https://github.com/metril/immich-hoarder/commit/554f6213203f84c740c885139bbe2f4a5343e850))


### Bug Fixes

* address final review findings ([3784cb2](https://github.com/metril/immich-hoarder/commit/3784cb2aa58f7f0310169a8894da0950d091eaee))
* **admin:** export share user principals by sub for portability ([5bb90d4](https://github.com/metril/immich-hoarder/commit/5bb90d48bd38c3645b291e5b8deb832705805150))
* **admin:** order share import before sources and protect target url credentials ([e8de0b5](https://github.com/metril/immich-hoarder/commit/e8de0b5ff473019f650b5b1f14c3c070f6ebb805))
* **api:** drop email from user directory, tolerate invalid stored settings ([8cf6945](https://github.com/metril/immich-hoarder/commit/8cf69454f8c480d190e7c48e1bf18f7897149249))
* **api:** force private ad-hoc rips, clean up on enqueue failure, index and order job lists ([a6510d0](https://github.com/metril/immich-hoarder/commit/a6510d02254e7653c76831bedc6bdd1130762a1b))
* **api:** handle malformed Immich responses and auth failures on albums ([efede4f](https://github.com/metril/immich-hoarder/commit/efede4fdcca5e65ede139f79fe0e483e2c8a9beb))
* **api:** harden thumbnail proxy content types, limits and id handling ([1ebf6c8](https://github.com/metril/immich-hoarder/commit/1ebf6c85601a100fc767c38696202baaff084074))
* **api:** paginate api keys, add key scopes, guard last admin and disabled owners ([153336f](https://github.com/metril/immich-hoarder/commit/153336f66d33912c47b39c0712d28988d336cf6c))
* **api:** recheck stream visibility, cap streams, handle gaps and replay shape ([7de5ab0](https://github.com/metril/immich-hoarder/commit/7de5ab0a62b9cda5c7d7336672224eea39260f74))
* **auth:** hide existence on owner-only ops and tighten scope bypass ([2a3163c](https://github.com/metril/immich-hoarder/commit/2a3163c78de080bbc03759c0dd649100999bec81))
* **auth:** persist denied-login groups, clear session, tolerate non-signing JWKS keys ([e257caf](https://github.com/metril/immich-hoarder/commit/e257caf5f0f3410030b9e9179e440da52309cbd9))
* **build:** use secret file for session secret, drop trusted_proxies setting ([be688e4](https://github.com/metril/immich-hoarder/commit/be688e47201b1fb8cf3db8c0f30dc74979105cc5))
* clear Plan 1 deferred minors ([a9618df](https://github.com/metril/immich-hoarder/commit/a9618df3f0a5c125aece504fa1690792c5132af6))
* clear Plan 2 deferred minors ([16947a9](https://github.com/metril/immich-hoarder/commit/16947a9ad0ff6bf054201addae13c1165869703e))
* **core:** enforce minimum secret length and tighten crypto tests ([eebfc69](https://github.com/metril/immich-hoarder/commit/eebfc6984106787dc2ca5cded024f8e31c1f44e2))
* **db:** add FK delete policies, pragma tuning and postgres URL normalisation ([c4564ae](https://github.com/metril/immich-hoarder/commit/c4564ae4dc11b21fca62366db92f576555010ae2))
* **deploy:** gluetun health dependency, tie scratch size to setting default ([94c9169](https://github.com/metril/immich-hoarder/commit/94c9169ef87dac81be60fc0bdf4a2ab22ee774ae))
* finalize cooperative cancels on stop as interrupted; atomic source delete guard ([f37bda4](https://github.com/metril/immich-hoarder/commit/f37bda436762718872d7b9bac482db526010ab8f))
* harden job runtime shutdown, recovery, readiness and CI ([6e3a444](https://github.com/metril/immich-hoarder/commit/6e3a4440d9bc4608aa3c9bb903194dccfc28153b))
* harden rate-limit options and /rip cancel handling ([64d5184](https://github.com/metril/immich-hoarder/commit/64d5184924528281be811064dc011e4422f024c0))
* **immich:** require identity encoding for thumbnails; test id canonicalisation ([d529db3](https://github.com/metril/immich-hoarder/commit/d529db381d42f54740d453e1f7fb402f8c753ff6))
* **immich:** restrict retries to safe cases and handle empty inputs ([3e33607](https://github.com/metril/immich-hoarder/commit/3e33607db4a8832a5fbc1c905dee2abaa9549431))
* keep savepoint-scoped user upsert and renew CSRF cookie with session ([e101f33](https://github.com/metril/immich-hoarder/commit/e101f3315503af377a78c132db2005a15612c415))
* **logging:** bound redaction cost, mask bearer and API keys, hide database_url repr ([b4d649d](https://github.com/metril/immich-hoarder/commit/b4d649d66b43fbe930281e222b377e99db74dcb8))
* **logging:** make query-param redaction linear ([0af5976](https://github.com/metril/immich-hoarder/commit/0af5976a881be0558138d1b1f0dd3869d67335b4))
* **logging:** redact secrets in JSON log output ([02ea16f](https://github.com/metril/immich-hoarder/commit/02ea16fd3e3c08fda596293cb01e9d0a0241b2a0))
* **rip:** accept MPO, drop thread-unsafe warnings filter, apply EXIF orientation ([3e98c66](https://github.com/metril/immich-hoarder/commit/3e98c66dac158e748c4eb691ba4d9362af304877))
* **rip:** close credential eval, proxy SSRF and path escape in runner ([3379781](https://github.com/metril/immich-hoarder/commit/3379781b3498a38e6000eed02bdb31f452424f67))
* **rip:** do not record items whose album link failed; cover corrupt images ([1e17a76](https://github.com/metril/immich-hoarder/commit/1e17a7601a003cc7be3a45eee176b3c768acac27))
* **rip:** filter pHash distance in SQL, require source_id, map ssl param ([06ca84d](https://github.com/metril/immich-hoarder/commit/06ca84dd7d3425488d2c75f7c04d147142c9ea67))
* **rip:** harden album rendering, template validation and resolver cache ([d36b05e](https://github.com/metril/immich-hoarder/commit/d36b05e351b40d237cbdf94e9d47c3d37427521f))
* **rip:** harden preview failures, cleanup, concurrency and scratch sweep ([ce09225](https://github.com/metril/immich-hoarder/commit/ce0922527744a2b465bc1610e1d6f7e08c075271))
* **rip:** harden URL host validation against SSRF bypasses ([7196afb](https://github.com/metril/immich-hoarder/commit/7196afbd0107c8efff95e1d871ffd55fa02bdb98))
* **rip:** read back deleted-in-immich records, tighten job status and queued item handling ([bd32b95](https://github.com/metril/immich-hoarder/commit/bd32b95bf3dda1be0924b4a56599b80697d45c7f))
* **rip:** scrub credential secrets from job logs and preview errors ([62752c4](https://github.com/metril/immich-hoarder/commit/62752c43f12d880bf821f0ddb4af0eab25d145fe))
* **rip:** scrub file URL used in descriptions and events ([0f6051a](https://github.com/metril/immich-hoarder/commit/0f6051ac7d332088e7bc6d45913acc03ec588cb5))
* **rip:** scrub pipeline error logs and nested credential values ([3a19225](https://github.com/metril/immich-hoarder/commit/3a1922517b2a134f0544fb4c89917c9cec7893de))
* **rip:** split gallery-dl options, enforce since window and validate filter bounds ([6d9b8dd](https://github.com/metril/immich-hoarder/commit/6d9b8dd31f7fc4d403cd24ca62968b3e6148b09c))
* **runtime:** block private hosts in apprise credentials and silence apprise logger ([63972e1](https://github.com/metril/immich-hoarder/commit/63972e1fbeba381934a250e34dc3fb7b1dacf07e))
* **runtime:** close supervisor races, atomic enqueue, exit-code crash detection ([8c04d88](https://github.com/metril/immich-hoarder/commit/8c04d8835235cf62baafcc0bee0fe719462a3530))
* **runtime:** drain ipc bridge on stop and back off writer restarts ([9b11d14](https://github.com/metril/immich-hoarder/commit/9b11d14414eaa615bb565f685d4c1ec07cf3997f))
* **runtime:** drop closed process handle after exit ([a1941fd](https://github.com/metril/immich-hoarder/commit/a1941fdf728a8da34b0b8bb813ba3abe33f965bd))
* **runtime:** enforce notify SSRF guard at connect time ([d3a3263](https://github.com/metril/immich-hoarder/commit/d3a3263c07decdbdd2e0507c006bce0e56e23b6a))
* **runtime:** feed metrics from lossless writer observer ([db73b47](https://github.com/metril/immich-hoarder/commit/db73b47255a7d5858400e120c6f7a7fb5189df07))
* **runtime:** guard every worker liveness check against closed processes ([93abf62](https://github.com/metril/immich-hoarder/commit/93abf6296792ef89fe21a01d76f8f817f5679de4))
* **runtime:** guard notify sends at getaddrinfo to cover raw-socket plugins ([1620dcc](https://github.com/metril/immich-hoarder/commit/1620dcc787c2e7dc39510e896e41867e6dbcaa23))
* **runtime:** harden maintenance prune, backup and rescheduling ([82b275e](https://github.com/metril/immich-hoarder/commit/82b275e821c4ac2096251a6047b8260302b1d8ed))
* **runtime:** isolate poisoned writer messages and harden bus and bridge ([0f75228](https://github.com/metril/immich-hoarder/commit/0f75228405dd23b9abd2b980f0b7ef021e69add3))
* **runtime:** thread-safe apprise log filter, redact validation errors, bound cancel_grace_s ([001e171](https://github.com/metril/immich-hoarder/commit/001e17160fb6f8281a998606f6459b0eff3fb0ea))
* **runtime:** use croniter trigger and harden scheduler sync ([8d5bf78](https://github.com/metril/immich-hoarder/commit/8d5bf780cbed3632a9fcc374e71f149b519629f1))
* **web:** 404 for dot-prefixed path segments ([617fcc8](https://github.com/metril/immich-hoarder/commit/617fcc87cb15f9fb92e0d5ab9269e03c7bcb4956))
* **web:** align source filters with FilterSpec, add can_use, load all picker pages, guard lazy chunks ([8875ef1](https://github.com/metril/immich-hoarder/commit/8875ef12ca2f63c9e17e16ebd660387652a8f70e))
* **web:** dashboard loading/error states, deduped job tiles and gallery tests ([49c00a4](https://github.com/metril/immich-hoarder/commit/49c00a470dbc5b7c258de73c27ab4e865679e26d))
* **web:** drop unused import ([089bd73](https://github.com/metril/immich-hoarder/commit/089bd736a4bdbbdb47abbfab89c104e2859cc444))
* **web:** dry-run unsaved drafts, preview timeout, accessible rip errors ([7408fad](https://github.com/metril/immich-hoarder/commit/7408fadec7842a1102dee73e6bd5dd63036ae713))
* **web:** gate target and credential actions by can_edit and ownership ([5e76312](https://github.com/metril/immich-hoarder/commit/5e76312f88f466594c3431576aae8dcaa82045e0))
* **web:** harden admin guard, sheet and help focus handling, preload error reload and theme sync ([6704c65](https://github.com/metril/immich-hoarder/commit/6704c65cf7bdbef18dc23e5b384b4917951fbda7))
* **web:** harden API error parsing and cover CSRF on all mutating methods ([0677527](https://github.com/metril/immich-hoarder/commit/06775279a1f59f41ff5b4957393d2bad690c87e5))
* **web:** harden log viewer buffer, a11y, download and tabs ([1b9a238](https://github.com/metril/immich-hoarder/commit/1b9a2387597c7040baea63a1d3e3fa9ecbbe0b6e))
* **web:** harden shared blocks, add share principal names ([8ec8a11](https://github.com/metril/immich-hoarder/commit/8ec8a1108a6a510f819c728967f1e70caeba5259))
* **web:** harden SPA route against NUL paths, API method 405s and header gaps ([7099d57](https://github.com/metril/immich-hoarder/commit/7099d57f2b6748fc391d08d4ff2dcd0dbed5158a))
* **web:** invalidate jobs on unknown or terminal status, flush on unmount, cap rejected reconnects ([f692355](https://github.com/metril/immich-hoarder/commit/f692355d370d9af5e2fcbf8ee87de3268ccd496a))
* **web:** palette new target, run gating, source invalidation, typed credential form, a11y contrast, stable tests ([00676e7](https://github.com/metril/immich-hoarder/commit/00676e78c61037c217261e5885d4d1337213912f))
* **web:** reconcile terminal jobs, link 409 active job, thumbnail fallback ([e10d9cb](https://github.com/metril/immich-hoarder/commit/e10d9cb5a4b23fbb493d0875fa43b427e673a1ff))
* **web:** settings list errors, rate limit row errors, responsive backups, tab keyboard nav ([0947b39](https://github.com/metril/immich-hoarder/commit/0947b397b25c865d237174b1540da481d5c8b567))
* **web:** tighten scaffold lint globals, script entry detection and EventSource mock ([8ed47d0](https://github.com/metril/immich-hoarder/commit/8ed47d084318e808252e15b52e4a1090fc3b956e))
* **web:** type API key scopes in openapi, lock key reveal dialog, validate expiry ([e522de7](https://github.com/metril/immich-hoarder/commit/e522de72b395683f284f3de4a861a57a34496197))
