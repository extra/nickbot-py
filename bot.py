import sys
import threading
import Queue

import irc.client
import irc.logging

# local imports
import exch

## irc config ##
q = Queue.Queue(maxsize=0)

class Nickbot(object):

    def __init__(self, nick, server, port=6667):
        self.client = irc.client.IRC()
        self.nick = nick
        self.server = server
        self.port = port
        self.channels = ["#testmybot"]

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

    def parse_msg(self, e, cmd):
        #print "parsing {}".format(cmd)
        nick = e.source.nick
        cmd = cmd.split(" ", 1)
        if cmd[0] == "!help":
            # TODO : msg reply (not all)
            self.msg_all("nickbotv2| new and improved, more features coming soon")

nick = Nickbot("nickbotv2", "chat.freenode.net", 6667)

## btc config ##

# TODO fix this don't use threads
#stamp = exch.Bitstamp(nick.msg_all) 
stamp = threading.Thread(target=exch.Bitstamp, args=(True,q))
stamp.daemon = True
stamp.start()

finex = threading.Thread(target=exch.Bitfinex, args=(True,q,))
finex.daemon = True
finex.start()

nick.start()

while True:
    try:
        msg = q.get(False)
        nick.msg_all( msg )
    except Queue.Empty:
        #do nothing
        None
    nick.client.process_once(0.2)
