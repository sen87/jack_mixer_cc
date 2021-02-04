#!/usr/bin/python
# -*- coding: utf-8 -*-
# sen <sen@archlinux.us>
# --- optional dependencies
# libnotify, python-gobject
# --- imports
from sys import argv
import getopt
from os import _exit
import asyncio
# ----------------------
info = """
┌───────────────────────────────────────────────────
│ jack_mixer MIDI CC Controller
│ v0.1 (client)
├───────────────────────────────────────────────────
│ Options:
│ --debug                  debug mode
│ --host <IP>              remote control
│                            > defaults to localhost
│ -n                       disable notifications
├──────────
│ Controls:
│ -v <chan name>,<volume>  set volume (0 - 127)
│ -i <chan name>           increase volume
│ -d <chan name>           decrease volume
│ -m <chan name>           toggle mute
│ -s <chan name>           toggle solo mode
└───────────────────────────────────────────────────\n"""
# --- settings
host = "localhost"
port = 9797
debug = 0
noti = 1


# -- message client
async def tcp(host, msg):
    try:
        # connect to server
        client, server = await asyncio.open_connection(host, port)
        # send message
        server.write(msg.encode("utf8"))
        await server.drain()
        if debug:
            print("SERVER:", server.get_extra_info("peername"), "\nTCP_MSG_OUT:", msg)
        # wait for response
        answer = (await asyncio.wait_for(client.read(50), timeout=3)).decode("utf8")
        if debug:
            print("TCP_MSG_IN:", answer)
        # terminate connection
        server.close()
        await server.wait_closed()
        return answer
    except asyncio.TimeoutError:
        print("[TIMEOUT] no answer from:", host)
        _exit(1)


# -- desktop notification
def notify(name, volume, mute, solo):
    try:
        from gi import require_version
        require_version("Notify", "0.7")
        from gi.repository import Notify
        # icons
        if volume == 0 or mute == "On":
            icon = "audio-volume-muted"
        elif volume > 99:
            icon = "audio-volume-high"
        elif volume > 49:
            icon = "audio-volume-medium"
        elif volume > 0:
            icon = "audio-volume-low"
        # ascii slider
        slider_vol = int((volume + 1) / 8)
        if slider_vol < 1:
            slider_vol = 1
        if slider_vol > 16:
            slider_vol = 16
        slider = ""
        for i in range(15 + 1):
            if i + 1 == slider_vol:
                slider += "█"
            else:
                slider += "🭹"
        # setup notify
        Notify.init("Jack | " + name)
        body = "ⓥ " + str(volume) + " ┃ ⓜ " + mute + " ┃ ⓢ " + solo
        popup = Notify.Notification.new(slider, body, icon)
        popup.props.id = 777  # only one instance
        popup.set_urgency(0)
        popup.set_timeout(2000)
        popup.show()
    except BaseException:
        pass


# -- main
try:
    # parse cli parameters
    name = ""
    control = ""
    options, values = getopt.getopt(argv[1:], "hnv:i:d:m:s:", ["help", "debug", "host="])
    for opt, val in options:
        if opt in ("-h", "--help"):
            print(info)
            _exit(0)
        elif opt == "--debug":
            debug = 1
        elif opt == "--host":
            host = val
        elif opt == "-n":
            noti = 0
        elif opt == "-v":
            try:
                name, volume = val.split(",")
                if int(volume) or volume == "0":
                    control = "1v," + volume
            except BaseException:
                print("input format: -v <channel name>,<volume>")
                _exit(0)
        elif opt == "-i":
            control = "1i"
            name = val
        elif opt == "-d":
            control = "1d"
            name = val
        elif opt == "-m":
            control = "2"
            name = val
        elif opt == "-s":
            control = "3"
            name = val
    if not len(argv[1:]) or not name or not control:
        print(info)
        _exit(0)
    # send tcp message
    msg = name + "⚏" + control
    answer = asyncio.run(tcp(host, msg))
    if noti:
        # show notification
        name, volume, mute, solo = answer.split("⚏")
        notify(name, int(volume), mute, solo)
except getopt.GetoptError:
    print(info)
    _exit(0)
except KeyboardInterrupt:
    print("[keyboard interrupt received]")
except BaseException as e:
    print("[ERROR]", e)
