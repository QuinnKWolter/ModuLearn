# put this file outside the modulearn folder
# then use it to update the modulearn and rebuild/run the docker containers
sudo rm -rf ModuLearn
git clone https://github.com/QuinnKWolter/ModuLearn.git
sudo docker-compose build --no-cache
sudo docker-compose down
sudo docker-compose up -d