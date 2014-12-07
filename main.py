# -*- coding: utf-8 -*-

# <config>
NICKNAME = "ferdus"
NSUSER = "ferdus"
NSPASSWORD = "iamsuperferdus"
IRCSERVER = "sinisalo.freenode.net"
CONTROLCHAN = "##wowsuchban"
BINDTO = "2001:1b40:5000:ff3::5:b00b"

TRUST = ["wikimedia/Polsaker"]
# </config>

import logging
from peewee import peewee
from irc import client
import base64
import time
import re
import json
import socket

# _USERDB[username]['channels'] = ['#list', '#of', '#channels']
_USERDB = {}
_PARROT = {}
_CONNECTED = False

logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig()

database = peewee.SqliteDatabase('ferdus.db')
database.connect()

connection = client.IRCClient("ferdus")
connection.configure(IRCSERVER, 6667, NICKNAME, NICKNAME, "realname", localaddress=BINDTO)

# ---- DATABASE STUFF ----

class BaseModel(peewee.Model):
    class Meta:
        database = database

class Channel(BaseModel):
    name = peewee.CharField()
    
class ChanFilter(BaseModel):
    Type = "channel"
    label = peewee.CharField(default="No label")
    content = peewee.CharField()
    hostmask = peewee.CharField()

class MsgFilter(BaseModel):
    Type = "message"
    label = peewee.CharField(default="No label")
    content = peewee.CharField()
    hostmask = peewee.CharField()

class HostMaskFilter(BaseModel):
    Type = "hostmask"
    label = peewee.CharField(default="No label")
    hostmask = peewee.CharField()

HostMaskFilter.create_table(True)
ChanFilter.create_table(True)
MsgFilter.create_table(True)
Channel.create_table(True)

# ---- IRC STUFF ----

def welcome(client, event): # When we're connected to the irc...
    _CONNECTED = True
    client.join(CONTROLCHAN) # ... we join the control channel
    for channel in Channel.select():
        client.join(channel.name)
    
def oconnect(client, event): # Phew, we're connecting to the server...
    # Let's try to do some SASL
    client.send("CAP REQ :sasl")
    client.send("AUTHENTICATE PLAIN")

def saslauth(client, event): # Finish sasl authentication
    client.send("AUTHENTICATE {0}".format(
        base64.b64encode("{0}\0{0}\0{1}".format(NSUSER, NSPASSWORD).encode()).decode()))
    client.send("CAP END")
    
def ctcp(cli, event):
    if event.arguments[0] == "VERSION":
        cli.notice(event.source, "\001VERSION HexChat 2.10.1 [x64] / Windows 7 SP1 [1.6GHz]\001")
    elif event.arguments[0] == "PING":
        cli.notice(event.source, "\001PING {0}\001".format(event.arguments[1]))
    elif event.arguments[0] == "AREYOUAWIZARD":
        cli.notice(event.source, "\001AREYOUAWIZARD Yes.\001")
        
def gotmsg(cli, event):
    if event.type == "ctcp" and event.arguments[0] == "ACTION" and client.is_channel(event.target) or _CONNECTED:
        return
    q = "a"
    if event.type[0] in ['a', 'e', 'i', 'o', 'u']:
        q = "an"
    cli.privmsg(CONTROLCHAN, "Got {3} \002{0}\002 from \037{1}\037 : {2}".format(event.type, event.source2, " ".join(event.arguments), q))

def publmsg(cli, ev):
    if ev.target == CONTROLCHAN:
        if not ev.source2.host in TRUST and ev.splitd[0][0] == ".":
            cli.privmsg(CONTROLCHAN, "I don't trust you")
            return
            
        if ev.splitd[0] == ".join":
            cli.join(ev.splitd[1])
            Channel.create(name=ev.splitd[1])
            cli.privmsg(CONTROLCHAN, "Joined \002{0}\002 and added it to the autojoin list".format(ev.splitd[1]))
        elif ev.splitd[0] == ".part":
            cli.part(ev.splitd[1], "Leaving")
            chan = Channel.get(Channel.name == ev.splitd[1])
            chan.delete_instance()
            cli.privmsg(CONTROLCHAN, "Parted \002{0}\002 and deleted it from the autojoin list".format(ev.splitd[1]))
        elif ev.splitd[0] == ".chanpattern" or ev.splitd[0] == ".cf":
            chanpattern(cli, ev)
        elif ev.splitd[0] == ".msgpattern" or ev.splitd[0] == ".mf":
            msgpattern(cli, ev)
        elif ev.splitd[0] == ".hostmakspattern" or ev.splitd[0] == ".hf":
            hostmaskpattern(cli, ev)
        elif ev.splitd[0] == ".label" or ev.splitd[0] == ".l":
            label(cli, ev)
        elif ev.splitd[0] == ".channels":
            cli.privmsg(CONTROLCHAN, " ".join(cli.channels))
        elif ev.splitd[0] == ".nicks":
            cli.privmsg(CONTROLCHAN, " ".join(cli.channels[ev.splitd[1]].users))
        elif ev.splitd[0] == ".msg":
            cli.privmsg(ev.splitd[1], " ".join(ev.splitd[2:]))
        elif ev.splitd[0] == ".notice":
            cli.notice(ev.splitd[1], " ".join(ev.splitd[2:]))
        elif ev.splitd[0] == ".raw":
            cli.send(" ".join(ev.splitd[1:]))
        elif ev.splitd[0] == ".quit":
            cli.disconnect("Leaving")
        elif ev.splitd[0] == ".parrot":
            if ev.splitd[1] == "on":
                _PARROT[ev.splitd[2]] = True
                cli.privmsg(CONTROLCHAN, "Enabled parrot mode for \002{0}\002".format(ev.splitd[2]))
            else:
                _PARROT[ev.splitd[2]] = False
                cli.privmsg(CONTROLCHAN, "Disabled parrot mode for \002{0}\002".format(ev.splitd[2]))
    try:
        if _PARROT[ev.target] is True:
            cli.privmsg(CONTROLCHAN, "[\002{0}\002] <{1}> {2}".format(ev.target, ev.source, ev.arguments[0]))
    except:
        pass
    if cli.nickname in ev.arguments[0] and ev.target != CONTROLCHAN:
        cli.privmsg(CONTROLCHAN, "Highlighted on \002{0}\002. Activating parrot mode for 5 minutes.".format(ev.target))
        cli.privmsg(CONTROLCHAN, "[\002{0}\002] <{1}> {2}".format(ev.target, ev.source, ev.arguments[0]))
        _PARROT[ev.target] = True
        time.sleep(300)
        cli.privmsg(CONTROLCHAN, "Parrot mode deactivated on \002{0}\002".format(ev.target))
        _PARROT[ev.target] = False
            
# --- command stuff ---

def label(cli, ev):
    try:
        ev.splitd[1]
    except:
        cli.privmsg(CONTROLCHAN, "Labels a filter. Usage: label <id> <label>")
        return
    if ev.splitd[1][0] == "c":
        filt = ChanFilter.get(ChanFilter.id == ev.splitd[1][1:])
    elif ev.splitd[1][0] == "m":
        filt = MsgFilter.get(MsgFilter.id == ev.splitd[1][1:])
    filt.label = " ".join(ev.splitd[2:])
    filt.save()
    cli.privmsg(CONTROLCHAN, "\002{0}\002 labeled.".format(ev.splitd[1]))

def chanpattern(cli, ev):
    try:
        ev.splitd[1]
    except:
        cli.privmsg(CONTROLCHAN, "Adds on-join filters. Usage: .chanpattern <add [hostmask regex] [channels (separated with spaces)]|del [id]|list>")
        return
        
    if ev.splitd[1] == "add":
        channels = json.dumps(ev.splitd[3:].lower().split())
        filt = ChanFilter.create(hostmask=ev.splitd[2], content=channels)
        cli.privmsg(CONTROLCHAN, "Filter created (ID: \002c{0}\002)".format(filt.id))
    elif ev.splitd[1] == "list":
        for filt in ChanFilter.select():
            content = json.loads(filt.content)
            cli.privmsg(CONTROLCHAN, "\002c{0}\002: {1} —— {3} (Hostmask: {2})".format(filt.id, " ".join(content), filt.hostmask, filt.label))
    elif ev.splitd[1] == "del":
        filt = ChanFilter.get(ChanFilter.id == ev.splitd[2])
        filt.delete_instance()
        cli.privmsg(CONTROLCHAN, "Filter deleted")

def msgpattern(cli, ev):
    try:
        ev.splitd[1]
    except:
        cli.privmsg(CONTROLCHAN, "Adds on-message filters. Usage: .msgpattern <add [hostmask regex] [message regex]|del [id]|list>")
        cli.privmsg(CONTROLCHAN, "Note: The message regex is prefixed and suffixed with .*")
        return
        
    if ev.splitd[1] == "add":
        filt = MsgFilter.create(hostmask=ev.splitd[2], content=".*" + " ".join(ev.splitd[3:]) + ".*")
        cli.privmsg(CONTROLCHAN, "Filter created (ID: \002m{0}\002)".format(filt.id))
    elif ev.splitd[1] == "list":
        for filt in MsgFilter.select():
            cli.privmsg(CONTROLCHAN, "\002m{0}\002: {1} —— {3} (Hostmask: {2})".format(filt.id, filt.content, filt.hostmask, filt.label))
    elif ev.splitd[1] == "del":
        filt = MsgFilter.get(MsgFilter.id == ev.splitd[2])
        filt.delete_instance()
        cli.privmsg(CONTROLCHAN, "Filter deleted")

def hostmaskpattern(cli, ev):
    try:
        ev.splitd[1]
    except:
        cli.privmsg(CONTROLCHAN, "Adds on-join hostmask filters. Usage: .hostmaskpattern <add [hostmask regex (nick!user@host)]|del [id]|list>")
        return
        
    if ev.splitd[1] == "add":
        filt = HostMaskFilter.create(hostmask=ev.splitd[2])
        cli.privmsg(CONTROLCHAN, "Filter created (ID: \002h{0}\002)".format(filt.id))
    elif ev.splitd[1] == "list":
        for filt in HostMaskFilter.select():
            cli.privmsg(CONTROLCHAN, "\002h{0}\002: {1} —— {2}".format(filt.id, filt.hostmask, filt.label))
    elif ev.splitd[1] == "del":
        filt = HostMaskFilter.get(HostMaskFilter.id == ev.splitd[2])
        filt.delete_instance()
        cli.privmsg(CONTROLCHAN, "Filter deleted")

# --- filter processing ---
def privmsgfilter(cli, ev):
    if ev.target == CONTROLCHAN:
        return
    for filt in MsgFilter.select():
        regex = re.compile(filt.hostmask)
        if re.search(regex, ev.source):
            regex2 = re.compile(filt.content)
            if re.search(regex2, ev.arguments[0]):
                # OMFGZ!!!!
                # WE GOT DAE TROLL
                kill_the_enemy(cli, ev, filt)
                # We leave the cooking and eating to a secondary bot
                #cook_the_enemy(...)
                #eat_the_cooked_enemy(...)
    
def joinfilter(cli, ev):
    # Hostmask filter:
    for filt in HostMaskFilter.select():
        regex = re.compile(filt.hostmask)
        if re.search(regex, ev.source):
            # MEEP MEEP MEEP MEEP MEEP MEEP MEEP
            # MEEP MEEP MEEP MEEP MEEP MEEP MEEP
            # MEEP MEEP MEEP MEEP MEEP MEEP MEEP
            # MEEP MEEP MEEP MEEP MEEP MEEP MEEP
            kill_the_enemy(cli, ev, filt)
            
    # Join filter
    try:
        _USERDB[ev.source]
        _USERDB[ev.source]['channels'].append(ev.target.lower())
    except:
        _USERDB[ev.source] = {}
        _USERDB[ev.source]['channels'] = [ev.target.lower()]
    
    for filt in ChanFilter.select():
        content = json.loads(filt.content)
        if set(_USERDB[ev.source]['channels']) == set(content) and ev.source.nick != cli.nickname:
            regex = re.compile(filt.hostmask)
            if re.search(regex, ev.source):
                # !!!!1 OMFG! ITZ A TROLL
                # EVERYTHING MATCHED
                # RED ALERT, RED ALERT: WE HAVE A TROLL IN THE CHANNEL
                # I REPEAT: WE HAVE A TROLL IN THE CHANNEL
                kill_the_enemy(cli, ev, filt)

# --- Meat processing ---

def kill_the_enemy(cli, ev, tfilter):
    # Freenode stuff, get the actual ip, removing the gateway stuff
    if "gateway/web/cgi-irc" in ev.source2 or "gateway/web/freenode" in ev.source2:
        ban = "*!*@*" + ev.source2.split("/")[-1]
    elif "gateway/tor-sasl/" in ev.source2.host:
        ban = "*!*@*" + ev.source2.host[17:]
    elif "gateway/" in ev.source2:
        ban = "*!*{0}@*".format(ev.source2.user)
    elif "/" in ev.source2.host:
        if cli.channels[ev.target].users[ev.source2.nick].account:
            ban = "$a:{0}".format(cli.channels[ev.target].users[ev.source2.nick].account)
        else:
            ban = "*!*@{0}".format(ev.source2.host)
    else:
        ip = str(socket.gethostbyname(ev.source2.host))
        ban = "*!*@*{0}".format(ip)
        
    
    if tfilter.Type == "channel":
        codename = "c" + str(tfilter.id)
    elif tfilter.Type == "message":
        codename = "m" + str(tfilter.id)
    elif tfilter.Type == "hostmask":
        codename = "h" + str(tfilter.id)
    
    cli.notice(CONTROLCHAN, "Filter [\002{0}\002 {3}] triggered: \037{1}\037 ||| BAN: {2}".format(codename, ev.source2, ban, tfilter.label))

# --- parrot ---
def parrot(cli, ev, k=False):
    if cli.nickname in " ".join(ev.arguments) and not k and ev.target != CONTROLCHAN:
        cli.privmsg(CONTROLCHAN, "Highlighted on \002{0}\002. Activating parrot mode for 5 minutes.".format(ev.target))
        parrot(cli, ev, True)
        _PARROT[ev.target] = True
        time.sleep(300)
        cli.privmsg(CONTROLCHAN, "Parrot mode deactivated on \002{0}\002".format(ev.target))
        _PARROT[ev.target] = False
        return
    try:
        if _PARROT[ev.target] is not True:
            return
    except:
        return
    if ev.type == "mode":
        cli.privmsg(CONTROLCHAN, "[\002{0}\002] Mode change by \037{1}\037: {2}".format(ev.target, ev.source, " ".join(ev.arguments)))
    elif ev.type == "kick":
        cli.privmsg(CONTROLCHAN, "[\002{0}\002] \037{1}\037 kicked by {2} (Reason: {3})".format(ev.target, ev.arguments[0], ev.source, ev.arguments[1]))
    elif ev.type == "notice":
        cli.privmsg(CONTROLCHAN, "[\002{0}\002] -{1}- {2}".format(ev.target, ev.source, ev.arguments[0]))
    elif ev.type == "part":
        cli.privmsg(CONTROLCHAN, "[\002{0}\002] \037{1}\037 left the channel \002{2}\002".format(ev.target, ev.source, " ".join(ev.arguments)))
    elif ev.type == "join":
        cli.privmsg(CONTROLCHAN, "[\002{0}\002] \037{1}\037 joined the channel".format(ev.target, ev.source))
    elif ev.type == "cquit":
        cli.privmsg(CONTROLCHAN, "[\002{0}\002] \037{1}\037 has quit".format(ev.target, ev.source, " ".join(ev.arguments)))

# --- handler registration ---
connection.addhandler("welcome", welcome)
connection.addhandler("connect", oconnect)
connection.addhandler("authenticate", saslauth)
connection.addhandler("privmsg", gotmsg)
connection.addhandler("privnotice", gotmsg)
connection.addhandler("ctcp", gotmsg)
connection.addhandler("invite", gotmsg)
connection.addhandler("ctcp", ctcp)
connection.addhandler("pubmsg", publmsg)

connection.addhandler("join", joinfilter)
connection.addhandler("pubmsg", privmsgfilter)

connection.addhandler("mode", parrot)
connection.addhandler("kick", parrot)
connection.addhandler("pubnotice", parrot)
connection.addhandler("join", parrot)
connection.addhandler("part", parrot)
connection.addhandler("cquit", parrot)



# Now we connect to the irc and loop forever
connection.connect()

while connection.connected:
    time.sleep(1)
