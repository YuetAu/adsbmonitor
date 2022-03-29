#!/usr/bin/python
# -*- coding:utf-8 -*-
from waveshare_epd import epd2in13_V2
from datetime import datetime
import time
import os
from PIL import Image,ImageDraw,ImageFont
from string import Template

import pyModeS as pms
from pyModeS.extra.tcpclient import TcpClient

import threading

font_bold_10 = ImageFont.truetype("fonts/Menlo-Bold.ttf", 10)
font_reg_10 = ImageFont.truetype("fonts/Menlo-Regular.ttf", 10)

font_bold_12 = ImageFont.truetype("fonts/Menlo-Bold.ttf", 12)
font_reg_12 = ImageFont.truetype("fonts/Menlo-Regular.ttf", 12)

boot_time = datetime.strptime(os.popen('uptime -s').read().strip(), "%Y-%m-%d %X")

spacing_height_10 = 10
spacing_width_10 = 6
offset_10 = 5

spacing_height_12 = 12
spacing_width_12 = 8
offset_12 = 7

planes_count = 0

station_pos =  (22.44913, 114.16835)

class DeltaTemplate(Template):
    delimiter ="%"

def strfdelta(tdelta, fmt):
    d = {"D": tdelta.days}
    d["H"], rem = divmod(tdelta.seconds, 3600)
    d["M"], d["S"] = divmod(rem, 60)
    if d["D"] > 0:
        d["H"] = d["H"] + 24*d["D"]
    if d["H"] < 10:
        d["H"] = "0"+str(d["H"])
    if d["M"] < 10:
        d["M"] = "0"+str(d["M"])
    if d["S"] < 10:
        d["S"] = "0"+str(d["S"])
    t = DeltaTemplate(fmt)
    return t.substitute(**d)

def frame_boarder(image, draw, height, width):
    global planes_count
    #Title Bar
    draw.text((0, 0), "ADS-B Monitor", font=font_bold_10)
    draw.line([(0, (spacing_height_10*1)+offset_10), (width, (spacing_height_10*1)+offset_10)], width=1)

    #Uptime
    current_time = datetime.now()
    time_delta = current_time - boot_time
    timespan = strfdelta(time_delta,"%H:%M:%S")
    draw.text((width-spacing_width_10*3-spacing_width_10*len(timespan), 0), "UP", font = font_bold_10)
    draw.text((width-spacing_width_10*len(timespan), 0), strfdelta(time_delta,"%H:%M:%S"), font = font_reg_10)

    #Plane
    bmp = Image.open("pics/paper-plane-white.bmp")
    image.paste(bmp, (offset_10, 38))
    draw.line([(65, (spacing_height_10*1)+offset_10), (65, height-spacing_height_10*1-offset_10)], width=1)

    #Bottom Bar
    draw.text((0, height-spacing_height_10*1), "TOTAL", font=font_bold_10)
    draw.text((spacing_width_10*6, height-spacing_height_10*1), str(planes_count), font=font_reg_10)
    draw.line([(0, height-spacing_height_10*1-offset_10), (width, height-spacing_height_10*1-offset_10)], width=1)

planes = {}
planes_lock = False

def frame_planes(image, draw, height, width):
    global planes_lock
    i = 0
    while planes_lock:
        time.sleep(0.2)
    planes_lock = True
    for plane in list(planes.keys()):
        if (datetime.now().timestamp()-planes[plane]["lc"]) > 300.0:
            planes.pop(plane)
            continue

        draw.text((65+offset_12, (spacing_height_10*1)+offset_10*2+(spacing_height_12*i)+offset_12*i), plane, font = font_bold_12)
        if "cs" in planes[plane]:
            draw.text((65+offset_12+spacing_width_12*6+offset_12, (spacing_height_10*1)+offset_10*2+(spacing_height_12*i)+offset_12*i), planes[plane]["cs"], font = font_reg_12)
        if "alt" in planes[plane]:
            draw.text((65+offset_12+spacing_width_12*6+offset_12+spacing_width_12*7+offset_12, (spacing_height_10*1)+offset_10*2+(spacing_height_12*i)+offset_12*i), str(planes[plane]["alt"]), font = font_reg_12)
        i = i+1
    planes_lock = False

last_update_frame = 0
display_lock = False

def frame(epd):
    global last_update_frame
    global display_lock
    if (datetime.now().timestamp() - last_update_frame) < 5.0:
        return False
    last_update_frame = datetime.now().timestamp()
    print("Framing")
    image = Image.new('1', (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)
    frame_boarder(image, draw, epd.width, epd.height)
    frame_planes(image, draw, epd.width, epd.height)
    while display_lock:
        time.sleep(0.2)
    display_lock = True
    epd.displayPartial(epd.getbuffer(image))
    display_lock = False
    return True

def frame_timer(epd):
    print("Timer Framing")
    frame(epd)

epd = epd2in13_V2.EPD()
print("Init and Clear")
epd.init(epd.FULL_UPDATE)
epd.Clear(0xFF)

epd.init(epd.PART_UPDATE)
frame(epd)

class ContinousTimer():
    def __init__(self):
        self.timer = None

    def run(self, epd):
        frame_timer(epd)

        self.timer = threading.Timer(interval=10, function=self.run, args=(epd, ))
        self.timer.start()

t = ContinousTimer()
t.run(epd=epd)

class ADSBClient(TcpClient):
    def __init__(self, host, port, rawtype):
        super(ADSBClient, self).__init__(host, port, rawtype)

    def handle_messages(self, messages):
        global planes_count
        global planes_lock
        for msg, ts in messages:
            if len(msg) != 28:  # wrong data length
                continue
            df = pms.df(msg)
            if df != 17:  # not ADSB
                continue
            if pms.crc(msg) !=0:  # CRC fail
                continue
            icao = pms.adsb.icao(msg)
            tc = pms.adsb.typecode(msg)
            #time = datetime.fromtimestamp(ts)
            while planes_lock:
                time.sleep(0.2)
            planes_lock = True
            if icao not in planes:
                planes[icao] = {"lc": ts, "msg": [], "weather": {}}
                planes_count = planes_count + 1

            if 1 <= tc and tc <= 4:
                planes[icao]["cs"] = pms.adsb.callsign(msg).strip("_")
            elif (5 <= tc and tc <= 18) or (20 <= tc and tc <= 22):
                flag = pms.adsb.oe_flag(msg)
                i = 0
                for bmsg in planes[icao]["msg"]:
                    if (datetime.now().timestamp()-bmsg[1]) > 10.0:
                        planes[icao]["msg"].pop(i)
                        i = i + 1
                        continue
                    if bmsg[2] != flag:
                        if bmsg[2] == 0:
                            even = bmsg
                            odd = (msg, ts, flag)
                        else:
                            odd = bmsg
                            even = (msg, ts, flag)
                        lat, lon = pms.adsb.position(even[0], odd[0], even[1], odd[1], station_pos[0], station_pos[1])
                        planes[icao]["lat"] = lat
                        planes[icao]["lon"] = lon
                    i = i + 1
                planes[icao]["alt"] = pms.adsb.altitude(msg)
                planes[icao]["msg"].append((msg, ts, flag))
            elif tc == 19:
                speed, angle, vertical, st = pms.adsb.velocity(msg)
                planes[icao]["sp"] = speed
                planes[icao]["ag"] = angle
                planes[icao]["vr"] = vertical
                planes[icao]["st"] = st

            if pms.bds.bds40.is40(msg):
                planes[icao]["altfms"] = pms.bds.bds40.selalt40fms(msg)
                planes[icao]["altmcp"] = pms.bds.bds40.selalt40mcp(msg)

            if pms.bds.bds44.is44(msg):
                planes[icao]["weather"]["humd"] = pms.bds.bds44.hum44(msg)
                planes[icao]["weather"]["temp"] = pms.bds.bds44.temp44(msg)
                planes[icao]["weather"]["turb"] = pms.bds.bds44.turb44(msg)
                planes[icao]["weather"]["wind"] = pms.bds.bds44.wind44(msg)

            if pms.bds.bds45.is45(msg):
                planes[icao]["weather"]["icing"] = pms.bds.bds45.ic45(msg)
                planes[icao]["weather"]["mburst"] = pms.bds.bds45.mb45(msg)
                planes[icao]["weather"]["windshear"] = pms.bds.bds45.ws45(msg)
                planes[icao]["weather"]["wakevortex"] = pms.bds.bds45.wv45(msg)

            if pms.bds.bds50.is50(msg):
                planes[icao]["roll"] = pms.bds.bds50.roll50(msg)

            if pms.bds.bds60.is60(msg):
                planes[icao]["mach"] = pms.bds.bds60.mach60(msg)

            planes_lock = False
            print(icao, tc, time.strftime("%H:%M:%S"), planes[icao])
            frame(epd)

client = ADSBClient(host='127.0.0.1', port=30005, rawtype='beast')
client.run()
