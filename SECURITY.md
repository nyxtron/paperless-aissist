# Security Policy

## Supported Versions

Paperless-AIssist is maintained by one person in their spare time. Security fixes
go into the next release from the current line — there are no backports to older
versions, so please upgrade before reporting.

| Version           | Supported          |
| ----------------- | ------------------ |
| Latest release    | :white_check_mark: |
| Anything older    | :x:                |

## Reporting a Vulnerability

Please report vulnerabilities privately through GitHub, not in a public issue:

**[Report a vulnerability](https://github.com/nyxtron/paperless-aissist/security/advisories/new)**
(also reachable via the repository's *Security* tab → *Report a vulnerability*)

Helpful details, as far as you have them:

- What kind of vulnerability it is, and what an attacker could do with it
- The affected version and how the instance is deployed
- The source files or endpoints involved
- Steps to reproduce, and any configuration needed to trigger it
- Proof-of-concept code, if you have it

I aim to reply within a week and will keep you posted while working on a fix.
If you have not heard back after two weeks, feel free to send a reminder in the
advisory thread.

## Disclosure

Reports stay private until a fixed release is available. Once it ships, the
advisory is published and I am happy to credit you unless you prefer otherwise.
If a report turns out to affect a dependency rather than this project, I will
say so and point you to the right place.

## Deploying Paperless-AIssist safely

Paperless-AIssist holds an API token for your Paperless-ngx instance and can read
and modify your documents. Treat it as trusted infrastructure:

1. **Do not expose it to the internet.** It is built for a private network. If you
   need remote access, put it behind a VPN or an authenticating reverse proxy.
2. **Turn on the login.** *Settings → Advanced → Anmeldung erforderlich* validates
   users against your Paperless instance. It is off by default.
3. **Keep the Automation API token secret.** It is shown once when generated and
   stored only as a hash; anyone holding it can trigger processing.
4. **Protect the data volume.** `/app/data` holds the configuration database
   including your Paperless token.
5. **Update regularly.** Fixes ship in the latest release only.
