# -*- coding: utf-8 -*-

NICKNAME = "ferdus"
NSPASSWORD = "iamsuperferdus"
IRCSERVER = "chat.freenode.net"
CONTROLCHAN = "##wowsuchban"

TRUST = ["wikimedia/Polsaker"]

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

logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig()

database = peewee.SqliteDatabase('ferdus.db')
database.connect()

connection = client.IRCClient("ferdus")
connection.configure(IRCSERVER, 6667, NICKNAME, NICKNAME, "realname")

# ---- DATABASE STUFF ----

class BaseModel(peewee.Model):
    class Meta:
        database = database

class Channel(BaseModel):
    name = peewee.CharField()
    
class Filter(BaseModel):
    Type = peewee.CharField() # what kind of filter? channels/message
    label = peewee.CharField() # name of the filter
    content = peewee.CharField() # JSON-encoded content of the filter
    hostmask = peewee.CharField() # regex of the hostmask where this filter should apply

Filter.create_table(True)
Channel.create_table(True)

# ---- IRC STUFF ----

def welcome(client, event): # When we're connected to the irc...
    client.join(CONTROLCHAN) # ... we join the control channel
    for channel in Channel.select():
        client.join(channel.name)
    
def oconnect(client, event): # Phew, we're connecting to the server...
    # Let's try to do some SASL
    client.send("CAP REQ :sasl")
    client.send("AUTHENTICATE PLAIN")

def saslauth(client, event): # Finish sasl authentication
    client.send("AUTHENTICATE {0}".format(
        base64.b64encode("{0}\0{0}\0{1}".format(NICKNAME, NSPASSWORD).encode()).decode()))
    client.send("CAP END")
    
def ctcp(cli, event):
    if event.arguments[0] == "VERSION":
        cli.notice(event.source, "\001VERSION HexChat 2.10.1 [x64] / Windows 7 SP1 [1.6GHz]\001")
    elif event.arguments[0] == "PING":
        cli.notice(event.source, "\001PING {0}\001".format(event.arguments[1]))
    elif event.arguments[0] == "AREYOUAWIZARD":
        cli.notice(event.source, "\001AREYOUAWIZARD Yes.\001")
        
def gotmsg(cli, event):
    if event.type == "ctcp" and event.arguments[0] == "ACTION" and client.is_channel(event.target):
        return
    q = "a"
    if event.type[0] in ['a', 'e', 'i', 'o', 'u']:
        q = "an"
    cli.privmsg(CONTROLCHAN, "Got {3} \002{0}\002 from \037{1}\037 : {2}".format(event.type, event.source2, " ".join(event.arguments), q))

def publmsg(cli, ev):
    if ev.target == CONTROLCHAN:
        if ev.splitd[0] == ".join":
            cli.join(ev.splitd[1])
            Channel.create(name=ev.splitd[1])
            cli.privmsg(CONTROLCHAN, "Joined \002{0}\002 and added it to the autojoin list".format(ev.splitd[1]))
        elif ev.splitd[0] == ".part":
            cli.part(ev.splitd[1])
            chan = Channel.get(Channel.name == ev.splitd[1])
            chan.delete_instance()
            cli.privmsg(CONTROLCHAN, "Parted \002{0}\002 and deleted it from the autojoin list".format(ev.splitd[1]))
        elif ev.splitd[0] == ".chanpattern" or ev.splitd[0] == ".cf":
            chanpattern(cli, ev)
            
# --- command stuff ---

def chanpattern(cli, ev):
    try:
        ev.splitd[1]
    except:
        cli.privmsg(CONTROLCHAN, "Adds on-join filters. Usage: .chanpattern <add [hostmask regex] [channels (separated with commas WITHOUT SPACES)] [label]|del [id]|list>")
        return
        
    if ev.splitd[1] == "add":
        channels = json.dumps(ev.splitd[3].lower().split(","))
        Filter.create(hostmask=ev.splitd[2], Type="channel", label=ev.splitd[4], content=channels)
        cli.privmsg(CONTROLCHAN, "Filter created")
    elif ev.splitd[1] == "list":
        for filt in Filter.select().where(Filter.Type == "channel"):
            content = json.loads(filt.content)
            cli.privmsg(CONTROLCHAN, "\002{0}\002: {1} —— {3} (Hostmask: {2})".format(filt.id, " ".join(content), filt.hostmask, filt.label))
    elif ev.splitd[1] == "del":
        filt = Filter.get(Filter.id == ev.splitd[2])
        filt.delete_instance()
        cli.privmsg(CONTROLCHAN, "Filter deleted")

# --- filter processing ---
def privmsgfilter(cli, ev):
    pass
    
def joinfilter(cli, ev):
    try:
        _USERDB[ev.source]
        _USERDB[ev.source]['channels'].append(ev.target.lower())
    except:
        _USERDB[ev.source] = {}
        _USERDB[ev.source]['channels'] = [ev.target.lower()]
    
    for filt in Filter.select().where(Filter.Type == "channel"):
        content = json.loads(filt.content)
        print(_USERDB[ev.source]['channels'])
        print(content)
        if set(_USERDB[ev.source]['channels']) == set(content) and ev.source.nick != cli.nickname:
            regex = re.compile(filt.hostmask)
            if re.search(regex, ev.source):
                # !!!!1 OMFG! ITZ A TROLL
                # EVERYTHING MATCHED
                # RED ALERT, RED ALERT: WE HAVE A TROLL IN THE CHANNEL
                # I REPEAT: WE HAVE A TROLL IN THE CHANNEL
                kill_the_enemy(cli, ev.source, filt)

# --- Meat processing ---

def kill_the_enemy(cli, source, tfilter):
    # Freenode stuff, get the actual ip, removing the gateway stuff
    if "gateway/web/cgi-irc" in source or "gateway/web/freenode" in source:
        ban = "*!*@*" + source.split("/")[-1]
    elif "gateway/tor-sasl/" in source.host:
        ban = "*!*@*" + q[17:]
    elif "gateway/" in source:
        ban = "*!*{0}@*".format(source.user)
    elif "/" in source.host:
        ban = "*!*@{0}".format(source.host)
    else:
        ip = str(socket.gethostbyname(source.host))
        ban = "*!*@*{0}".format(ip)
        
    
    if tfilter.Type == "channel":
        codename = "c" + str(tfilter.id)
    
    cli.notice(CONTROLCHAN, "Filter [\002{0}\002 {3}] triggered: \037{1}\037 ||| BAN: {2}".format(codename, source, ban, tfilter.label))

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


# Now we connect to the irc and loop forever
connection.connect()

while connection.connected:
    time.sleep(1)
