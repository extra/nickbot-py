import sys
import threading
import Queue

import irc.client
import irc.buffer

import random

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
        self.channels = ["#bitcointraders","#bitcointraders-bots","#nickbot"]
        #self.channels = ["#nickbot"]
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
	# self.c.add_global_handler("part", self.on_part)
	# self.c.add_global_handler("quit", self.on_quit)

    def msg_all(self, msg):
        if self.c != None:
            for channel in self.channels:
                self.c.privmsg(channel, msg)  # TODO use privmsg many

    def msg_one(self, channel, msg):
        self.c.privmsg(channel, msg)

    def on_connect(self, c, e):
        print "connected"
        for channel in self.channels:
            c.join(channel)

    def on_join(self, c, e):
	pass
        #self.msg_one(e.target, "hello")

    def on_disconnect(self, c, e):
        print "DISCONNECTED {}".format(e.arguments[0])
        raise SystemExit()

    def on_privmsg(self, c, e):
        self.parse_msg(e, e.arguments[0])

    def on_pubmsg(self, c, e):
	#self.msg_one(e.target, "HELLO")
	if random.random()*100 < 1:
	    pass
	    # self.msg_one(e.target, 'SNIB SNIB')
        self.parse_msg(e, e.arguments[0])

    def parse_msg(self, e, data):
	if e.source.nick == u"Lycerion":
            pass
        #print "parsing {}".format(cmd)
        nick = e.source.nick
        cmd = data.split(" ", 3)
	if cmd[0] == "!help":
            # TODO : msg reply (not all)
            self.msg_one(e.target, "nickbotv2| new and improved, more features coming soon; PM extra with suggestions")
	elif cmd[0] == "!swap":
	    try:
		if len(cmd) > 1:
		    curr = cmd[1]
		    if len(curr) > 3:
		        return
		    self.exch['bitfinex'].getSwap(currency=cmd[1])
		    self.msg_one(e.target, q.get(False))
		else:
		    self.exch['bitfinex'].getSwap()
		    self.msg_one(e.target, q.get(False))
		    self.msg_one(e.target, q.get(False))
		    self.msg_one(e.target, q.get(False))
	    except ValueError:
		pass
        elif cmd[0] == "!usd":
            try:
		base = float(cmd[1])
		self.msg_one(e.target, str(base)+" CNY is about "+str(base*0.162)+" USD")
	    except ValueError:
		pass
        elif cmd[0] == "!cny":
	    try:
	        base = float(cmd[1])
	        self.msg_one(e.target, "$"+str(base)+" is about "+str(base*6.15)+" CNY")
	    except ValueError:
		pass
        elif cmd[0] == "!wall":
            if len(cmd) > 2:
                try:
                    amount = int(cmd[2])
                except TypeError:
                    return
                if amount >= 250 and amount <= 5000:
                    if cmd[1] in self.exch:
                        self.exch[cmd[1]].setWall(cmd[2])
        elif cmd[0] == "!price":
            if len(cmd) > 1 and cmd[1] in self.exch:
                self.exch[cmd[1]].priceQuery()
            else:
                for exch in self.exch:
                    self.exch[exch].priceQuery()
                # threading/concurrency issues
                toSend = u""
                for x in [1,2,3,4]:
                    try:
                        toSend += q.get(False) + u"; "
                    except Queue.Empty:
                        pass
                self.msg_one( e.target, toSend )
                self.msg_one( e.target, toSend )
        elif cmd[0] == "!volume":
            if len(cmd) > 1 and cmd[1] in self.exch:
                if len(cmd) > 2:
                    try:
                        volume = int(cmd[2])
                    except TypeError:
                        return
                else:
                    volume = 1
                if volume < 1 or volume > 1440:
                    return
                self.exch[cmd[1]].volumeQuery(volume)
            else:
                if len(cmd) > 1:
                    try:
                        volume = int(cmd[1])
                    except TypeError:
                        return
                else:
                    volume = 1
                if volume < 1 or volume > 1440:
                    return
                for exch in self.exch:
                    self.exch[exch].volumeQuery(volume)

## btc config ##

stamp = exch.Bitstamp(q)
finex = exch.Bitfinex(q)
huobi = exch.Huobi(q)
btce = exch.BTCe(q)
huobiltc = exch.HuobiLTC(q)

exchDict = { "bitstamp" : stamp, "bitfinex" : finex, "huobi" : huobi, "btce" : btce, "huobiltc" : huobiltc }

nick = Nickbot("nickbotv2", "weber.freenode.net", exchDict)

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
