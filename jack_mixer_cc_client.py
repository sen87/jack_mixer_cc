#!/usr/bin/python
# -*- coding: utf-8 -*-
# sen <sen@praisethe.net>
# --- optional dependencies
# python-dbus
# --- imports
from sys import argv
import getopt
from os import _exit
import asyncio
# ----------------------
info = """
┌───────────────────────────────────────────────────
│ jack_mixer MIDI CC Controller
│ v0.4 (client)
├───────────────────────────────────────────────────
│ Options:
│ --debug                  debug mode
│ --host <IP>              remote control
│                            > defaults to localhost
│ --notify <TYPE>          d = default (freedesktop)
│                          g = gnome shell
│                          p = plasma (kde)
│                            > disabled by default
├──────────
│ Controls:
│ -v <chan name>,<volume>  set volume (0 - 127)
│ -i <chan name>           increase volume
│ -d <chan name>           decrease volume
│ -m <chan name>           mute
│ -u <chan name>           unmute
│ -t <chan name>           toggle mute
│ -s <chan name>           toggle solo mode
└───────────────────────────────────────────────────\n"""
# --- settings
host = "localhost"
port = 9797
debug = 0
name = ""
control = ""
noti = ""


# -- message client
async def tcp(host, msg):
    try:
        # - connect to server
        client, server = await asyncio.open_connection(host, port)
        # - send message
        server.write(msg.encode("utf8"))
        await server.drain()
        if debug:
            print("SERVER:", server.get_extra_info("peername"), "\nTCP_MSG_OUT:", msg)
        # - wait for response
        answer = (await asyncio.wait_for(client.read(50), timeout=3)).decode("utf8")
        if debug:
            print("TCP_MSG_IN:", answer)
        # - terminate connection
        server.close()
        await server.wait_closed()
        return answer
    except asyncio.TimeoutError:
        print("[TIMEOUT] no answer from:", host)
        _exit(1)


# -- desktop notification
def dbus_notify(n_type, name, volume, mute, solo):
    try:
        vol_perc = int(volume / 1.27)
        # - icons
        icon = "audio-volume-"
        if vol_perc == 0 or mute == "On":
            icon += "muted"
        elif vol_perc > 70:
            icon += "high"
        elif vol_perc > 30:
            icon += "medium"
        else:
            icon += "low"
        # - send dbus msg
        if n_type == "g": # gnome shell
            dbus_object = bus.get_object("org.gnome.Shell", "/org/gnome/Shell")
            dbus_interface = dbus.Interface(dbus_object, "org.gnome.Shell")
            dbus_interface.ShowOSD({"icon": icon, "label": name + ": ⓜ " + mute + " | ⓢ " + solo, "level": vol_perc / 100})
        elif n_type == "p": # plasma (kde)
            if mute == "On":
                vol_perc = 0
            dbus_object = bus.get_object("org.kde.plasmashell", "/org/kde/osdService")
            dbus_interface = dbus.Interface(dbus_object, "org.kde.osdService")
            dbus_interface.mediaPlayerVolumeChanged(vol_perc, name, icon)
        else: # default (freedesktop spec)
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
            dbus_object = bus.get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications")
            dbus_interface = dbus.Interface(dbus_object, "org.freedesktop.Notifications")
            dbus_interface.Notify("Jack | " + name, 777, icon, slider, "ⓥ " + str(vol_perc) + "% ┃ ⓜ " + mute + " ┃ ⓢ " + solo, [], {}, 2000)
    except BaseException:
        pass


# -- main
try: # parse cli parameters
    options, values = getopt.getopt(argv[1:], "hv:i:d:m:u:t:s:", ["help", "debug", "host=", "notify="])
    for opt, val in options:
        if opt in ("-h", "--help"):
            print(info)
            _exit(0)
        elif opt == "--debug":
            debug = 1
        elif opt == "--host":
            host = val
        elif opt == "--notify":
            noti = val
        elif opt == "-v":
            try:
                name, volume = val.split(",")
                if int(volume) or volume == "0":
                    control = "1v," + volume
            except BaseException:
                print("[PARAMETER ERROR] volume example: -v test,50")
                _exit(0)
        elif opt == "-i":
            control = "1i"
            name = val
        elif opt == "-d":
            control = "1d"
            name = val
        elif opt == "-m":
            control = "2m"
            name = val
        elif opt == "-u":
            control = "2u"
            name = val
        elif opt == "-t":
            control = "2t"
            name = val
        elif opt == "-s":
            control = "3t"
            name = val
    if not len(argv[1:]) or not name or not control:
        print(info)
        _exit(0)
    # send tcp message
    msg = name + "⚏" + control
    answer = asyncio.run(tcp(host, msg))
    if noti: # setup notification
        import dbus
        bus = dbus.SessionBus()
        name, volume, mute, solo = answer.split("⚏")
        dbus_notify(noti, name, int(volume), mute, solo)
except getopt.GetoptError:
    print(info)
    _exit(0)
except KeyboardInterrupt:
    print("[keyboard interrupt received]")
except BaseException as e:
    print("[ERROR]", e)
