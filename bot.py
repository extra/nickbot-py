import sys
import threading
import Queue

import irc.client
import irc.logging

from twisted.internet import task
from twisted.internet import reactor

# local imports
import exch

## irc config ##
q = Queue.Queue(maxsize=0)

class Nickbot(object):

    def __init__(self, nick, server, exchDict, port=6667):
        self.client = irc.client.IRC()
        self.nick = nick
        self.server = server
        self.port = port
        self.channels = ["#bitcointraders","#testmybot"]
        self.exch = exchDict
        self.c = None

    def start(self):
        try:
            self.c = self.client.server();
            self.c.buffer_class = irc.buffer.LenientDecodingLineBuffer
            print "connecting"
            self.c.connect(self.server, self.port, self.nick)
        except irc.client.ServerConnectionError:
            print "failed connecting"
            raise SysemExit(1)

        self.c.add_global_handler("welcome", self.on_connect)
        self.c.add_global_handler("join", self.on_join)
        self.c.add_global_handler("disconnect", self.on_disconnect)
        self.c.add_global_handler("privmsg", self.on_privmsg)
        self.c.add_global_handler("pubmsg", self.on_pubmsg)

    def msg_all(self, msg):
        if self.c != None:
            for channel in self.channels:
                self.c.privmsg(channel, msg)  # TODO use privmsg many

    def on_connect(self, c, e):
        print "connected"
        for channel in self.channels:
            c.join(channel)

    def on_join(self, c, e):
        pass
        #self.msg_all("hello")

    def on_disconnect(self, c, e):
        print "DISCONNECTED {}".format(e.arguments[0])
        raise SystemExit()

    def on_privmsg(self, c, e):
        self.parse_msg(e, e.arguments[0])

    # TODO : reply to chan vs nick
    def on_pubmsg(self, c, e):
        self.parse_msg(e, e.arguments[0])

    def parse_msg(self, e, data):
        #print "parsing {}".format(cmd)
        nick = e.source.nick
        cmd = data.split(" ", 3)
        if cmd[0] == "!help":
            # TODO : msg reply (not all)
            self.msg_all("nickbotv2| new and improved, more features coming soon; PM extra with suggestions")
        elif cmd[0] == "!wall":
            if len(cmd) > 2:
                amount = int(cmd[2])
                if amount >= 250 and amount <= 5000:
                    if cmd[1] in self.exch:
                        self.exch[cmd[1]].setWall(cmd[2])
        elif cmd[0] == "!price":
            if len(cmd) > 1 and cmd[1] in self.exch:
                self.exch[cmd[1]].priceQuery()
            else:
                for exch in self.exch:
                    self.exch[exch].priceQuery()
        elif cmd[0] == "!volume":
            if len(cmd) > 1 and cmd[1] in self.exch:
                if len(cmd) > 2:
                    volume = int(cmd[2])
                else:
                    volume = 1
                if volume < 1 or volume > 1440:
                    return
                self.exch[cmd[1]].volumeQuery(volume)
            else:
                if len(cmd) > 1:
                    volume = int(cmd[1])
                else:
                    volume = 1
                if volume < 1 or volume > 1440:
                    return
                for exch in self.exch:
                    self.exch[exch].volumeQuery(volume)

## btc config ##

stamp = exch.Bitstamp(q)
finex = exch.Bitfinex(q)

exchDict = { "bitstamp" : stamp, "bitfinex" : finex }

nick = Nickbot("nickbotv2", "chat.freenode.net", exchDict)

reactor.callLater(5, nick.start)

def pollQ():
    try:
        msg = q.get(False)
        nick.msg_all( msg )
    except Queue.Empty:
        pass

def pollIRC():
    nick.client.process_once(0.2)

queueTask = task.LoopingCall(pollQ)
ircTask = task.LoopingCall(pollIRC)

queueTask.start(0.5) # TODO better implementation
ircTask.start(0.5)

reactor.run()
