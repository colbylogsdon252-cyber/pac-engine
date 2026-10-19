# PAC Integration Distribution — Increment 2

Scope: installable local CLI, read-only TypeScript validation client, and display-only Web Component. No Proof Token issuance, execution API, downstream dispatch, or authority delegation.

## CLI

From the repository, install `python -m pip install .` then run `pac validate input.json`. The CLI uses the original canonical validator and retains its exit codes. The frozen contract JSON is bundled in the installed package. Packaging is tested in an isolated temporary directory.

## TypeScript SDK

Under `integrations/typescript`, run `npm install`, `npm test`. Instantiate `new PacValidationClient("https://pac.example", () => getToken())`. The token callback must obtain a scoped credential from a trusted backend. Never hardcode or embed the current server-side API bearer key in browser code. The client calls only `POST /v1/validations`, refuses remote plaintext HTTP and redirects, and treats malformed responses and authentication errors as failures. This package is private and not published to npm.

## Embedded component

Import the built `dist/widget.js` in a trusted web application and render:

```html
<pac-validation-status status="invalid"></pac-validation-status>
```

The component displays host-provided status only. It does not fetch, authorize, issue Proof Tokens, or handle credentials. Hosts must source and authenticate status on their own trusted backend. Never treat the badge as proof of execution authority.

## Operational boundary

Existing `POST /validate` remains unchanged. The authenticated `POST /v1/validations` remains validation-only. Do not expose legacy unauthenticated routes publicly. Tenant identity, rate limits, audit trail, production public ingress, and proactive webhooks remain future increments subject to independent review.
