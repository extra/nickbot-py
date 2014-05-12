# exchange code
import logging
import json
import Queue
from sys import exit
from time import sleep

from twisted.internet import reactor

# local imports
import twistedpusher
from util import RepeatEvent

#logging.basicConfig(level=logging.DEBUG)

class Exchange(object):
    def __init__(self, name, queue, currency="USD", tradeThreshold=100,
                 volumeThreshold=250, wallThreshold=500):
        self.name = name
        self.currency = currency
        self.q = queue

        self.thresholdTrade = float(tradeThreshold)

        self.thresholdVolume = float(volumeThreshold)
        self.iterVolume = 0
        self.volume = {x: 0 for x in (1440, 720, 360, 180, 120, 60, 30, 15, 10,
                                      5, 1)}
        self.volumeTimer = RepeatEvent(60, self.updateVolume)

        self.lastTrade = 0

        self.thresholdWall = float(wallThreshold)
        self.orderBook = {(0, 0, 0, 0)}  # { (id, type, price, amount) }
        self.oldBook = {(0, 0, 0, 0)}  # for set comparisons
        self.wallTimer = RepeatEvent(15, self.findWalls)
        # orderBook is a set of 3-tuples
        # use set membership tests to parse wall data
        # TODO : if order deleted w/0 volume then probably filled, else pulled

    def getVolume(self, interval):
        return self.volume[interval]

    def updateVolume(self):
        for n in [1440, 720, 360, 180, 120, 60, 30, 15, 10, 5]:
            if self.iterVolume % n == 0:
                self.volume[n] = self.volume[1]
            else:
                self.volume[n] += self.volume[1]
        if self.volume[1] >= self.thresholdVolume:
            self.volumeAlert( self.volume[1] )
        self.volume[1] = 0
        if self.iterVolume == 1441:
            self.iterVolume = 0
        else:
            self.iterVolume += 1

    def gotVolume(self):
        exit("ABORT: define setVolume in subclass")

    def gotTrade(self):
        exit("ABORT: define setTrade in subclass")

    def orderAdd(self):
        exit("ABORT: define orderAdd in subclass")

    def orderDel(self):
        exit("ABORT: define orderDel in subclass")

    def findWalls(self):
        print "Searching!"
        for order in self.orderBook - self.oldBook:
            # in orderBook, but not in oldBook (new wall)
            #print "New Order: %i\n" % order[0]  # TODO : add alert
            self.wallAlert( order[3], order[2], order[1] )
        for order in self.oldBook - self.orderBook:
            # in oldBook, but not in orderBook (wall pulled)
            #print "Old Order: %i\n" % order[0]  # TODO : add alert
            self.wallAlert( -1 *order[3], order[2], order[1] )
        self.oldBook = self.orderBook  # TODO : worry about concurrency?

    def tradeAlert(self, amount, price, direction):
        self.q.put("{} Trade Alert | {} {:.3f} @ {:.3f}".format(self.name, direction, amount, price))

    def wallAlert(self, amount, price):
        direction = "Added"
        if amount < 0:
            direction = "Pulled"
        self.q.put("{} Wall Alert | {} {:.3f} @ {:.3f}".format(self,name,
        direction, amount, price))

    def volumeAlert(self, amount):
        self.q.put("{} Volume Alert | {:.3f}".format(self.name, amount))


class Bitstamp(Exchange):
    def __init__(self, keepAlive, queue, pusherKey='de504dc5763aeef9ff52'):
        Exchange.__init__(self, "Bitstamp", queue, tradeThreshold=5,
                          volumeThreshold=25, wallThreshold=50)

        self.pusherKey = pusherKey
        self.pusher = twistedpusher.Client(key=self.pusherKey)

        self.tradeChannel = self.pusher.subscribe('live_trades')
        self.orderChannel = self.pusher.subscribe('live_orders')

        self.tradeChannel.bind('trade', self.gotTrade)
        self.tradeChannel.bind('trade', self.gotVolume)
        self.orderChannel.bind('order_created', self.orderAdd)
        self.orderChannel.bind('order_deleted', self.orderDel)
        print "Exchange Initiated"
        if keepAlive:
            reactor.run(installSignalHandlers=0)

    def gotVolume(self, event):
        data = json.loads(event['data'].encode('utf-8'))
        id, price, amount = int(data['id']), float(data['price']), float(data['amount'])
        self.volume[1] += amount

    def gotTrade(self, event):
        data = json.loads(event['data'].encode('utf-8'))
        id, price, amount = int(data['id']), float(data['price']), float(data['amount'])
        self.lastTrade = price
        if amount >= self.thresholdTrade:
            # TODO alert here
            self.tradeAlert(amount, price, "BUYSELL")

    def orderAdd(self, event):
        data = json.loads(event['data'].encode('utf-8'))
        tradeId, price, amount, tradeType = int(data['id']), float(data['price']), float(data['amount']), int(data['order_type'])
        # TODO fix above (separate lines)

        # TODO config alert amount
        if amount >= self.thresholdWall and (price < self.lastTrade + 15 and
                                             price > self.lastTrade - 15):
            self.orderBook.add((tradeId, tradeType, price, amount))

    def orderDel(self, event):
        data = json.loads(event['data'].encode('utf-8'))
        tradeId, price, amount, tradeType = int(data['id']), float(data['price']), float(data['amount']), int(data['order_type'])

        #self.orderBook.discard((tradeId, tradeType, price, amount))
