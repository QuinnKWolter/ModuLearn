#!/bin/bash
set -e

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

# 1. Pull down a fresh copy of your repository
rm -rf ModuLearn.new
git clone https://github.com/QuinnKWolter/ModuLearn.git ModuLearn.new
sudo rm -rf ModuLearn
sudo mv ModuLearn.new ModuLearn

# 2. Sync your repository's production compose file to the root directory
cp ModuLearn/docker/docker-compose.yml ./docker-compose.yml

# 3. Validate and build while the existing container remains available.
sudo docker-compose config --quiet
sudo docker-compose build
sudo docker-compose up -d --no-deps --force-recreate webapp

# Check the current container, rather than matching an old startup log line.
# Migrations and collectstatic finish before Gunicorn starts accepting requests.
echo "Waiting up to five minutes for application startup..."
ready=false
for attempt in $(seq 1 60); do
    if sudo docker exec modulearn__webapp python -c 'import urllib.request; r = urllib.request.urlopen("http://127.0.0.1:8000/", timeout=3); raise SystemExit(0 if r.status == 200 else 1)' >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 2
done
if [ "$ready" != true ]; then
    echo "Startup check failed. Existing published static files were left intact."
    sudo docker logs --tail 100 modulearn__webapp
    exit 1
fi

# 4. Publish compiled assets without removing hashes still referenced by open pages.
# If startup was recovered manually after this script failed, run this copy step
# once Gunicorn is running; starting the container alone does not publish assets.
sudo mkdir -p /var/www/html/modulearn-static
sudo docker cp modulearn__webapp:/modulearn/staticfiles/. /var/www/html/modulearn-static/

echo "Deployment completed successfully!"
