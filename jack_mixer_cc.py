#!/usr/bin/python
# -*- coding: utf-8 -*-
# sen <sen@archlinux.us>
# --- dependencies
# python-jack-client
# --- imports
from sys import argv
import getopt
from os import _exit
from os.path import expanduser
import asyncio
import jack
from struct import unpack
import xml.etree.ElementTree as et
# ----------------------
info = """
┌──────────────────────────────────────────────────────────
│ jack_mixer MIDI CC Controller
│ v0.1
├──────────────────────────────────────────────────────────
│ Options:
│ --debug        debug mode
│ --ip <LAN IP>  to allow remote control
│                  > defaults to localhost
│ -c <FILE>      jack_mixer config
│                  > ~/.config/jack_mixer/config.xml
│ -s <FILE>      jack_mixer_cc session
│                  > ~/.config/jack_mixer/jack_mixer_cc.xml
│ -n             no persistance (disable session)
│ --step <VAL>   volume in-/decrease value
│                  > default is 3
└──────────────────────────────────────────────────────────\n"""
# --- settings
debug = 0
ip = "localhost"
port = 9797
jm_config = "~/.config/jack_mixer/config.xml"
session = 1
s_file = "~/.config/jack_mixer/jack_mixer_cc.xml"
s_file_tmp = "/dev/shm/jack_mixer_cc.xml"
vol_step = 3
# --- internals
jack_client = jack.Client("jack_mixer_cc")
midi_in = jack_client.midi_inports.register("midi_in")
midi_out = jack_client.midi_outports.register("midi_out")
jack_conn = [0, 0, 0]
jack_ipc_buffer = []
activity = 0
chan_map = [["", [0, 0], [0, 0], [0, 0]]]


# -- parse jack_mixer config
def map_channels():
    try:
        global chan_map
        root = et.parse(expanduser(jm_config)).getroot()
        for child in root.iter():
            # select input_channel and output_channel
            if "put_channel" in child.tag:
                name = (child.get("name")).casefold()
                vol_cc = int(child.get("volume_midi_cc"))
                mute_cc = int(child.get("mute_midi_cc"))
                solo_cc = int(child.get("solo_midi_cc") or 0)
                chan_map.append([name, [vol_cc, 0], [mute_cc, 0], [solo_cc, 0]])
        if debug:
            print("CHAN_MAP:", chan_map)
    except BaseException:
        print("[ERROR] could not load jack_mixer config from:", jm_config)
        _exit(1)


# -- jack client
@jack_client.set_process_callback
def process(frames):
    # midi out
    global jack_ipc_buffer, activity
    midi_out.clear_buffer()
    for msg in jack_ipc_buffer:
        try:
            midi_out.write_midi_event(0, msg)
            if debug:
                print("MIDI_MSG_OUT:", msg)
        except jack.JackError as e:
            print("[JACK_ERROR]", e)
    jack_ipc_buffer.clear()
    # midi in
    for offset, data in midi_in.incoming_midi_events():
        msg = unpack("3B", data)
        if debug:
            print("MIDI_MSG_IN:", msg)
        save_state(int(msg[1]), int(msg[2]))
        if session:
            activity = 1


@jack_client.set_port_connect_callback
def port_connect(a, b, connect):
    global jack_conn
    if debug:
        print("JACK:", a, ["<<< DISC >>>", ">>> CONN <<<"][connect], b)
    if session and not jack_conn[0]:
        if "jack.OwnMidiPort" in str(a):
            jack_conn[1] = 1
        elif "jack.OwnMidiPort" in str(b):
            jack_conn[2] = 1
        if jack_conn[1] and jack_conn[2]:
            # midi ports connected
            jack_conn[0] = 1
            load_session()


# -- message server
async def tcp(server, client):
    # wait for a client
    msg = (await server.read(50)).decode("utf8")
    if debug:
        print("CLIENT:", client.get_extra_info("peername"), "\nTCP_MSG_IN:", msg)
    # parse message
    name, control = msg.split("⚏")
    n, vol, mute, solo = set_state(name, control)
    # send response to client
    answer = n.capitalize() + "⚏" + str(vol)
    for toggle in (mute, solo):
        if not toggle:
            answer += "⚏Off"
        else:
            answer += "⚏On"
    client.write(answer.encode("utf8"))
    if debug:
        print("TCP_MSG_OUT:", answer)
    await client.drain()
    # terminate connection
    client.close()
    await client.wait_closed()


# -- states
def set_state(name, control):
    global jack_ipc_buffer, chan_map
    state = ["unknown channel", 0, 0, 0]
    for chan in chan_map:
        if chan[0] == name:
            # channel matched
            state[0] = name
            cont_id = int(control[0])
            for cc in range(1, 3 + 1):
                # get current state
                state[cc] = chan[cc][1]
                if cc == 1 and cont_id == 1:
                    # change volume
                    if control[1] == "v":
                        state[1] = int(control[3:])
                    elif control[1] == "i":
                        state[1] += vol_step
                    elif control[1] == "d":
                        state[1] -= vol_step
                    # limits
                    if state[1] < 0:
                        state[1] = 0
                    elif state[1] > 127:
                        state[1] = 127
                    msg = (176, chan[1][0], state[1])
                elif cont_id == cc:
                    # toggle mute / solo
                    if state[cc] == 127:
                        state[cc] = 0
                    else:
                        state[cc] = 127
                    msg = (176, chan[cc][0], state[cc])
            if debug:
                print("SET_STATE:", state)
            # queue midi cc
            jack_ipc_buffer.append(msg)
            return state
    return state


def save_state(channel, val):
    global chan_map, activity
    for channels in chan_map:
        for cc in range(1, 3 + 1):
            if channels[cc][0] == channel:
                channels[cc][1] = val
                if debug:
                    print("SAVE_STATE: CC=" + str(channel), "VAL=" + str(val))
                return


# -- session
def load_session():
    try:
        global jack_ipc_buffer
        root = et.parse(expanduser(s_file)).getroot()
        for child in root.iter():
            cc = int(child.get("cc") or 0)
            if cc:
                val = int(child.get("val") or 0)
                # manual sync (there might be no midi response)
                save_state(cc, val)
                # queue midi cc
                msg = (176, cc, val)
                jack_ipc_buffer.append(msg)
        if debug:
            print("SESSION: restored from:", s_file)
    except BaseException:
        print("[INFO] session could not be restored.")


async def save_session_tmp():
    try:
        global activity
        while True:
            # look for activity every 10 seconds
            await asyncio.sleep(10)
            if activity:
                activity = 0
                # create xml
                root = et.Element("jack_mixer_cc", modified=datetime.now().strftime("%c"))
                for channels in chan_map:
                    for cc in range(1, 3 + 1):
                        channel = int(channels[cc][0] or 0)
                        if channel:
                            et.SubElement(root, "channel", cc=str(channel), val=str(channels[cc][1]))
                # write xml
                tree = et.ElementTree("tree")
                tree._setroot(root)
                tree.write(expanduser(s_file_tmp), encoding="UTF-8", xml_declaration=True)
                if debug:
                    print("SESSION: saved to:", s_file_tmp)
    except BaseException as e:
        print("[ERROR] session could not be saved:", e)


def save_session(sig, frame):
    try:
        # copy from /dev/shm to home folder
        copy(s_file_tmp, expanduser(s_file))
        if debug:
            print("SIGNAL_RECEIVED:", sig, "\nSESSION: saved to", s_file)
        _exit(0)
    except BaseException as e:
        print("[ERROR] session could not be saved:", e)


# -- main
try:
    # parse cli parameters
    options, values = getopt.getopt(argv[1:], "hc:s:n", ["help", "debug", "ip=", "step="])
    for opt, val in options:
        if opt in ("-h", "--help"):
            print(info)
            _exit(0)
        elif opt == "--debug":
            debug = 1
        elif opt == "--ip":
            ip = val
        elif opt == "-c":
            jm_config = val
        elif opt == "-s":
            s_file = val
        elif opt == "-n":
            session = 0
        elif opt == "--step":
            vol_step = int(val)
    map_channels()
    jack_client.activate()
    loop = asyncio.get_event_loop()
    loop.create_task(asyncio.start_server(tcp, ip, port))
    if session:
        # additional imports
        import atexit
        import signal
        from datetime import datetime
        from shutil import copy
        # temporary
        loop.create_task(save_session_tmp())
        # persistant
        atexit.register(save_session, None, None)
        signal.signal(signal.SIGTERM, save_session)
    # start loop
    loop.run_forever()
except getopt.GetoptError:
    print(info)
    _exit(0)
except KeyboardInterrupt:
    print("[keyboard interrupt received]")
except BaseException as e:
    print("[ERROR]", e)
