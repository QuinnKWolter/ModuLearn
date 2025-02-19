# put this file outside the modulearn folder
# then use it to update the modulearn and rebuild/run the docker containers
sudo rm -rf modulearn
git clone https://github.com/QuinnKWolter/ModuLearn.git
sudo docker-compose --env-file .env.host-ip build --no-cache
sudo docker-compose --env-file .env.host-ip down
sudo docker-compose --env-file .env.host-ip up -d