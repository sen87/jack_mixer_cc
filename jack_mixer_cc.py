#!/usr/bin/python
# -*- coding: utf-8 -*-
# sen <sen@archlinux.us>
# --- dependencies
# jack_mixer python-jack-client
# --- optional dependencies
# pipewire
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
│ v0.3
├──────────────────────────────────────────────────────────
│ Options:
│ --debug        debug mode
│ --ip <LAN IP>  to allow remote control
│                  > defaults to localhost
│ -c <FILE>      jack_mixer config
│                  > ~/.config/jack_mixer/config.xml
│ -s <FILE>      jack_mixer_cc session
│                  > ~/.config/jack_mixer/jack_mixer_cc.xml
│ -S             no persistance (disable session)
│ --step <VAL>   volume in-/decrease value
│                  > default is 2
├──────────
│ PipeWire Control:     (pw-cli dump short Node |grep alsa)
│ --pw <jm_channel_name>,<pw_node_name>
└──────────────────────────────────────────────────────────\n"""
# --- settings
debug = 0
ip = "localhost"
port = 9797
jm_config = "~/.config/jack_mixer/config.xml"
session = 1
s_file = "~/.config/jack_mixer/jack_mixer_cc.xml"
s_file_tmp = "/dev/shm/jack_mixer_cc.xml"
vol_step = 2
vol_range = (0, 127)
# --- internals
jack_client = jack.Client("jack_mixer_cc")
midi_in = jack_client.midi_inports.register("midi_in")
midi_out = jack_client.midi_outports.register("midi_out")
jack_conn = [0, 0, 0] # [session, midi_in, midi_out]
jack_ipc_buffer = [] # (176, cc, val)
activity = 0 # trigger session save
chan_map = [] # [name, [cc, vol], [cc, mute], [cc, solo], pw_node]
pw = [] # [mixer_channel, node_name, node_id]


# -- parse jack_mixer config
def map_channels():
    try:
        global chan_map
        root = et.parse(expanduser(jm_config)).getroot()
        for child in root.iter():
            if "put_channel" in child.tag: # select INput_channel and OUTput_channel
                name = (child.get("name")).casefold()
                vol_cc = int(child.get("volume_midi_cc"))
                mute_cc = int(child.get("mute_midi_cc"))
                solo_cc = int(child.get("solo_midi_cc") or 0)
                pw_node = ""
                if pw: # setup pipewire trigger
                    for node in pw:
                        if name == node[0].casefold():
                            pw_node = node[2]
                chan_map.append([name, [vol_cc, 0], [mute_cc, 0], [solo_cc, 0], pw_node])
        if debug:
            print("CHAN_MAP:", chan_map)
    except BaseException:
        print("[ERROR] could not load jack_mixer config from:", jm_config)
        _exit(1)


# -- jack client
@jack_client.set_process_callback
def process(frames):
    global jack_ipc_buffer, activity
    # - midi out
    midi_out.clear_buffer()
    for msg in jack_ipc_buffer:
        try:
            midi_out.write_midi_event(0, msg)
            if debug:
                print("MIDI_MSG_OUT:", msg)
        except jack.JackError as e:
            print("[JACK_ERROR]", e)
    jack_ipc_buffer.clear()
    # - midi in
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
        if jack_conn[1] and jack_conn[2]: # midi ports connected
            jack_conn[0] = 1
            load_session()


# -- message server
async def tcp(server, client):
    # - wait for a client
    msg = (await server.read(50)).decode("utf8")
    if debug:
        print("CLIENT:", client.get_extra_info("peername"), "\nTCP_MSG_IN:", msg)
    # - parse message
    name, control = msg.split("⚏")
    n, vol, mute, solo = set_state(name, control)
    # - send response to client
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
    # - terminate connection
    client.close()
    await client.wait_closed()


# -- states
def set_state(name, control):
    global jack_ipc_buffer, chan_map
    cont_id = int(control[0])
    state = ["unknown channel", 0, 0, 0]
    for chan in chan_map:
        if chan[0] == name: # channel matched
            state[0] = name
            for prop in range(1, 3 + 1): # get current state
                state[prop] = chan[prop][1]
                if prop == 1 and cont_id == 1: # volume
                    if control[1] == "v":
                        state[1] = int(control[3:])
                    elif control[1] == "i":
                        state[1] += vol_step
                    elif control[1] == "d":
                        state[1] -= vol_step
                    if state[1] < vol_range[0]: # lower volume limit
                        state[1] = vol_range[0]
                    elif state[1] > vol_range[1]: # upper volume limit
                        state[1] = vol_range[1]
                    msg = (176, chan[1][0], state[1])
                elif cont_id == prop:
                    if control[1] == "m": # mute
                        state[prop] = 127
                    elif control[1] == "u": # unmute
                        state[prop] = 0
                    elif control[1] == "t": # toggle mute / solo
                        if state[prop] == 127:
                            state[prop] = 0
                        else:
                            state[prop] = 127
                    msg = (176, chan[prop][0], state[prop])
            if debug:
                print("SET_STATE:", state)
            jack_ipc_buffer.append(msg) # queue midi cc
            return state
    return state

def save_state(cc, val):
    global chan_map
    for chan in chan_map:
        for prop in range(1, 3 + 1):
            if chan[prop][0] == cc: # update channel map
                chan[prop][1] = val
                if chan[4] and prop in (1, 2): # update pipewire
                        pipewire_control(chan[4], prop, val)
                if debug:
                    print("SAVE_STATE: CC=" + str(cc), "VAL=" + str(val) + "\n---")
                return


# -- session
def load_session():
    try:
        global jack_ipc_buffer
        root = et.parse(expanduser(s_file)).getroot()
        for child in root.iter(): # restore state from xml
            cc = int(child.get("cc") or 0)
            if cc:
                val = int(child.get("val") or 0)
                save_state(cc, val) # manual sync --> midi response only on mixer change
                msg = (176, cc, val)
                jack_ipc_buffer.append(msg) # queue midi cc
        if debug:
            print("SESSION: restored from:", s_file)
    except BaseException:
        print("[INFO] session could not be restored.")

async def save_session_tmp():
    try: # on change create session file and save to ramdisk
        global activity
        while True: # look for activity every 10 seconds
            await asyncio.sleep(10)
            if activity:
                activity = 0
                # - create xml
                root = et.Element("jack_mixer_cc", modified=datetime.now().strftime("%c"))
                for chan in chan_map:
                    for prop in range(1, 3 + 1):
                        channel = int(chan[prop][0] or 0)
                        if channel:
                            et.SubElement(root, "channel", cc=str(channel), val=str(chan[prop][1]))
                # - write xml
                tree = et.ElementTree("tree")
                tree._setroot(root)
                tree.write(expanduser(s_file_tmp), encoding="UTF-8", xml_declaration=True)
                if debug:
                    print("SESSION: saved to:", s_file_tmp)
    except BaseException as e:
        print("[ERROR] session could not be saved:", e)

def save_session(sig, frame):
    try: # copy session file from ramdisk to home folder
        copy(s_file_tmp, expanduser(s_file))
        if debug:
            print("SIGNAL_RECEIVED:", sig, "\nSESSION: saved to", s_file)
        _exit(0)
    except BaseException as e:
        print("[ERROR] session could not be saved:", e)


# -- pipewire
def pipewire_init():
    try: # get the id numbers for pw nodes
        global pw
        for node in pw:
            pw_node = run(["pw-cli", "ls", node[1]], capture_output=True, text=True).stdout
            if not pw_node:
                raise Exception("Device not found: " + node[1])
                break
            node[2] = str(re.findall("id\\s([0-9]*)", pw_node)[0]) # get node_id
            if debug:
                print("PW_INIT: node <" + node[1] + "> has id: " + node[2])
    except BaseException as e:
        print("[ERROR] PipeWire could not be initialized:", e)
        _exit(1)

def pipewire_control(node, cc, val):
    try: # change node properties: pw-cli enum-params <node_id> Props
        if cc == 1: # volume
            vol = str(float((val / 127) ** 3))
            prop = "volume:" + vol + ", monitorVolumes:[" + vol + ", " + vol + "]"
        else: # mute
            if val:
                sw = "true"
            else:
                sw = "false"
            prop = "mute:" + sw + ", monitorMute:" + sw
        run(["pw-cli", "set-param " + node + " Props { " + prop + " }"], stdin=DEVNULL, stdout=DEVNULL, check=True)
        if debug:
            print("PW_CONTROL: NODE=" + node, "CC=" + str(cc), "VAL=" + str(val), "PROP=" + prop)
    except BaseException as e:
        print("[ERROR] PipeWire control failed:", e)


# -- main
try: # parse cli parameters
    options, values = getopt.getopt(argv[1:], "hc:s:S", ["help", "debug", "ip=", "step=", "pw="])
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
        elif opt == "-S":
            session = 0
        elif opt == "--step":
            vol_step = int(val)
        elif opt == "--pw":
            try:
                pw_map, pw_dev = val.split(",")
                pw.append([pw_map, pw_dev, 0])
            except BaseException:
                print('[PARAMETER ERROR] PipeWire example: --pw "mic,alsa_input.usb-MICROPHONE"')
                _exit(1)
    if pw: # setup pipewire control
        from subprocess import run
        from subprocess import DEVNULL
        import re
        pipewire_init()
    map_channels()
    jack_client.activate()
    loop = asyncio.new_event_loop()
    loop.create_task(asyncio.start_server(tcp, ip, port))
    if session: # setup session management
        import atexit
        import signal
        from datetime import datetime
        from shutil import copy
        loop.create_task(save_session_tmp())
        atexit.register(save_session, None, None)
        signal.signal(signal.SIGTERM, save_session)
    loop.run_forever() # start event loop
except getopt.GetoptError:
    print(info)
    _exit(0)
except KeyboardInterrupt:
    print("[keyboard interrupt received]")
except BaseException as e:
    print("[ERROR]", e)
