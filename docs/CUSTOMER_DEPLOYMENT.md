# Customer Docker deployment

## What the customer image contains

The root `Dockerfile` is a multi-stage production build. Its final stage contains:

- minified frontend assets from `vite build` (no React/TypeScript source or source maps);
- importable Python bytecode for the proprietary backend (no application `.py` files);
- runtime dependencies, OCR language packs, and a non-root operating-system user;
- an empty persistent data mount at `/opt/soc/data`.

Build tools, Git history, tests, local data, `.env`, package caches and source
trees remain in builder stages and are not copied into the distributed image.

This prevents normal source browsing, but it is not absolute DRM. A customer
who controls the Docker host can export and inspect every image layer, and both
Python bytecode and browser JavaScript can be reverse engineered. If contractual
source secrecy is mandatory, operate the product as a vendor-hosted service.
For on-premises delivery, combine the stripped image with a licence agreement,
a private registry, per-customer image credentials and signed release images.

## Build and verify

From the repository root:

```bash
docker build --pull --build-arg APP_VERSION=0.4.0 -t registry.example.com/soorin/soc-workbench:0.4.0 .

# This must print no proprietary Python or TypeScript source files.
docker run --rm --entrypoint sh registry.example.com/soorin/soc-workbench:0.4.0 \
  -c "find /opt/soc -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) -print"
```

Only distribute the tagged image. Do not send the repository, build context or
Compose override files containing secrets.

## Configure

Copy `.env.example` to `.env` on the deployment host and set, at minimum:

```dotenv
ENVIRONMENT=production
DEBUG=false
ADMIN_USERNAME=admin
ADMIN_PASSWORD=a-long-unique-initial-password
SECRET_KEY=a-random-value-of-at-least-48-characters
CORS_ORIGINS=https://soc.customer.example
ATLASSIAN_OAUTH_REDIRECT_URI=https://soc.customer.example/api/atlassian/oauth/callback
```

Keep the same `SECRET_KEY` for the lifetime of a deployment. Changing it
invalidates sessions and makes stored encrypted connection credentials
unreadable. Put TLS at a reverse proxy/load balancer and forward only trusted
proxy headers.

## Run and operate

```bash
SOC_IMAGE=registry.example.com/soorin/soc-workbench:0.4.0 \
SOC_PORT=8000 \
docker compose up -d --no-build

docker compose ps
docker compose logs --tail=100 soc-workbench
curl --fail http://127.0.0.1:8000/api/health
```

The Compose profile runs read-only, drops Linux capabilities, disallows new
privileges, writes temporary files only to a bounded tmpfs, and persists the
database/uploads/reports in the named `soc-workbench-data` volume.

Back up the volume before upgrades:

```bash
docker run --rm -v soc-workbench-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/soc-workbench-data.tgz -C /data .
```

To upgrade, pull the new immutable tag, update `SOC_IMAGE`, and run
`docker compose up -d --no-build`. Database migrations run automatically on
startup. Roll back with the previous image tag and the matching pre-upgrade
volume backup when a release includes a non-backward-compatible migration.
