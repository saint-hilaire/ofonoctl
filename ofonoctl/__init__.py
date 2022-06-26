#!/usr/bin/env python3
import os
import subprocess
import time
import ipaddress
import dbus
import dbus.mainloop.glib
import sys
import argparse
import re
import tempfile

import tabulate

from gi.repository import GLib

bus = None
manager = None


def fatal(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
    exit(1)


def set_property_wait(interface, property, value, timeout=10):
    interface.SetProperty(property, value, timeout=120)
    for i in range(0, timeout):
        state = interface.GetProperties()
        if state[property] == value:
            return True
        time.sleep(1)
    return False


def init():
    global bus, manager
    try:
        bus = dbus.SystemBus()
    except Exception as e:
        fatal(e)

    try:
        manager = dbus.Interface(bus.get_object('org.ofono', '/'), 'org.ofono.Manager')
    except dbus.exceptions.DBusException:
        fatal("Could not aquire org.ofono.Manager on dbus")


def action_list():
    init()
    global manager, bus
    modems = manager.GetModems()

    result = []

    if len(modems) == 0:
        print("No modems found")
        return

    for path, properties in modems:
        model = path[1:]
        powered = False
        online = False
        if 'Powered' in properties:
            powered = properties['Powered'] == 1

        if 'Online' in properties:
            online = properties['Online'] == 1

        try:
            registration_interface = dbus.Interface(bus.get_object('org.ofono', path), 'org.ofono.NetworkRegistration')
            properties = registration_interface.GetProperties()
            status = str(properties["Status"])
            network_name = str(properties["Name"])
            if status == "searching":
                registration = "Searching"
            elif status == "denied":
                registration = "Denied"
            elif status == "registered":
                strength = float(properties["Strength"])
                registration = "Registered to {} ({}%)".format(network_name, strength)
            else:
                registration = "{}, {}".format(status, network_name)
        except dbus.exceptions.DBusException:
            registration = "Unregistered"

        try:
            sim_manager = dbus.Interface(bus.get_object('org.ofono', path), 'org.ofono.SimManager')
            properties = sim_manager.GetProperties()
            if properties['Present'] == 1:
                if 'ServiceProviderName' in properties:
                    sim = properties['ServiceProviderName']
                else:
                    sim = 'Unknown'
            else:
                sim = "No SIM"
        except dbus.exceptions.DBusException:
            sim = "Unknown"

        if not powered:
            result.append([model, "Unpowered", sim])
            continue

        if not online:
            result.append([model, "Offline", sim])
            continue

        result.append([model, registration, sim])

    print(tabulate.tabulate(result, headers=["Modem", "Status", "SIM"]))


def action_power(component, state, command):
    message = {
        'poweron': ["Powered on {}", "Could not power on {}"],
        'poweroff': ["Powered off {}", "Could not power off {}"],
        'online': ["Brought {} online", "Could not online {}"],
        'offline': ["Took {} offline", "Could not offline {}"]
    }

    init()
    global manager, bus
    modems = manager.GetModems()

    if len(modems) == 0:
        print("No modems found")
        exit(1)

    if component == 'Online' and state:
        powered = modems[0][1]['Powered'] == 1
        if not powered:
            print("Trying to online a modem that's not powered on. Running power on first...")
            action_power('Powered', True, 'poweron')

    for path, properties in modems:
        model = path[1:]
        modem = dbus.Interface(bus.get_object('org.ofono', path), 'org.ofono.Modem')
        if set_property_wait(modem, component, dbus.Boolean(1 if state else 0)):
            print(message[command][0].format(model))
            return
        else:
            fatal(message[command][1].format(model))


def action_scan_operators():
    init()
    global manager, bus
    modems = manager.GetModems()
    if len(modems) == 0:
        print("No modems found")
        exit(1)
    modem = modems[0][0]

    netreg = dbus.Interface(bus.get_object('org.ofono', modem), 'org.ofono.NetworkRegistration')

    print("Scanning for operators... (100 seconds)")

    operators = netreg.Scan(timeout=100)
    result = []
    for _, properties in operators:
        tech = ", ".join(list(properties['Technologies']))
        result.append([properties['Name'], properties['Status'], tech, properties['MobileCountryCode']])

    print(tabulate.tabulate(result, headers=['Operator', 'Status', 'Technology', 'MCC']))


def action_wan(connect=False, resolv=False):
    init()
    global manager, bus
    modems = manager.GetModems()
    if len(modems) == 0:
        print("No modems found")
        exit(1)
    modem = modems[0][0]

    if 'Powered' in modems[0][1]:
        powered = modems[0][1]['Powered'] == 1
        if not powered:
            print("The modem is not powered, can't control WAN settings")
            print("You can power on the modem using ofonoctl poweron")
            exit(1)

    if 'Online' in modems[0][1]:
        online = modems[0][1]['Online'] == 1
        if not online:
            print("The modem is offline, can't control WAN settings")
            print("You can bring the modem online using ofonoctl online")
            exit(1)

    connman = dbus.Interface(bus.get_object('org.ofono', modem), 'org.ofono.ConnectionManager')
    try:
        contexts = connman.GetContexts()
    except dbus.exceptions.DBusException:
        print("Could not fetch contexts on the modem")
        exit(1)

    has_flushed = False

    result = []
    for path, properties in contexts:
        settings4 = properties['Settings']
        settings6 = properties['IPv6.Settings']
        if "Method" in settings4:
            s = settings4

            if connect and not has_flushed:
                cmd = ['ip', 'addr', 'flush', 'dev', s['Interface']]
                subprocess.check_output(cmd)
                has_flushed = True

            address = s["Address"] if s["Method"] == "static" else ""
            gateway = s["Gateway"] if s["Method"] == "static" else ""
            dns = ", ".join(s["DomainNameServers"]) if s["Method"] == "static" else ""
            if len(address) > 0:
                address += "/" + str(ipaddress.IPv4Network('0.0.0.0/{}'.format(s["Netmask"])).prefixlen)
            result.append([s["Interface"], "ipv4", properties["AccessPointName"], s["Method"], address, gateway, dns])

            if connect and s["Method"] == "static":
                cmd = ['ip', 'addr', 'add', address, 'dev', s["Interface"]]
                subprocess.check_output(cmd)
                cmd = ['ip', 'route', 'add', 'default', 'via', gateway, 'dev', s["Interface"]]
                subprocess.check_output(cmd)
            if resolv and s["Method"] == "static":
                update_resolvconf(s["DomainNameServers"])

        if "Method" in settings6:
            s = settings6

            if connect and not has_flushed:
                cmd = ['ip', 'addr', 'flush', 'dev', s['Interface']]
                subprocess.check_output(cmd)
                has_flushed = True

            address = s["Address"] if s["Method"] == "static" else ""
            gateway = s["Gateway"] if s["Method"] == "static" else ""
            dns = ", ".join(s["DomainNameServers"]) if s["Method"] == "static" else ""
            result.append([s["Interface"], "ipv6", properties["AccessPointName"], s["Method"], address, gateway, dns])

    print(tabulate.tabulate(result, headers=["Interface", "Protocol", "APN", "Method", "Address", "Gateway", "DNS"]))


def action_sms(destination, message=None):
    init()
    global manager, bus
    modems = manager.GetModems()
    if len(modems) == 0:
        print("No modems found")
        exit(1)
    modem = modems[0][0]

    if message is None:
        editor = 'nano'
        if 'EDITOR' in os.environ:
            editor = os.environ['EDITOR']
        if 'VISUAL' in os.environ:
            editor = os.environ['VISUAL']

        buffer = tempfile.NamedTemporaryFile(suffix='.txt', prefix='sms-')
        subprocess.call([editor, buffer.name])
        buffer.seek(0)
        message = buffer.read().decode().strip()
        buffer.close()

    if len(message) == 0:
        print("Message empty. Aborting...")
        exit(1)

    mm = dbus.Interface(bus.get_object('org.ofono', modem), 'org.ofono.MessageManager')
    mm.SendMessage(destination, message)
    print("Sent")


def action_sms_get():
    init()
    global manager, bus
    modems = manager.GetModems()
    if len(modems) == 0:
        print("No modems found")
        exit(1)
    modem = modems[0][0]

    mm = dbus.Interface(bus.get_object('org.ofono', modem), 'org.ofono.MessageManager')
    messages = mm.GetMessages()
    print(messages)


def update_resolvconf(nameservers):
    with open('/etc/resolv.conf') as handle:
        current = handle.read()

    header = 'DNS servers set by ofonoctl'
    regex = r"# {}.+# end\n".format(header)

    new_block = '# {}\n'.format(header)
    for ns in nameservers:
        new_block += 'nameserver {}\n'.format(ns)
    new_block += '# end\n'

    if header in current:
        new_file = re.sub(regex, new_block, current, flags=re.MULTILINE | re.DOTALL)
    else:
        new_file = current + '\n' + new_block

    with open('/etc/resolv.conf', 'w') as handle:
        handle.write(new_file)

def incoming_message(message, details, path, interface):
    print("%s" % (message.encode('utf-8')))

    for key in details:
        val = details[key]
        print("    %s = %s" % (key, val))

def action_receive_sms():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    bus.add_signal_receiver(incoming_message, bus_name="org.ofono",
        signal_name = "ImmediateMessage", path_keyword="path",
        interface_keyword="interface")

    bus.add_signal_receiver(incoming_message, bus_name="org.ofono",
        signal_name = "IncomingMessage", path_keyword="path",
        interface_keyword="interface")

    mainloop = GLib.MainLoop()
    mainloop.run()

def main():
    parser = argparse.ArgumentParser(description="Ofono control tool")
    sub = parser.add_subparsers(title="action", dest="action")
    sub.add_parser('list', help="List modems")
    sub.add_parser('poweron', help="Enable power to modem")
    sub.add_parser('poweroff', help="Disable power to modem")
    sub.add_parser('online', help="Enable modem")
    sub.add_parser('offline', help="Disable modem")
    sub.add_parser('operators', help="Display operator info")
    parser_wan = sub.add_parser('wan', help="Control internet access")
    parser_wan.add_argument('--connect', help="Bring up first connection", action="store_true")
    parser_wan.add_argument('--append-dns', help="Add the providers DNS servers to /etc/resolv.conf",
                            dest="resolv", action="store_true")
    parser_sms = sub.add_parser('sms', help="Send sms message")
    parser_sms.add_argument('--message', '-m', help="The message, if left out your editor will be opened")
    parser_sms.add_argument('destination', help="Destination number for the message")
    sub.add_parser('sms-list', help="List stored SMS messages")
    sub.add_parser('receive-sms', help="Receive incoming SMS messages")

    args = parser.parse_args()

    if args.action is None or args.action == "list":
        action_list()
        return

    if args.action == "poweron":
        action_power('Powered', True, 'poweron')
        return

    if args.action == "poweroff":
        action_power('Powered', True, 'poweroff')
        return

    if args.action == "online":
        action_power('Online', True, 'online')
        return

    if args.action == "offline":
        action_power('Online', True, 'offline')
        return

    if args.action == "operators":
        action_scan_operators()
        return

    if args.action == "wan":
        action_wan(args.connect, args.resolv)
        return

    if args.action == "sms":
        action_sms(args.destination, args.message)
        return

    if args.action == "sms-list":
        action_sms_get()
        return

    if args.action == "receive-sms":
        action_receive_sms()
        return

if __name__ == '__main__':
    main()
