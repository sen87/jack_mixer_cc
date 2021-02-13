# jack_mixer_cc

## About
[jack_mixer](https://github.com/jack-mixer/jack_mixer) companion that provides a CLI for channel adjustments.
<br>Creates a [JACK](https://jackaudio.org)-client that controls jack_mixer via MIDI Control Change Messages.


## Features
- **`Volume Control`** increase, decrease and set to value
- **`toggle Mute`**
- **`toggle Solo Mode`**
- **`Persistance`** autosave/restore all channel states
- **`Remote Control`** client can send TCP control messages over the network 
- **`Desktop Notifications`** client-side OSD (channel state)


## Use Cases
- **`CLI`** command line access to jack_mixer channel controls
- **`Keyboard Shortcuts`** can be used (with [xbindkeys](https://www.nongnu.org/xbindkeys/xbindkeys.html) for example) to control JACK volume via multimedia keys
- **`Scripts`** automate channel states
- **`Example`** the scripts could probably be easily adapted to control other JACK-clients via MIDI CC


## Dependencies
jack_mixer_cc.py: `python python-jack-client jack_mixer`
<br>jack_mixer_cc_client.py: `python` | Optional: `python-dbus` (for notifications)


## Howto
1. Start jack_mixer and save your configuration to ~/.config/jack_mixer/config.xml
2. Start jack_mixer_cc (use the "-c" parameter if you saved your jack_mixer config somewhere else).
<br>`python jack_mixer_cc.py`
3. Connect the jack_mixer and jack_mixer_cc MIDI ports.
<br><img src="https://user-images.githubusercontent.com/16217416/106959180-a17cb200-673a-11eb-81ac-22f53e7763b1.jpg"/>
4. Use the jack_mixer_cc_client to change something. For example: increase the volume of the channel "MPD"
<br>`python jack_mixer_cc_client.py --notify d -i mpd`
5. You should see a notification like this:
<br><img src="https://user-images.githubusercontent.com/16217416/107836482-927eab00-6d9d-11eb-911a-062cb2621692.png"/>
___
### Remote control
Run jack_mixer_cc with the LAN IP from your JACK system. For example: 192.168.1.10 
<br>`python jack_mixer_cc.py --ip 192.168.1.10`
<br> Then, from another system, connect with the client to this IP:
<br>`python jack_mixer_cc_client.py --host 192.168.1.10 --notify d -m mpd`
___
### Native desktop notifications
__gnome shell:__ `python jack_mixer_cc_client.py --notify g -i mpd`
<br><img src="https://user-images.githubusercontent.com/16217416/107836487-93afd800-6d9d-11eb-9b73-7ba80f08f83d.png"/>

<br>__plasma (kde):__ `python jack_mixer_cc_client.py --notify p -i mpd`
<br><img src="https://user-images.githubusercontent.com/16217416/107836488-93afd800-6d9d-11eb-8bb6-e0edc567ecfc.png"/>
___
The `-h|--help` parameter should help you figure out the rest.


## Known Issue
If you start your JACK session in an automated way and use something that autoconnects all ports (like the [QjackCtl Patchbay](https://www.rncbc.org/drupal/node/76)) the channel states might not be restored (or only partially).
<br>The script waits until all MIDI-ports of the JACK-client are connected before the session is restored but it seems that there is a (small) delay until MIDI messages are getting parsed. If this is caused by jack_mixer or JACK itself I don't know (seems inconsistent or dependent on system load).
<br>The lazy fix for this is to start jack_mixer_cc delayed. See the included example scripts under `example_start+stop_scripts/`.
