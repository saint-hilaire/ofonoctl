#!/usr/bin/env python3
import subprocess
import time
import ipaddress
import dbus
import sys
import argparse

import tabulate

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
    modem = manager.GetModems()[0][0]
    netreg = dbus.Interface(bus.get_object('org.ofono', modem), 'org.ofono.NetworkRegistration')

    print("Scanning for operators... (100 seconds)")

    operators = netreg.Scan(timeout=100)
    result = []
    for _, properties in operators:
        tech = ", ".join(list(properties['Technologies']))
        result.append([properties['Name'], properties['Status'], tech, properties['MobileCountryCode']])

    print(tabulate.tabulate(result, headers=['Operator', 'Status', 'Technology', 'MCC']))


def action_wan(connect=False):
    init()
    global manager, bus
    modem = manager.GetModems()[0][0]
    connman = dbus.Interface(bus.get_object('org.ofono', modem), 'org.ofono.ConnectionManager')
    result = []
    for path, properties in connman.GetContexts():
        settings4 = properties['Settings']
        settings6 = properties['IPv6.Settings']
        if "Method" in settings4:
            s = settings4
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

        if "Method" in settings6:
            s = settings6
            address = s["Address"] if s["Method"] == "static" else ""
            gateway = s["Gateway"] if s["Method"] == "static" else ""
            dns = ", ".join(s["DomainNameServers"]) if s["Method"] == "static" else ""
            result.append([s["Interface"], "ipv6", properties["AccessPointName"], s["Method"], address, gateway, dns])

    print(tabulate.tabulate(result, headers=["Interface", "Protocol", "APN", "Method", "Address", "Gateway", "DNS"]))


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
        action_wan(args.connect)
        return


if __name__ == '__main__':
    main()
