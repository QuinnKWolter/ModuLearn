# put this file outside the modulearn folder
# then use it to update the modulearn and rebuild/run the docker containers
set -e

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

rm -rf ModuLearn.new
git clone https://github.com/QuinnKWolter/ModuLearn.git ModuLearn.new
sudo rm -rf ModuLearn
sudo mv ModuLearn.new ModuLearn
sudo docker-compose build
sudo docker-compose down
sudo docker-compose up -d
