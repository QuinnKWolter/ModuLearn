# Serving ModuLearn at adapt2.sis.pitt.edu/modulearn

The production Compose file sets the public domain, allowed hosts, CSRF origin,
proxy CORS origin, script prefix, static URL, and media URL. Its `environment`
entries take precedence over values in the production `.env`; secrets and
service-specific settings still come from `.env`.

On the adapt2 nginx host, route `/modulearn/` to port 20600 and strip that
prefix before forwarding to Django. Preserve the public host and HTTPS scheme:

```nginx
location = /modulearn { return 301 /modulearn/; }

location /modulearn-static/ {
    alias /var/www/html/modulearn-static/;
}

location /modulearn/ {
    proxy_pass http://127.0.0.1:20600/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

The deploy script copies collected static files to the nginx alias above.
With `SERVE_MEDIA_FILES=True`, Django handles `/modulearn/media/` through the
same proxy location. Keep existing nginx routes for PAWS, Aggregate, and other
services on adapt2 separate from `/modulearn/`. If nginx is on another host,
replace the upstream address and static-file path accordingly.
Restrict direct access to port 20600 to the trusted proxy, since Django uses
the proxy's `X-Forwarded-Proto` header to recognize HTTPS requests.


## Deployment procedure

The maintained script is [docker/reload-from-github.sh](../../docker/reload-from-github.sh). Install that script as `/home/qkw3/modulearn-app/reload-from-github.sh`; editing the repository copy does not update a separately installed root script. The deployment root owns `.env`, persisted storage and the active Compose file. Keep local changes out of the checkout replaced by the script.

The script clones the repository, copies its production Compose template, validates/builds while the old container remains available, recreates only `webapp`, waits for a successful application response, then copies collected assets to nginx. It does not delete old published asset hashes or run `docker-compose down`. It is not an automatic database backup or rollback system: take a database-consistent backup and retain the prior image/revision before migrations.

On the server verified in this project, the deployment-root `.env` needs `MODULEARN_HOST_GATEWAY=172.17.0.1`. Preserve that override: the installed Docker engine did not accept the template's `host-gateway` default. Do not assume another server uses the same address.

After deployment:

```bash
cd /home/qkw3/modulearn-app
sudo docker ps --filter name=modulearn__webapp
sudo docker logs --since 5m --tail 100 modulearn__webapp
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:20600/
sudo docker exec modulearn__webapp bash -c 'cd /modulearn && python manage.py showmigrations courses'
```

Use `/` for the direct-container check: nginx strips the public `/modulearn/` prefix. Check the public home, login, a course and the actual hashed stylesheet URL shown in page source from a browser that reaches public HTTPS. Curl `HTTP 000` is a transport failure, not a successful HTTP response or proof of a missing file.

If startup was recovered manually after the script exited, publish collected files after the app is ready:

```bash
sudo docker cp modulearn__webapp:/modulearn/staticfiles/. /var/www/html/modulearn-static/
```

Starting the container alone does not publish nginx's static files. Never clear the live static directory before copying: open pages can still reference older hashes. Check media uploads too. Public LMS callback, JWKS and study-entry URLs must use HTTPS and the `/modulearn` prefix.

## QuizJET / Pitt network diagnostics

A `No route to host` connecting to the public IP occurs before a provider response. The proxy resolves the original hostname through the container resolver; HTTP retains its Host header. Both `pawscomp2.sis.pitt.edu` and `adapt2.sis.pitt.edu` must resolve to reachable destinations. Tests supplied from production confirmed both work through `172.17.0.1`; the Compose-network gateway itself is not necessarily the correct host service address.

```bash
sudo docker inspect modulearn__webapp --format '{{json .HostConfig.ExtraHosts}}'
sudo docker exec -i modulearn__webapp python - < ModuLearn/docker/check-quizjet-network.py
```

The diagnostic optionally accepts candidate IP arguments and checks QuizJET markers without submitting student answers. For a mapping-only change, back up/edit the deployment-root Compose/environment, validate with `sudo docker-compose config --quiet`, then run `sudo docker-compose up -d --no-deps --force-recreate webapp`. A plain restart does not apply new host mappings. No course URL rewrite or progress repair follows automatically from a DNS fix.

An `Activity enrollment not found` 403 is a separate context/authorization issue: verify the signed-in account, exact session/module and instructor-testing enrollment. Do not bypass access checks to repair networking.

## Direct PAWS database and catalog checks

For ACOS certificate errors, production verified that the OS CA bundle succeeds where Requests' default bundle fails. Set `REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt` in the deployment-root `.env`, validate Compose and recreate `webapp`. The Dockerfile now includes this default for future builds and checks that the bundle exists. Verify with `requests.get("https://acos.cs.vt.edu/", timeout=15)` inside the running container; TLS verification remains enabled. This is separate from the Pitt hostname mapping and missing-intermediate handling.

Application-managed SSH tunneling and the implicit Saltire test registration have been removed. HTTPS does not replace direct MySQL: preserve `PAWS_DB_HOST`, `PAWS_DB_PORT`, `PAWS_DB_USER`, `PAWS_DB_PASSWORD` and schema settings. API login, provisioning, password sync and legacy analytics have different database needs. Arrange any private-network access outside Django.

```bash
sudo docker exec modulearn__webapp bash -c 'cd /modulearn && python manage.py shell -v 0 -c "from dashboard.kt_db_connection import get_paws_db_connection; c = get_paws_db_connection(); ok, message = c.connect(); print(\"PAWS direct database connection:\", \"OK\" if ok else \"FAILED\"); c.disconnect(); raise SystemExit(0 if ok else 1)"'
sudo docker exec modulearn__webapp bash -c 'cd /modulearn && python manage.py check_slc_catalog'
```

The first check only connects; verify a known test account and KT-linked analytics separately. The second distinguishes catalog upstream/TLS/cache errors and uses temporary diagnostic cache keys. Catalog counts change over time. Never disable TLS verification as a workaround. See [integrations](integrations.md).

Old SSH environment values are ignored. A manually stored Saltire registration is independent of the removed default: deactivate obsolete registrations in Admin without deleting identity history. Rebuild to remove obsolete dependencies. For LTI testing, follow [testing](testing.md); do not recreate an existing lab merely to inspect it.
