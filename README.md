# ofonoctl

This is a command line tool to control the ofono daemon over dbus, it's a substitute for calling the test scripts from the ofono git repository.

## Basic usage

There are two "switches" to control the device state in ofono, the`powered` and the `online` state. The first controls the
power to the modem and the second controls the radio state in the modem. The modem has to be powered first before it can be
set online.

```shell-session
$ ofonoctl list
Modem         Status     SIM
------------  ---------  -------
quectelqmi_0  Unpowered  Unknown

$ ofonoctl poweron
Powered on quectelqmi_0
$ ofonoctl list
Modem         Status    SIM
------------  --------  -------
quectelqmi_0  Offline   Unknown

$ ofonoctl online
Brought quectelqmi_0 online
$ ofonoctl list
Modem         Status                           SIM
------------  -------------------------------  ----------
quectelqmi_0  Registered to [network] (40.0%)  [provider]
```

To bring the modem down the commands are `offline` and `poweroff`

## Scanning operators

The `operators` command can be used to make the modem listen for operator beacons for 100 seconds and then list the status.

```shell-session
$ ofonoctl operators
Scanning for operators... (100 seconds)
Operator    Status     Technology        MCC
----------  ---------  --------------  -----
NL KPN      available  gsm, umts, lte    204
voda NL     forbidden  gsm, umts, lte    204
TMO NL      forbidden  gsm, umts, lte    204
Tele2       available  lte               204
```

## Data connection

The ofono daemon handles most of the data connection automagically, the only thing it doesn't do is assigning the ip address.
The APNs/contexts ofonoctl knows can be listed with the `wan` command.

```shell-session
$ ofonoctl wan
Interface    Protocol    APN       Method    Address            Gateway        DNS
-----------  ----------  --------  --------  -----------------  -------------  ------------------------------
wwan0        ipv4        INTERNET  static    10.115.256.210/30  10.115.79.209  194.151.256.18, 194.151.228.50
```

This shows that the interface ofono registered for the modem is `wwan0`. In my case the provider doesn't use DHCP on the
network but provides a static address. Ofonoctl can assign the address to the interface by specifying the `--connect` argument.
By default the provider DNS server isn't used, if you want to add the provider DNS servers to your /etc/resolv.conf you can
add the `--append-dns` option.

```shell-session
$ ofonoctl wan --connect --append-dns
```

After this you should have an internet connection.

## Sending SMS

The `sms` command can be used to send sms messages.

```shell-session
$ ofonoctl sms +31[number] -m "Hello World!"
Send
$ ofonoctl sms +31[number]
[your $EDITOR launches]
Send
```