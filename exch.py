#!/usr/bin/python
# vim: set fileencoding=utf-8 :
# exchange code
import logging
import json
import datetime
import Queue
from sys import exit
import time

import requests

# local imports
import twistedpusher
from util import RepeatEvent

#logging.basicConfig(level=logging.DEBUG)

class Exchange(object):
    def __init__(self, name, queue, currency="$", tradeThreshold=100,
                 volumeThreshold=250, wallThreshold=2500, priceSens=40):
        self.name = name
        self.currency = currency
        self.q = queue
        self.quiet = False
        self.quietQ = self.q

        self.priceSens = priceSens

        self.thresholdTrade = float(tradeThreshold)

        self.thresholdVolume = float(volumeThreshold)
        self.iterVolume = 0
        self.volume = {x: 0 for x in (1440, 720, 360, 180, 120, 60, 30, 15, 10,
                                      5, 1)}
        self.volumeTimer = RepeatEvent(60, self.updateVolume)

        r = requests.get( "https://www.bitstamp.net/api/ticker/" )
        try:
            data = r.json()
            self.lastTrade = float( data['last'] )
        except ValueError:
            self.lastTrade = 0.0

        self.quietWalls = { (0,) }
        self.thresholdWall = float(wallThreshold)
        self.orderPrices = { 0.0: [0.0,0.0] }
        # use hash b/c order amounts aren't constant
        self.orderBook = {(0, 0, 0)}  # { (id, type, price) }
        self.oldBook = {(0, 0, 0)}  # for set comparisons
        self.wallTimer = RepeatEvent(15, self.findWalls)
        # orderBook is a set of 3-tuples
        # use set membership tests to parse wall data
        # TODO : if order deleted w/0 volume then probably filled, else pulled

    def setTrade(self, amount):
        self.thresholdTrade = amount

    def setVolume(self, amount):
        self.thresholdVolume = amount

    def setWall(self, amount):
        self.thresholdWall = float(amount)

    def toggleQuiet(self):
        if not self.quiet:
            self.quiet = True
            self.q = Queue.Queue()
        else:
            self.quiet = False
            self.q = self.quietQ

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

    def gotVolume(self, amount):
        self.volume[1] += amount

    def gotTrade(self, price, amount, tradeType=None):
        # TODO handle None
        tType = ""
        if tradeType == None:
            if price > self.lastTrade:
                tType = "Buy"
            elif price < self.lastTrade:
                tType = "Sell"
        else:
            if tradeType == "1":
                tType = "Buy"
            elif tradeType == "0":
                tType = "Sell"
        if amount >= self.thresholdTrade:
            self.tradeAlert(amount, price, tType)
        self.lastTrade = price

    def orderAdd(self, price, amount, orderType, orderId=None):
        # TODO handle None
        if amount >= self.thresholdWall and (price < self.lastTrade +
            self.priceSens and price > self.lastTrade - self.priceSens):
            self.orderBook.add((orderId, orderType, price))
            self.orderPrices[price] = [amount, amount]

    def orderDel(self, price, amount, orderType, orderId=None):
        # TODO handle None
        self.orderBook.discard( (orderId, orderType, price) )
        if price in self.orderPrices:
            oldAmount = self.orderPrices[price][0]
            self.orderPrices[price] = [oldAmount,amount]
        # TODO : when to prune dict?

    def findWalls(self):
        for order in self.orderBook - self.oldBook:
            # in orderBook, but not in oldBook (new wall)
            amount = self.orderPrices[order[2]]
            if( order[2] < self.lastTrade + (self.priceSens /2) and order[2] > self.lastTrade - (self.priceSens/2)):
            	self.wallAlert( amount[0], amount[1], order[2], order[0] )
        for order in self.oldBook - self.orderBook:
            # in oldBook, but not in orderBook (wall pulled)
            amount = self.orderPrices[order[2]]
            if( order[2] < self.lastTrade + (self.priceSens /2) and order[2] > self.lastTrade - (self.priceSens/2)):
            	self.wallAlert( -1 * amount[0], -1 * amount[1], order[2], order[0] )
        self.oldBook = self.orderBook.copy()  # TODO : worry about concurrency?

    def tradeAlert(self, amount, price, direction):
        self.q.put(u"{} Trade Alert | {} {:.3f} BTC @ {}{:.3f}".format(self.name, direction, amount, self.currency, price))

    def priceQuery(self):
        self.q.put(u"{} Price | {}{:.3f}".format(self.name, self.currency, self.lastTrade))

    def volumeQuery(self, interval):
        if interval in self.volume:
            self.q.put(u"{} {}m Volume | {:.3f} BTC".format(self.name, interval, self.volume[interval]))

    def wallAlert(self, oldAmount, amount, price, wallId):
        if (price,) in self.quietWalls:
            return
        direction = "Added"
        if amount < 0:
            direction = "Pulled"
        elif amount == 0:
            direction = "Eaten"
        self.q.put(u"{} Wall Alert | {} {:.3f} BTC @ {}{:.3f}".format(self.name, direction, oldAmount, self.currency, price))

    def volumeAlert(self, amount):
        # TODO add direction
        self.q.put(u"{} Volume Alert | Last 60s {:.3f} BTC ({}{:.3f})".format(self.name, amount, self.currency, self.lastTrade))  


class Bitstamp(Exchange):
    def __init__(self, queue, pusherKey='de504dc5763aeef9ff52'):
        Exchange.__init__(self, "Bitstamp", queue, tradeThreshold=100,
                          volumeThreshold=250, wallThreshold=2500)

        self.pusherKey = pusherKey
        self.pusher = twistedpusher.Client(key=self.pusherKey)

        self.tradeChannel = self.pusher.subscribe('live_trades')
        self.orderChannel = self.pusher.subscribe('live_orders')

        self.tradeChannel.bind('trade', self.getTrade)
        self.tradeChannel.bind('trade', self.getVolume)
        self.orderChannel.bind('order_created', self.getOrderAdd)
        self.orderChannel.bind('order_deleted', self.getOrderDel)
        print "Bitstamp Initialized"

    def getVolume(self, event):
        data = json.loads(event['data'].encode('utf-8'))
        id, price, amount = int(data['id']), float(data['price']), float(data['amount'])
        self.gotVolume(amount)

    def getTrade(self, event):
        data = json.loads(event['data'].encode('utf-8'))
        id, price, amount = int(data['id']), float(data['price']), float(data['amount'])
        self.gotTrade( price, amount )

    def getOrderAdd(self, event):
        data = json.loads(event['data'].encode('utf-8'))
        tradeId, price, amount, orderType = int(data['id']), float(data['price']), float(data['amount']), int(data['order_type'])

        self.orderAdd( price, amount, orderType, orderId=tradeId )

    def getOrderDel(self, event):
        data = json.loads(event['data'].encode('utf-8'))
        tradeId, price, amount, orderType = int(data['id']), float(data['price']), float(data['amount']), int(data['order_type'])

        self.orderDel( price, amount, orderType, orderId=tradeId )


class Bitfinex(Exchange):
    # TODO  SWAP
    def __init__(self, queue):
        Exchange.__init__(self, "Bitfinex", queue, tradeThreshold=100,
                          volumeThreshold=250, wallThreshold=2500)

        #self.base = apiBase 
        self.base = "https://api.bitfinex.com/v1/"
        self.tradeTime = round(time.time())

        r = requests.get( self.base + 'pubticker/BTCUSD' )
        try:
            data = r.json()
            self.lastTrade = float(data['last_price'])
        except ValueError:
            self.lastTrade = 0.0
            print "Couldn't get finex price"


        self.pollTrade = RepeatEvent(3, self.getTrade)
        self.pollOrders = RepeatEvent(3, self.getOrders)
        print "Bitfinex Initialized"

    def getSwap(self, currency=None):
        if currency is None:
            currency = ['btc', 'usd', 'ltc']
	else:
	    currency = [currency.lower()]

	for curr in currency:
	    r = requests.get( self.base + 'lends/' + curr )
	    try:
		data = r.json()[0]
	    except ValueError:
		return

	    amount = float(data["amount_lent"])

	    swapdate = datetime.datetime.fromtimestamp(data["timestamp"]).strftime('%H:%M:%S')

	    self.q.put("{} Swaps: {:20,.3f} {} as of {} EST".format(curr.upper(), amount, curr.upper(), swapdate))
		

    def getTrade(self):
        payload = {'timestamp': self.tradeTime, 'limit_trades': '250'}
        # TODO how many?
        r = requests.get( self.base + 'trades/btcusd', params=payload )
        try:
            data = r.json()
        except ValueError:
            print "Couldn't decode Bitfinex"
            return

        if len(data) > 0:
            self.tradeTime = int(data[0]["timestamp"]) + 1
            for trade in data:
                price, amount, which = float(trade['price']), float(trade['amount']), trade['type']
                self.gotTrade(price, amount, tradeType=which)
                self.gotVolume(amount)

    def getOrders(self):
        payload = {'limit_bids': '250', 'limit_asks': '250'}
        r = requests.get( self.base + 'book/btcusd', params=payload)
        try:
            data = r.json()
        except ValueError:
            print "Couldn't decode Bitfinex"
            return

        for order in self.oldBook: # stops set change during iteration
            if order[2] == 0:
                oType = "bids"
            else:
                oType = "asks"
            
            found = True
            for elm in data[oType]:
                price = float(elm['price'])
                amount = float(elm['amount'])
                original = self.orderPrices[order[2]][0]
                if price == order[2]:
                    if amount < original:
                        if 100 * amount / original <= 10:
                            self.orderDel( order[2], amount, order[1] )
                else:
                    self.orderDel( order[2], original, order[1] )

        for bid in data['bids']:
            price = float(bid['price'])
            amount = float(bid['amount'])
            self.orderAdd( price, amount, 0 ) 

        for ask in data['asks']:
            price = float(ask['price'])
            amount = float(ask['amount'])
            self.orderAdd( price, amount, 1 )

class Huobi(Exchange):
    def __init__(self, queue):
        Exchange.__init__(self, "Huobi", queue, tradeThreshold=100,
                          volumeThreshold=250, wallThreshold=2500,
                          priceSens=100, currency=u'¥')

        #self.base = apiBase 
        self.base = "http://market.huobi.com/staticmarket/"
        # TODO add http(s) back...timeouts fix?
        self.tradeTime = None

        try:
            r = requests.get( self.base + 'ticker_btc_json.js' )
            data = r.json()
            self.lastTrade = float(data['ticker']['last'])
        except ValueError:
            self.lastTrade = 0.0
            print "Couldn't get huobi price"
        except requests.exceptions.Timeout:
            self.lastTrade = 0.0
            print "Huobi Price Timeout"
        except requests.exceptions.ConnectionError:
            self.lastTrade = 0.0
            print "Huobi Price Error"

        self.pollTrade = RepeatEvent(20, self.getTrade)
        self.pollOrders = RepeatEvent(30, self.getOrders)
        print "Huobi Initialized"

    def getTrade(self):
        try:
            r = requests.get( self.base + 'detail_btc_json.js')
            data = r.json()
        except ValueError:
            print "Couldn't decode Huobi"
            return
        except requests.exceptions.Timeout:
            print "Huobi Trade Timeout"
            return
        except requests.exceptions.ConnectionError:
            print "Huobi Trade Error"
            return

        if len(data) > 0:
            if self.tradeTime == None:
                self.tradeTime = time.strptime(data['trades'][0]['time'], "%H:%M:%S")
                print "Set time: {} {}".format(data['trades'][0]['time'],self.tradeTime)
                return
            for trade in data['trades']:
                tradeTime, price, amount, which = time.strptime(trade['time'], "%H:%M:%S"), float(trade['price']), float(trade['amount']), trade['type']
                if tradeTime > self.tradeTime:
                    if which == u'买入':
                        which = 1
                    else:
                        which = 0 # '卖出'
                    self.gotTrade(price, amount, tradeType=which)
                    self.gotVolume(amount)
            self.tradeTime = time.strptime(data['trades'][0]['time'], "%H:%M:%S")

    def getOrders(self):
        try:
            r = requests.get( self.base + 'depth_btc_json.js' )
            data = r.json()
        except ValueError:
            print "Couldn't decode Huobi"
            return
        except requests.exceptions.Timeout:
            print "Huobi Orders Timeout"
            return
        except requests.exceptions.ConnectionError:
            print "Huobi Orders Error"
            return

        for order in self.oldBook: # stops set change during iteration
            if order[2] == 0:
                oType = "bids"
            else:
                oType = "asks"
            
            found = True
            for elm in data[oType]:
                price = float(elm[0])
                amount = float(elm[1])
                original = self.orderPrices[order[2]][0]
                if price == order[2]:
                    if amount < original:
                        if 100 * amount / original <= 10:
                            self.orderDel( order[2], amount, order[1] )
                else:
                    self.orderDel( order[2], original, order[1] )

        for bid in data['bids']:
            price = float(bid[0])
            amount = float(bid[1])
            self.orderAdd( price, amount, 0 ) 

        for ask in data['asks']:
            price = float(ask[0])
            amount = float(ask[1])
            self.orderAdd( price, amount, 1 )

class BTCe(Exchange):
    def __init__(self, queue):
        Exchange.__init__(self, "BTC-e", queue, tradeThreshold=100,
                          volumeThreshold=250, wallThreshold=1000)

        #self.base = apiBase 
        self.base = "https://btc-e.com/api/3/"
        self.tradeTime = None

        r = requests.get( self.base + 'ticker/btc_usd' )
        try:
# TODO add exception checking everywhere
            data = r.json()
            self.lastTrade = float(data['btc_usd']['last'])
        except ValueError:
            self.lastTrade = 0.0
            print "Couldn't get btc-e price"


        self.pollTrade = RepeatEvent(3, self.getTrade)
        self.pollOrders = RepeatEvent(3, self.getOrders)
        print "BTC-e Initialized"

    def getTrade(self):
        payload = {'limit': '250'}
        # TODO how many?
        r = requests.get( self.base + 'trades/btc_usd', params=payload )
        try:
            data = r.json()
        except ValueError:
            print "Couldn't decode Bitfinex"
            return

        if len(data) > 0:
            if self.tradeTime == None:
                self.tradeTime = int(data['btc_usd'][0]["timestamp"])
            for trade in data['btc_usd']:
                price, amount, which, tradeTime = float(trade['price']), float(trade['amount']), trade['type'], int(trade['timestamp'])
                if tradeTime > self.tradeTime:
                    if which == "ask":
                        which = 0
                    elif which == "bid":
                        which = 1
                    self.gotTrade(price, amount, tradeType=which)
                    self.gotVolume(amount)
            self.tradeTime = int(data['btc_usd'][0]["timestamp"])

    def getOrders(self):
        payload = {'limit': '250'}
        r = requests.get( self.base + 'depth/btc_usd/', params=payload)
        try:
            data = r.json()
        except ValueError:
            print "Couldn't decode Bitfinex"
            return

        for order in self.oldBook: # stops set change during iteration
            if order[2] == 0:
                oType = "bids"
            else:
                oType = "asks"
            
            for elm in data['btc_usd'][oType]:
                price = float(elm[0])
                amount = float(elm[1])
                original = self.orderPrices[order[2]][0]
                if price == order[2]:
                    if amount < original:
                        if 100 * amount / original <= 10:
                            self.orderDel( order[2], amount, order[1] )
                else:
                    self.orderDel( order[2], original, order[1] )

        for bid in data['btc_usd']['bids']:
            price = float(bid[0])
            amount = float(bid[1])
            self.orderAdd( price, amount, 0 ) 

        for ask in data['btc_usd']['asks']:
            price = float(ask[0])
            amount = float(ask[1])
            self.orderAdd( price, amount, 1 )

class HuobiLTC(Exchange):
    def __init__(self, queue):
        Exchange.__init__(self, "Huobi LTC", queue, tradeThreshold=5000,
                          volumeThreshold=99999999, wallThreshold=99999999,
                          priceSens=999999999, currency=u'¥')

        #self.base = apiBase 
        self.base = "http://market.huobi.com/staticmarket/"
        # TODO add http(s) back...timeouts fix?
        self.tradeTime = None

        try:
            r = requests.get( self.base + 'ticker_ltc_json.js' )
            data = r.json()
            self.lastTrade = float(data['ticker']['last'])
        except ValueError:
            self.lastTrade = 0.0
            print "Couldn't get huobi price"
        except requests.exceptions.Timeout:
            self.lastTrade = 0.0
            print "Huobi Price Timeout"
        except requests.exceptions.ConnectionError:
            self.lastTrade = 0.0
            print "Huobi Price Error"

        self.pollTrade = RepeatEvent(20, self.getTrade)
        print "HuobiLTC Initialized"

    def getTrade(self):
        try:
            r = requests.get( self.base + 'detail_ltc_json.js')
            data = r.json()
        except ValueError:
            print "Couldn't decode Huobi"
            return
        except requests.exceptions.Timeout:
            print "Huobi Trade Timeout"
            return
        except requests.exceptions.ConnectionError:
            print "Huobi Trade Error"
            return

        if len(data) > 0:
            if self.tradeTime == None:
                self.tradeTime = time.strptime(data['trades'][0]['time'], "%H:%M:%S")
                print "Set time: {} {}".format(data['trades'][0]['time'],self.tradeTime)
                return
            for trade in data['trades']:
                tradeTime, price, amount, which = time.strptime(trade['time'], "%H:%M:%S"), float(trade['price']), float(trade['amount']), trade['type']
                if tradeTime > self.tradeTime:
                    if which == u'买入':
                        which = 1
                    else:
                        which = 0 # '卖出'
                    self.gotTrade(price, amount, tradeType=which)
                    self.gotVolume(amount)
            self.tradeTime = time.strptime(data['trades'][0]['time'], "%H:%M:%S")

    def getOrders(self):
	pass
