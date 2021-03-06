#!/usr/bin/python
# -*- coding:utf-8 -*-
from waveshare_epd import epd2in13_V2
from datetime import datetime
import time
import os
from PIL import Image,ImageDraw,ImageFont
from string import Template
import signal

import httpx

import threading

font_bold_10 = ImageFont.truetype("fonts/Menlo-Bold.ttf", 10)
font_reg_10 = ImageFont.truetype("fonts/Menlo-Regular.ttf", 10)

font_bold_12 = ImageFont.truetype("fonts/Menlo-Bold.ttf", 12)
font_reg_12 = ImageFont.truetype("fonts/Menlo-Regular.ttf", 12)

font_bold_14 = ImageFont.truetype("fonts/Menlo-Bold.ttf", 14)
font_reg_14 = ImageFont.truetype("fonts/Menlo-Regular.ttf", 14)

font_bold_16 = ImageFont.truetype("fonts/Menlo-Bold.ttf", 16)
font_reg_16 = ImageFont.truetype("fonts/Menlo-Regular.ttf", 16)

boot_time = datetime.strptime(os.popen('uptime -s').read().strip(), "%Y-%m-%d %X")

spacing_height_10 = 10
spacing_width_10 = 6
offset_10 = 5

spacing_height_12 = 12
spacing_width_12 = 8
offset_12 = 7


class DeltaTemplate(Template):
    delimiter ="%"

class GracefulKiller:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self,signum, frame):
    self.kill_now = True

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

bmp = Image.open("pics/paper-plane-white.bmp")

static_image = None

def frame_static(height, width):
    global static_image
    if not static_image:
        image = Image.new('1', (width, height), 255)
        draw = ImageDraw.Draw(image)

        #Title Bar

        draw.text((0, 0), "ADS-B Monitor", font=font_bold_10)
        draw.line([(0, (spacing_height_10*1)+offset_10), (width, (spacing_height_10*1)+offset_10)], width=1)

        #Plane Image
        image.paste(bmp, (offset_10, 38))
        draw.line([(65, (spacing_height_10*1)+offset_10), (65, height-spacing_height_10*1-offset_10)], width=1)

        #Bottom Bar
        draw.line([(0, height-spacing_height_10*1-offset_10), (width, height-spacing_height_10*1-offset_10)], width=1)

        static_image = image.copy()
        return image, draw

    else:
        image = static_image.copy()
        draw = ImageDraw.Draw(image)
        return image, draw

last_ssid = None
last_local_ip = None
static_network = None

def draw_ssid(image, draw, height, width, ssid, local_ip):

    bb_offset_x = width-spacing_width_10*len(local_ip)
    bb_offset_y = height-spacing_height_10*1
    draw.text((bb_offset_x, bb_offset_y), local_ip, font = font_reg_10)
    bb_offset_x = bb_offset_x - spacing_width_10*(len(ssid)+1)
    draw.text((bb_offset_x, bb_offset_y), ssid, font = font_bold_10)

    static_network = image.copy()
    return image, draw

def frame_ssid(image, draw, height, width):
    global last_ssid
    global last_local_ip
    global static_network
    local_ip = None
    ssid = None
    hostname_cmd = os.popen("hostname -I").read().split()
    if len(hostname_cmd) >= 1:
        if hostname_cmd[0] != "172.17.0.1":
            local_ip = hostname_cmd[0]
        else:
            local_ip = "Unable"
    else:
        local_ip = "Unable"
    ssid_cmd = os.popen("iwgetid").read().split('"')
    if len(ssid_cmd) >= 2:
        ssid = ssid_cmd[1]
    else:
        ssid = "NO WIFI"

    if ssid != last_ssid or local_ip != last_local_ip:
        image, draw = draw_ssid(image, draw, height, width, ssid, local_ip)
    else:
        if not static_network:
            image, draw = draw_ssid(image, draw, height, width, ssid, local_ip)
        else:
            image = static_network.copy()
            draw = ImageDraw.Draw(image)
    return image, draw

all_planes = {}
total_planes = 0

def frame_boarder(draw, height, width):
    global planes_count


    #Title Bar


    #Uptime
    current_time = datetime.now()
    time_delta = current_time - boot_time
    timespan = strfdelta(time_delta,"%H:%M:%S")
    tb_offset_x = width - spacing_width_10*len(timespan)
    draw.text((tb_offset_x, 0), timespan, font = font_reg_10)
    tb_offset_x = tb_offset_x - spacing_width_10*3
    draw.text((tb_offset_x, 0), "UP", font = font_bold_10)

    #Temperature
    temp = float(os.popen("vcgencmd measure_temp").read().split("=")[1].split("'")[0])
    tb_offset_x = tb_offset_x - spacing_width_10*(len(str(temp))+1)
    draw.text((tb_offset_x, 0), str(temp), font=font_reg_10)
    tb_offset_x = tb_offset_x - spacing_width_10*5
    draw.text((tb_offset_x, 0), "TEMP", font=font_bold_10)


    #Bottom Bar


    #Total Planes
    bb_offset_x = 0
    bb_offset_y = height-spacing_height_10*1
    draw.text((bb_offset_x, bb_offset_y), "TOTAL", font=font_bold_10)
    bb_offset_x = bb_offset_x + spacing_width_10*6
    draw.text((bb_offset_x, bb_offset_y), str(total_planes), font=font_reg_10)

client = httpx.Client(http2=True, base_url="http://127.0.0.1/tar1090")

def frame_planes(draw, height, width):
    global all_planes
    global total_planes
    global client
    planes = []

    try:
        r = client.get("/data/aircraft.json")
    except httpx.RemoteProtocolError:
        for i in range(1,3):
            print("Retry in "+str(i))
            r = client.get("/data/aircraft.json")
            if r.status_code == httpx.codes.OK:
                break

    if r.status_code == httpx.codes.OK:
        json = r.json()
        planes = json["aircraft"]
    i = 0
    for plane in list(all_planes.keys()):

        if (datetime.now().timestamp() - all_planes[plane]["lc"]) > 3600.0:
            all_planes.pop(plane)

    for plane in planes:

        if plane["hex"] not in all_planes:
            all_planes[plane["hex"]] = {}
            total_planes = total_planes + 1


        if i > 5:
            break

        offset_x = 65+offset_12
        offset_y = (spacing_height_10*1)+offset_10*2+(spacing_height_12*i)+offset_10*i
        draw.text((offset_x, offset_y), plane["hex"].upper(), font = font_bold_12)

        offset_x = offset_x + spacing_width_12*6+offset_10
        if "flight" in plane:
            draw.text((offset_x, offset_y), plane["flight"].strip().upper(), font = font_reg_12)

        offset_x = offset_x + spacing_width_12*7+offset_10
        if "alt_baro" in plane:
            draw.text((offset_x, offset_y), str(plane["alt_baro"]), font = font_reg_12)

            if "baro_rate" not in plane:
                if "alt" in all_planes[plane["hex"]]:
                    plane["baro_rate"] = (plane["alt_baro"] - all_planes[plane["hex"]]["alt"])/(datetime.now().timestamp()-all_planes[plane["hex"]]["lc"])

            all_planes[plane["hex"]]["alt"] = plane["alt_baro"]

        offset_x = offset_x + spacing_width_12*5+offset_10

        if "baro_rate" in plane:
            if plane["baro_rate"] > 0:
                draw.text((offset_x, offset_y-3), "???", font = font_bold_16)
            elif plane["baro_rate"] == 0:
                draw.text((offset_x, offset_y-3), "-", font = font_bold_16)
            elif plane["baro_rate"] < 0:
                draw.text((offset_x, offset_y-3), "???", font = font_bold_16)


        all_planes[plane["hex"]]["lc"] = datetime.now().timestamp()
        i = i + 1

def frame(epd):
    print("Framing")
    image, draw = frame_static(epd.width, epd.height)
    image, draw = frame_ssid(image, draw, epd.width, epd.height)
    frame_boarder(draw, epd.width, epd.height)
    frame_planes(draw, epd.width, epd.height)
    epd.displayPartial(epd.getbuffer(image))
    return True

epd = epd2in13_V2.EPD()
print("Init and Clear")
epd.init(epd.FULL_UPDATE)
epd.Clear(0xFF)

epd.init(epd.PART_UPDATE)
frame(epd)

killer = GracefulKiller()
while not killer.kill_now:
    frame(epd)
    time.sleep(1)
epd.sleep()
client.close()
