#!/usr/bin/env python3
"""Take screenshot using XDG Desktop Portal. Run standalone, not inside async code."""
import sys
import dbus
import uuid
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop
import os

# Ensure DBus session bus is available
if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"

DBusGMainLoop(set_as_default=True)

bus = dbus.SessionBus()
portal = bus.get_object(
    'org.freedesktop.portal.Desktop',
    '/org/freedesktop/portal/desktop'
)
iface = dbus.Interface(portal, 'org.freedesktop.portal.Screenshot')

token = str(uuid.uuid4()).replace('-', '_')
sender = bus.get_unique_name()[1:].replace('.', '_')
request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

result_uri = [None]

def response_handler(response, results):
    if response == 0:
        result_uri[0] = str(results.get('uri', ''))
    loop.quit()

bus.add_signal_receiver(
    response_handler,
    signal_name='Response',
    dbus_interface='org.freedesktop.portal.Request',
    path=request_path
)

loop = GLib.MainLoop()

iface.Screenshot('', {
    'interactive': dbus.Boolean(False, variant_level=1),
    'handle_token': dbus.String(token, variant_level=1),
})

# Timeout after 15 seconds
GLib.timeout_add_seconds(15, loop.quit)
loop.run()

if result_uri[0]:
    uri = result_uri[0].replace('file://', '')
    print(uri)
    sys.exit(0)
else:
    print("FAILED", file=sys.stderr)
    sys.exit(1)
