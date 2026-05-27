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

# 3. Clean, rebuild, and launch your container infrastructure
sudo docker-compose down
sudo docker-compose build
sudo docker-compose up -d

# --- START OF CHANGE ---
# Wait dynamically for single-threaded collectstatic to finish and Gunicorn to boot
echo "Waiting for production asset compilation to complete inside the container..."
until sudo docker logs modulearn__webapp 2>&1 | grep -q "Starting gunicorn"; do
    echo -n "."
    sleep 2
done
echo -e "\nAsset compilation finished! Proceeding to file extraction..."
# --- END OF CHANGE ---

# 4. Extract the dynamically compiled production assets out to Nginx
sudo rm -rf /var/www/html/modulearn-static/*
sudo docker cp modulearn__webapp:/modulearn/staticfiles/. /var/www/html/modulearn-static/

echo "Deployment completed successfully!"