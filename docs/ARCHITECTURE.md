# LocalScope Architecture --- Semrush-Specific Build

## 1. Purpose

LocalScope is a Semrush-specific reverse-proxy application built with
FastAPI.

Its central design is:

``` text
Browser
   ↓
LocalScope
   ↓
Selected server-side Semrush account
   ↓
Semrush
   ↓
LocalScope rewrites the response
   ↓
Browser
```

The browser talks to LocalScope rather than directly carrying the
administrator-supplied Semrush authentication cookie.

LocalScope keeps account cookies server-side, assigns an account to each
LocalScope browser session, injects the selected cookie only for Semrush
hosts, forwards requests upstream, synchronizes refreshed cookies,
rewrites content back onto the LocalScope origin, and blocks configured
sensitive account-management operations.

This version intentionally targets `https://www.semrush.com`.

------------------------------------------------------------------------

## 2. High-level components

``` text
app/main.py
│
├── accounts/
│   ├── account model
│   ├── account selection
│   ├── health
│   ├── cookie synchronization
│   └── session cleanup
│
├── storage/
│   └── SQLite persistence
│
├── security/
│   └── Fernet cookie encryption
│
├── policies/
│   └── access restrictions
│
├── proxy/
│   ├── target URL construction
│   ├── HTTP forwarding
│   ├── origin/header rewriting
│   ├── URL mapping
│   ├── HTML/CSS/manifest rewriting
│   └── redirect handling
│
└── inspectors/
    └── streaming-response classification
```

`main.py` is the orchestration layer. The smaller modules contain
focused logic so that request forwarding, account management,
persistence, encryption, and rewriting do not all live in one file.

------------------------------------------------------------------------

## 3. `app/main.py`

### Responsibility

`main.py` creates the FastAPI application and connects all subsystems.

It is responsible for:

-   application startup/shutdown;
-   the shared `httpx.AsyncClient`;
-   the fixed Semrush target;
-   database initialization and account loading;
-   LocalScope browser sessions;
-   admin authentication;
-   account-management API routes;
-   root and `/proxy/` forwarding routes;
-   `/proxy-external/` forwarding;
-   WebSocket forwarding;
-   access-policy enforcement;
-   response rewriting and cookie synchronization.

### Startup: `lifespan()`

At startup LocalScope:

1.  creates one shared `httpx.AsyncClient` with redirects disabled and a
    30-second timeout;
2.  sets the target to `https://www.semrush.com`;
3.  initializes SQLite;
4.  loads stored accounts;
5.  initializes in-memory session/account-assignment structures;
6.  initializes the in-memory admin-session set;
7.  reads admin username/password from the environment;
8.  refuses startup if either admin credential is missing.

At shutdown the shared HTTP client is closed.

### Important application state

The application keeps several runtime values under `app.state`:

``` text
http_client
target
accounts
account_assignments
next_account_index
session_last_seen
admin_sessions
admin_username
admin_password
```

The database persists account records, but browser assignments and admin
sessions are currently process-memory state.

### `localscope_session_middleware()`

This middleware manages ordinary proxied browser sessions.

Internal routes beginning with `/__localscope/` do not create these user
sessions.

For ordinary traffic:

1.  read `localscope_session`;
2.  create a UUID if missing;
3.  store the ID on `request.state`;
4.  update its last-seen timestamp;
5.  process the request;
6.  set an HTTP-only, `SameSite=Lax` session cookie if the browser did
    not already have one.

This LocalScope cookie identifies the browser to the account selector.
It is not the Semrush authentication cookie.

### `handle_proxy_request()`

This is the central HTTP proxy orchestration function.

Its flow is:

``` text
Incoming request
    ↓
Read body + headers
    ↓
Get LocalScope session ID
    ↓
Select assigned Semrush account
    ↓
No account? → 503 unavailable.html
    ↓
Remove browser Cookie header
    ↓
If upstream host is semrush.com/*.semrush.com:
inject selected account.cookie
    ↓
Rewrite Origin/Referer-style headers
    ↓
Open upstream response with httpx
    ↓
Update account health when relevant
    ↓
Streaming?
   ↙          ↘
 yes          no
 ↓             ↓
stream        read body
response      + close upstream
 ↓             ↓
sync          sync Set-Cookie
Set-Cookie     ↓
              rewrite HTML/CSS/manifest
              ↓
              rewrite redirect Location
              ↓
              return Response
```

A critical security decision is that account cookies are injected only
when the upstream hostname is `semrush.com` or a subdomain ending in
`.semrush.com`.

External resources are still proxyable, but the Semrush account cookie
is removed for them.

### Document detection

`is_document_request()` uses `Sec-Fetch-Dest` and `Accept` to
distinguish browser document navigation from script/style/image/API
traffic.

That distinction matters because broad page restrictions should block
actual navigation without unnecessarily blocking unrelated assets or
APIs that happen to contain a sensitive word.

### Blocked responses

`blocked_response()` returns:

-   JSON HTTP 403 for API-like requests;
-   `blocked.html` HTTP 403 for normal browser page navigation.

### Proxy routes

The application supports three main HTTP entry patterns:

``` text
/
 /{path:path}
 /proxy/{path:path}
```

These map onto the configured Semrush base URL.

It also supports:

``` text
/proxy-external/{scheme}/{encoded_netloc}/{path:path}
```

for resources that belong to another origin.

### Admin routes

Internal admin URLs live under:

``` text
/__localscope/
```

The admin panel uses a separate cookie:

``` text
localscope_admin_session
```

Admin sessions are random URL-safe tokens stored in
`app.state.admin_sessions`.

Credentials are compared with `secrets.compare_digest()`.

The admin cookie is:

-   HTTP-only;
-   `SameSite=Strict`;
-   scoped to `/__localscope`.

### Account routes

The admin API supports:

``` text
POST   /__localscope/api/accounts
GET    /__localscope/api/accounts
POST   /__localscope/api/accounts/{id}/enable
POST   /__localscope/api/accounts/{id}/disable
DELETE /__localscope/api/accounts/{id}
```

Adding an account creates an in-memory `Account` and persists it
encrypted.

Enabling an account persists `enabled=True` and performs an explicit
health check.

Disabling persists `enabled=False`.

Deleting removes the account from memory and SQLite and removes any
browser assignments that referenced it.

### WebSocket route

``` text
/ws-proxy/{encoded_url:path}
```

decodes the upstream WebSocket URL, determines an upstream origin,
forwards requested subprotocols, connects with the `websockets` client,
accepts the browser connection, and runs two concurrent loops:

``` text
browser → upstream
upstream → browser
```

Both text and binary frames are supported.

------------------------------------------------------------------------

## 4. `app/accounts/`

### `models.py`

Defines the `Account` dataclass:

``` text
id
name
cookie
enabled
health
last_status_code
```

`create_account()` creates a UUID-backed account that starts:

``` text
enabled = False
health = "unknown"
last_status_code = None
```

Starting disabled prevents a newly entered cookie from immediately
receiving user traffic before the administrator enables it.

### `selector.py`

Contains sticky account assignment and round-robin selection.

`select_account_for_session()` first checks whether the LocalScope
session already has an assigned account.

The existing assignment remains valid only if the account:

-   still exists;
-   is enabled;
-   is not marked `expired`.

Otherwise the assignment is removed.

For a new assignment, the function builds a list of enabled, non-expired
accounts and uses `next_account_index` to choose them in round-robin
order.

The selected account ID is stored in:

``` text
app.state.account_assignments[session_id]
```

This creates sticky sessions while distributing new sessions across
available accounts.

### `session_cleanup.py`

Defines:

``` text
SESSION_TIMEOUT_SECONDS = 15 * 60
```

`cleanup_stale_sessions()` removes session last-seen records and account
assignments that have been inactive for more than 15 minutes.

In the current application this cleanup is triggered when the
administrator lists accounts.

### `health_check.py`

Performs an explicit Semrush-specific account check against:

``` text
https://www.semrush.com/projects/api/me
```

It sends the stored account cookie and expects:

``` text
200      → healthy
401/403  → expired
other    → error
network failure → error, no status code
```

This function is used when an account is enabled.

### `health.py`

Updates health opportunistically from normal proxied traffic.

It only reacts when the target URL contains:

``` text
/projects/api/me
```

Then:

``` text
2xx      → healthy
401/403  → expired
other    → error
```

This lets normal application traffic update account health without a
separate health request every time.

### `cookie_sync.py`

Keeps stored server-side account cookies synchronized with Semrush.

Important functions:

-   `parse_cookie_header()` converts a Cookie header into a dictionary;
-   `build_cookie_header()` reconstructs a Cookie header;
-   `update_account_cookie()` merges upstream `Set-Cookie` headers into
    the current account cookie.

If a `Set-Cookie` contains `Max-Age=0`, that cookie is removed.

After synchronization, `main.py` persists the new encrypted cookie
through `storage/database.py`.

------------------------------------------------------------------------

## 5. `app/security/cookie_crypto.py`

This module protects stored account cookies with Fernet symmetric
authenticated encryption.

### `get_cipher()`

Reads:

``` text
LOCALSCOPE_ENCRYPTION_KEY
```

and constructs a `Fernet` cipher.

Startup/account loading cannot successfully decrypt stored cookies if
the key has changed.

### `encrypt_cookie()`

Converts the raw cookie to UTF-8 bytes, encrypts it, and returns a
text-safe encrypted token.

### `decrypt_cookie()`

Decrypts the stored token.

An invalid key/token becomes:

``` text
RuntimeError: Stored account cookie could not be decrypted
```

This behavior is intentional: silently treating undecryptable
authentication material as valid would be unsafe.

------------------------------------------------------------------------

## 6. `app/storage/database.py`

LocalScope uses SQLite:

``` text
DATABASE_PATH = "localscope.db"
```

### Schema

The current table is:

``` sql
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cookie TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0
)
```

`health` and `last_status_code` are runtime account fields and are not
currently persisted in this table.

### Functions

`get_connection()` creates a SQLite connection with `sqlite3.Row` rows.

`initialize_database()` creates the table when necessary.

`save_account()` encrypts the account cookie before insertion.

`load_accounts()` reads records and decrypts each cookie into an
`Account`.

`update_account_enabled()` persists the enabled flag.

`update_account_cookie()` encrypts the refreshed cookie before updating
the row.

`delete_account_from_database()` removes an account.

### Why the database is not distributed

`localscope.db` contains real account records and encrypted
authentication material. Encryption is defense in depth, not a reason to
publish the database.

A fresh installation creates its own database automatically.

------------------------------------------------------------------------

## 7. `app/policies/access_rules.py`

This file centralizes LocalScope's Semrush access policy.

It contains four main configuration groups:

### `BLOCKED_PAGE_KEYWORDS`

Used for broad browser-page navigation restrictions, including terms
related to:

``` text
logout/login/signup
account/profile/settings
billing/payment
subscription/pricing/upgrade
password/security
team/member/invite
```

### `MUTATING_METHODS`

``` text
POST
PUT
PATCH
DELETE
```

### `SENSITIVE_ACTION_KEYWORDS`

Used to detect mutating operations related to account, security,
billing, subscription, membership, deletion, and similar sensitive
operations.

### UI configuration

`HIDDEN_LINK_PATTERNS` hides known restricted links from the proxied UI.

`HIDDEN_SELECTORS` is available for explicit selectors when a sensitive
UI element cannot be identified by its link.

`HEADER_MESSAGE` contains the LocalScope management notice inserted into
proxied HTML.

### Enforcement functions

`normalize_path()` normalizes and lowercases a path.

`path_contains_keyword()` compares whole path segments rather than
arbitrary substrings.

`is_blocked_page()` applies broad page rules only to GET/HEAD.

`is_blocked_action()` applies sensitive-action rules only to mutating
methods.

`is_access_blocked()` combines both rules:

-   broad restrictions require an actual document navigation;
-   sensitive mutating operations are blocked regardless of whether they
    came from fetch/XHR or navigation.

Backend enforcement is the security boundary. Hiding links in HTML is
not considered sufficient enforcement.

------------------------------------------------------------------------

## 8. `app/proxy/`

### `target_config.py`

Defines the upstream target abstraction and `build_target_url()`.

For this build the active target is created in `main.py` as:

``` text
https://www.semrush.com
```

`build_target_url()` combines:

-   base scheme;
-   base host;
-   base path;
-   requested path;
-   query string.

### `proxy_engine.py`

Contains low-level HTTP forwarding.

Its responsibilities include preparing request/response headers,
forwarding normal requests, and opening upstream responses for
streaming.

`main.py` deliberately uses `open_stream_response()` before deciding
whether the response must remain streamed. This prevents SSE-style
responses from being buffered like ordinary content.

### `origin_rewriter.py`

Rewrites browser-origin-related headers so upstream requests make sense
to the target origin rather than the LocalScope localhost origin.

This is important because proxied browser requests otherwise contain
LocalScope-origin values that upstream applications may reject or
interpret incorrectly.

### `url_mapper.py`

Provides the canonical mapping between upstream URLs and LocalScope
routes.

For URLs on the configured Semrush origin:

``` text
https://www.semrush.com/path?q=1
```

the mapper returns a LocalScope-relative path:

``` text
/path?q=1
```

For another origin it creates:

``` text
/proxy-external/{scheme}/{encoded-host}/{path}
```

This preserves the original external host so LocalScope can reconstruct
the upstream URL later.

`build_external_target_url()` performs the reverse transformation for
incoming `/proxy-external/` requests.

### `redirect_rewriter.py`

Handles upstream HTTP `Location` headers.

It resolves relative redirect locations against the current upstream URL
and then sends the absolute result through the central URL mapper.

Without this, a Semrush redirect could send the browser away from
LocalScope to the real upstream domain.

### `html_rewriter.py`

Rewrites server-returned HTML so resources and navigation continue
through LocalScope.

The current implementation handles URL-bearing elements such as links,
scripts, images, forms, iframes, sources, video, audio, and `srcset`.

It also:

-   removes integrity attributes where rewritten resource URLs would
    invalidate SRI;
-   removes CSP meta tags that would conflict with localhost rewriting;
-   injects `runtime_proxy.js` before site scripts when possible;
-   injects the LocalScope access UI script;
-   hides configured restricted links/selectors;
-   inserts the LocalScope management banner;
-   observes DOM mutations so dynamically inserted UI is processed too.

The runtime script receives the real `upstream_url` through a data
attribute.

### `css_rewriter.py`

Rewrites URLs referenced from CSS so fonts, images, imports, and other
CSS resources remain reachable through LocalScope instead of escaping to
their upstream origins.

### `manifest_rewriter.py`

Rewrites URL fields inside web-app manifest content using the same
LocalScope URL mapping strategy.

This is needed because manifests can contain icons and other URLs
independently of the HTML document.

### `cookie_rewriter.py`

Contains logic for rewriting upstream `Set-Cookie` attributes for a
LocalScope host context.

The active account-cookie design in `main.py` primarily consumes Semrush
`Set-Cookie` values server-side through `cookie_sync.py` rather than
exposing the account cookie to the browser. Keep this module because it
belongs to the proxy's cookie-rewriting support, but the server-side
account-cookie store is the key authentication mechanism in the current
build.

### Why there are multiple rewriters

A single HTML rewrite is not enough.

Web applications can refer to upstream URLs through:

``` text
HTML attributes
CSS url(...)
HTTP Location headers
web manifests
runtime JavaScript
Origin/Referer headers
WebSockets
```

Each mechanism occurs at a different layer and therefore has its own
focused handling.

------------------------------------------------------------------------

## 9. `app/inspectors/stream_classifier.py`

The original project contained a larger network-inspection subsystem.
After cleanup, only the useful streaming classifier remains.

`is_streaming_response()` currently identifies:

``` text
text/event-stream
```

as streaming.

This prevents SSE responses from being fully buffered before they are
returned to the browser.

The `inspectors` directory name is historical; the remaining module is
still functionally useful.

------------------------------------------------------------------------

## 10. `static/js/runtime_proxy.js`

Server-side rewriting only sees URLs present in the original response.

Modern JavaScript applications create additional requests dynamically
after page load. `runtime_proxy.js` provides the browser-side layer for
those cases.

The current script patches/intercepts mechanisms including:

-   `fetch()`;
-   `XMLHttpRequest.open()`;
-   WebSocket URL construction;
-   `navigator.sendBeacon()`;
-   `EventSource`;
-   dynamic DOM URL properties;
-   `setAttribute()` for URL-bearing attributes;
-   `Worker`;
-   `SharedWorker`.

It maps same-origin upstream URLs back to LocalScope and external
origins through `/proxy-external/`.

For WebSockets it maps the target into LocalScope's `/ws-proxy/` route.

This script is injected by `html_rewriter.py`.

------------------------------------------------------------------------

## 11. `static/js/app.js`

`app.js` is the LocalScope admin-panel frontend logic.

Its role is to communicate with the protected
`/__localscope/api/accounts` endpoints and update the account-management
interface.

The backend remains authoritative: frontend controls are not substitutes
for admin authentication or server-side validation.

------------------------------------------------------------------------

## 12. `static/css/style.css`

Contains the LocalScope admin/login/status-page presentation styles.

It is a presentation-only layer and does not participate in proxy
security.

------------------------------------------------------------------------

## 13. Templates

### `templates/index.html`

The authenticated LocalScope admin interface.

It works with `static/js/app.js` to manage stored Semrush accounts and
display account state.

### `templates/admin_login.html`

The LocalScope administrator login page.

Credentials are validated by the backend against environment variables.

### `templates/blocked.html`

Rendered with HTTP 403 when a normal browser document request violates
the LocalScope access policy.

### `templates/unavailable.html`

Rendered with HTTP 503 when no enabled, usable Semrush account is
available for the requesting LocalScope session.

------------------------------------------------------------------------

## 14. Complete HTTP request flow

A typical authenticated proxied request works as follows:

``` text
1. Browser requests LocalScope URL
        ↓
2. Session middleware reads/creates localscope_session
        ↓
3. Root/proxy route checks access policy
        ↓
4. Target Semrush URL is constructed
        ↓
5. handle_proxy_request() selects account
        ↓
6. Browser Cookie header is removed
        ↓
7. Selected account cookie is injected only for Semrush hosts
        ↓
8. Origin-related headers are rewritten
        ↓
9. httpx sends request upstream
        ↓
10. Semrush responds
        ↓
11. Relevant response updates account health
        ↓
12. Set-Cookie changes are merged into server-side account cookie
        ↓
13. Updated cookie is encrypted into SQLite
        ↓
14. Streaming response?
       ├── yes → stream chunks directly
       └── no  → read response body
                    ↓
15. Rewrite HTML/CSS/manifest if needed
                    ↓
16. Rewrite redirect Location if needed
                    ↓
17. Remove/prepare incompatible response headers
                    ↓
18. Return LocalScope response to browser
```

------------------------------------------------------------------------

## 15. Account lifecycle

``` text
Admin adds account
    ↓
create_account()
    ↓
enabled=False
health=unknown
    ↓
save_account()
    ↓
cookie encrypted in SQLite

Admin enables account
    ↓
enabled=True persisted
    ↓
check_account_health()
    ↓
healthy / expired / error

Browser session arrives
    ↓
selector chooses enabled + non-expired account
    ↓
assignment becomes sticky

Semrush refreshes cookies
    ↓
Set-Cookie captured server-side
    ↓
cookie_sync merges changes
    ↓
database encrypts updated cookie

Admin disables/deletes account
    ↓
account stops being usable
    ↓
deleted account assignments are removed
```

------------------------------------------------------------------------

## 16. Cookie separation

There are three conceptually different cookie categories.

### LocalScope user-session cookie

``` text
localscope_session
```

Identifies an ordinary browser session for sticky account assignment.

### LocalScope admin-session cookie

``` text
localscope_admin_session
```

Authenticates access to the internal admin panel.

### Semrush account cookie

Stored on the server as `Account.cookie`.

This cookie is:

-   entered by the administrator;
-   encrypted in SQLite;
-   decrypted when accounts load;
-   injected upstream only for Semrush hosts;
-   updated from Semrush `Set-Cookie` responses;
-   not intentionally exposed as the browser's ordinary account cookie.

Keeping these roles separate is a central part of the architecture.

------------------------------------------------------------------------

## 17. Access-control flow

For a normal path:

``` text
request
  ↓
is_document_request()
  ↓
is_access_blocked(method, path, is_document)
  ↓
allowed → proxy
blocked → 403
```

Document GET/HEAD requests are checked against broad blocked-page
keywords.

Mutating methods are checked against sensitive-action keywords.

The HTML UI additionally hides known restricted links and displays the
management banner, but those frontend changes are secondary to backend
enforcement.

------------------------------------------------------------------------

## 18. Streaming flow

For `text/event-stream`:

``` text
open upstream response
      ↓
classify as streaming
      ↓
prepare headers
      ↓
synchronize Semrush Set-Cookie if present
      ↓
async iterate upstream bytes
      ↓
StreamingResponse
      ↓
close upstream response in finally
```

This design avoids waiting for an event stream to "finish" before
sending data to the browser.

------------------------------------------------------------------------

## 19. WebSocket flow

``` text
Browser
   ↓ ws://localhost/ws-proxy/<encoded upstream>
LocalScope
   ↓ connect()
Upstream WebSocket
```

LocalScope:

1.  decodes the target URL;
2.  preserves requested subprotocols;
3.  computes the upstream origin;
4.  opens the upstream connection;
5.  accepts the browser connection with the negotiated subprotocol;
6.  concurrently forwards frames in both directions.

------------------------------------------------------------------------

## 20. Persistent vs in-memory state

### Persistent

Stored in SQLite:

``` text
account ID
account name
encrypted cookie
enabled flag
```

### In memory

Stored under `app.state`:

``` text
loaded Account objects
account health
last status code
browser → account assignments
round-robin index
session last-seen timestamps
admin sessions
```

Therefore an application restart reloads account records but resets
browser assignments, health observations, last-status values, and admin
sessions.

------------------------------------------------------------------------

## 21. Private files

### `.env`

Contains:

``` text
LOCALSCOPE_ADMIN_USER
LOCALSCOPE_ADMIN_PASSWORD
LOCALSCOPE_ENCRYPTION_KEY
```

Never distribute the real file.

### `localscope.db`

Contains encrypted authentication material and account records.

Never distribute the real database.

### `.venv/`

Contains the local Python installation environment. It is
machine/environment-specific and should be recreated from
`requirements.txt`.

### `__pycache__/` and `.pyc`

Generated Python bytecode. These are disposable and should not be
distributed.

------------------------------------------------------------------------

## 22. Shareable configuration

### `.env.example`

Documents required environment-variable names using placeholders only.

It should never contain real credentials or a real production encryption
key.

### `.gitignore`

Prevents local secrets, databases, virtual environments, Python caches,
and IDE/OS artifacts from being accidentally committed to Git.

Important: `.gitignore` does not control what Windows includes in a
manually created ZIP.

### `requirements.txt`

Lists the direct Python packages required to recreate the application
environment.

------------------------------------------------------------------------

## 23. Why LocalScope remains Semrush-specific

Much of the proxy engine is reusable in principle, but authenticated web
applications differ in:

-   authentication-cookie structure;
-   SSO flows;
-   domains/subdomains;
-   redirect behavior;
-   bot/security verification;
-   origin assumptions;
-   health endpoints;
-   account-management APIs;
-   frontend runtime navigation.

This build therefore keeps the known-good target:

``` text
https://www.semrush.com
```

and Semrush-specific health/access behavior rather than claiming
universal compatibility.

If another target application is required later, this project is best
treated as a reference implementation to copy and adapt deliberately.

------------------------------------------------------------------------

## 24. Current design boundaries and useful future work

The current codebase is feature-complete for the working
Semrush-specific design, but useful engineering work remains around
deployment quality rather than adding more proxy features.

Useful future work includes:

-   automated regression tests under `tests/`;
-   production HTTPS/reverse-proxy configuration;
-   CSRF review for admin mutations;
-   persistent or shared admin sessions if multiple worker processes are
    introduced;
-   structured application logging;
-   rate limiting for the admin login;
-   configurable session-cleanup scheduling rather than cleanup only
    during account listing;
-   migration/versioning if the SQLite schema evolves;
-   monitoring Semrush route changes that affect health or access-policy
    rules.

Avoid adding generic multisite abstractions unless there is a concrete
compatible target and a tested requirement.

------------------------------------------------------------------------

## 25. Mental model

The easiest way to understand the finished application is to separate it
into five layers:

``` text
1. Browser/session layer
   LocalScope session + admin session

2. Policy layer
   Decide what the user may request

3. Account layer
   Choose and maintain a Semrush account

4. Proxy layer
   Forward HTTP/WebSocket traffic and rewrite URLs/content

5. Persistence/security layer
   Encrypt account cookies and store account records
```

`main.py` coordinates those layers. The smaller modules exist so each
layer can be understood and maintained independently.
