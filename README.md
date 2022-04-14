# ADS-B Monitor
ADS-B data on your e-ink screen

# Installation

Tutorial copy from https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT

1. Enable SPI interface

`sudo raspi-config` Choose Interfacing Options -> SPI -> Yes `sudo reboot`

2. Install BCM2835 libraries 

```
wget http://www.airspayce.com/mikem/bcm2835/bcm2835-1.68.tar.gz
tar zxvf bcm2835-1.68.tar.gz 
cd bcm2835-1.68/
sudo ./configure
sudo make
sudo make check
sudo make install
cd ~/
```

3. Install WiringPi libraries 

```
git clone https://github.com/WiringPi/WiringPi
cd WiringPi
./build
cd ~/
```

4. Install Python3 libraries 

```
sudo apt-get update
sudo apt-get install python3-pip python3-pil python3-numpy
sudo pip3 install RPi.GPIO
sudo pip3 install spidev
```

5. Install ADS-B Monitor

```
git clone https://github.com/YuetAu/adsbmonitor
cd adsbmonitor
sudo cp adsbmonitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adsbmonitor.service
```

It will try to grab `127.0.0.1/dat/aircraft.json` in Tar1090. Edit yourself to match your situation.
