# LocalScope --- Semrush Reverse Proxy

LocalScope is a Semrush-specific FastAPI reverse proxy that lets browser
sessions use administrator-supplied Semrush account cookies without
exposing those upstream cookies directly to the browser.

It provides:

-   a protected LocalScope admin panel;
-   encrypted SQLite storage for Semrush account cookies;
-   enable/disable/delete account management;
-   sticky browser-session-to-account assignment with round-robin
    selection;
-   Semrush account health checking;
-   synchronization of refreshed upstream cookies;
-   HTTP, streaming/SSE, and WebSocket proxying;
-   HTML, CSS, manifest, redirect, origin, and URL rewriting;
-   restrictions for sensitive account, billing, subscription, security,
    team, and logout operations;
-   a LocalScope banner and hidden restricted links in proxied HTML.

> This repository is intentionally Semrush-specific. It is not designed
> as a universal reverse proxy for arbitrary websites.

## Project structure

``` text
localscope-semrush/
├── app/
│   ├── accounts/
│   │   ├── cookie_sync.py
│   │   ├── health.py
│   │   ├── health_check.py
│   │   ├── models.py
│   │   ├── selector.py
│   │   └── session_cleanup.py
│   ├── inspectors/
│   │   └── stream_classifier.py
│   ├── policies/
│   │   └── access_rules.py
│   ├── proxy/
│   │   ├── cookie_rewriter.py
│   │   ├── css_rewriter.py
│   │   ├── html_rewriter.py
│   │   ├── manifest_rewriter.py
│   │   ├── origin_rewriter.py
│   │   ├── proxy_engine.py
│   │   ├── redirect_rewriter.py
│   │   ├── target_config.py
│   │   └── url_mapper.py
│   ├── security/
│   │   └── cookie_crypto.py
│   ├── storage/
│   │   └── database.py
│   └── main.py
├── static/
│   ├── css/style.css
│   └── js/
│       ├── app.js
│       └── runtime_proxy.js
├── templates/
│   ├── admin_login.html
│   ├── blocked.html
│   ├── index.html
│   └── unavailable.html
├── tests/
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

For a detailed explanation of every important file and the complete
request flow, see `docs/ARCHITECTURE.md`.

## Requirements

-   Python 3.12 or a compatible modern Python 3 release
-   pip
-   a Semrush account cookie that you are authorized to use
-   Windows, Linux, or macOS for local development

The current dependency list is:

``` text
fastapi==0.141.1
uvicorn[standard]==0.52.3
httpx==0.28.1
beautifulsoup4==4.15.0
python-dotenv==1.2.3
python-multipart==0.0.32
cryptography==50.0.0
websockets==17.0.1
brotli==1.2.0
zstandard==0.25.0
Jinja2==3.1.6
```

## Installation

Create a virtual environment:

``` powershell
python -m venv .venv
```

Activate it on Windows PowerShell:

``` powershell
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

``` powershell
pip install -r requirements.txt
```

Do not distribute your `.venv` directory. Every installation should
create its own virtual environment from `requirements.txt`.

## Environment configuration

Copy the safe template:

``` powershell
Copy-Item .env.example .env
```

The application requires three environment variables:

``` env
LOCALSCOPE_ADMIN_USER=your_admin_username
LOCALSCOPE_ADMIN_PASSWORD=your_admin_password
LOCALSCOPE_ENCRYPTION_KEY=your_generated_fernet_key
```

Generate a Fernet encryption key with:

``` powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Place the generated value in `LOCALSCOPE_ENCRYPTION_KEY`.

### Important encryption-key rule

Do not casually replace `LOCALSCOPE_ENCRYPTION_KEY` after accounts have
been stored. Existing account cookies in `localscope.db` were encrypted
with the previous key. A different key cannot decrypt them, and
application startup will fail while loading those records.

## Database

LocalScope uses SQLite and stores data in:

``` text
localscope.db
```

You do not need to distribute a database file.

At application startup, `initialize_database()` creates the database and
the `accounts` table if they do not already exist.

The database stores:

-   account ID;
-   account display name;
-   encrypted Semrush cookie;
-   enabled/disabled state.

The raw Semrush cookie is encrypted before it is written to SQLite.

## Running LocalScope

For development:

``` powershell
uvicorn app.main:app --reload
```

If you want another local port:

``` powershell
uvicorn app.main:app --reload --port 8001
```

Open the admin panel at:

``` text
http://127.0.0.1:8000/__localscope/
```

or use the port you selected.

The proxied Semrush application is available from the root URL:

``` text
http://127.0.0.1:8000/
```

## Admin workflow

1.  Open `/__localscope/`.
2.  LocalScope redirects unauthenticated administrators to
    `/__localscope/login`.
3.  Log in using `LOCALSCOPE_ADMIN_USER` and
    `LOCALSCOPE_ADMIN_PASSWORD`.
4.  Add a Semrush account name and cookie.
5.  Newly added accounts start disabled.
6.  Enable an account to make it available for browser-session
    assignment.
7.  Enabling an account performs a Semrush health check against
    `/projects/api/me`.
8.  Disable an account to stop new/continued use.
9.  Delete an account to remove it from memory, SQLite, and active
    browser-session assignments.

## Browser-session assignment

LocalScope creates a `localscope_session` cookie for ordinary proxied
users.

A browser session is assigned one enabled, non-expired account. The
assignment is sticky: subsequent requests from the same LocalScope
session continue using the same account while that account remains
enabled and non-expired.

For new sessions, accounts are selected in round-robin order.

If no usable account exists, LocalScope returns the `unavailable.html`
page with HTTP 503.

Stale session assignments are cleaned after 15 minutes of inactivity
when the admin account list is requested.

## Cookie security model

The upstream Semrush account cookie is not copied into the browser's
normal `Cookie` header.

Instead:

1.  the browser sends its request to LocalScope;
2.  LocalScope removes the browser `Cookie` header from the upstream
    header set;
3.  for `semrush.com` and its subdomains only, LocalScope injects the
    selected account's server-side cookie;
4.  the request is sent to Semrush with `httpx`;
5.  Semrush `Set-Cookie` updates are merged into the stored account
    cookie;
6.  the updated cookie is encrypted and persisted to SQLite.

This is why `.env` and `localscope.db` must remain private.

## Access restrictions

`app/policies/access_rules.py` blocks sensitive page navigation and
mutating actions.

Restricted areas include keywords associated with:

-   login/logout/signup;
-   account/profile/settings;
-   billing/payment;
-   subscriptions/pricing/upgrades;
-   password/security;
-   teams/members/invitations.

Broad page restrictions are applied to document navigation. Sensitive
`POST`, `PUT`, `PATCH`, and `DELETE` actions are blocked regardless of
whether they originate from normal navigation or XHR/fetch.

API-style blocked requests receive JSON with HTTP 403. Browser document
requests receive `blocked.html`.

The HTML rewriter also hides configured restricted links and injects the
LocalScope management banner. UI hiding is only a convenience layer; the
backend access policy is the enforcement layer.

## Files that must not be shared

Do not commit or include these in a shareable project archive:

``` text
.venv/
.env
localscope.db
__pycache__/
*.pyc
```

`.gitignore` is configured to exclude these from Git, but remember:
`.gitignore` does not prevent Windows or another archive tool from
adding them to a manually created ZIP.

Before sharing a ZIP, inspect its contents manually.

## Files that should be shared

A clean project distribution should include:

``` text
app/
static/
templates/
tests/
.env.example
.gitignore
README.md
requirements.txt
docs/
```

## Security notes

-   Use a strong admin password.
-   Keep the Fernet key private.
-   Keep `localscope.db` private even though stored cookies are
    encrypted.
-   Only add upstream account cookies you are authorized to use.
-   Use HTTPS and an appropriate production deployment configuration
    before exposing LocalScope beyond a trusted local/private
    environment.
-   The in-memory admin-session set and development Uvicorn command are
    suitable for the current application design, but production
    deployment may require additional session persistence, CSRF
    protection, rate limiting, logging, and reverse-proxy configuration
    depending on the deployment environment.
-   Access restrictions are application policy controls; review them
    when Semrush changes routes or APIs.

## Development vs production

`uvicorn app.main:app --reload` is a development command. `--reload`
watches source files and restarts the process when code changes.

For a production deployment, remove `--reload`, place the application
behind HTTPS-capable infrastructure as appropriate, and review
cookie/security settings for the deployment domain.

## Documentation

Read `docs/ARCHITECTURE.md` for:

-   the purpose of every important file;
-   startup flow;
-   complete HTTP request/response flow;
-   account selection;
-   cookie encryption and synchronization;
-   health checking;
-   URL and content rewriting;
-   streaming and WebSocket behavior;
-   access-policy enforcement;
-   frontend/admin responsibilities.
