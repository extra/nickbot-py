# exchange code
import sys

class Exchange:
    def __init__(self, name, currency = "USD", volumeThreshold = 250,
    wallThreshold = 500):
        self.name = name
        self.currency = currency

        self.thresholdVolume = volumeThreshold
        self.volume = {x: 0 for x in (1440, 720, 360, 180, 120, 60, 30, 15, 10,
        5)}

        self.lastTrade = 0

        self.thresholdWall = wallThreshold
        self.orderBook = { (0, 0, 0) } # { (price, id, volume) }
        self.oldBook = { (0, 0, 0) } # for set comparisons
        # orderBook is a set of 3-tuples
        # use set membership tests to parse wall data
        # TODO : only add to sets if order fits criteria/threshold

    def getVolume(self, interval):
        return self.volume[interval]

    def updateVolume(self):
# TODO : method for repeating this every 60s
        for n in [1440, 720, 360, 180, 120, 60, 30, 15, 10, 5]:
            if self.iterVolume % n == 0:
                self.volume[n] = self.volume[1]
            else:
                self.volume[n] += self.volume[1]
        if self.volume[1] >= self.thresholdVolume:
# TODO : do something (alert)
            self.volume = self.volume #remove me
        self.volume[1] = 0
        if self.iterVolume == 1441:
            self.iterVolume = 0
        else:
            self.iterVolume += 1

    def setVolume(self):
# TODO : define in subclass
        sys.exit("ABORT: define setVolume in subclass")

    def setTrade(self):
# TODO : call trade alert in subclass as well
        sys.exit("ABORT: define setTrade in subclass")

    def orderAdd(self):
        sys.exit("ABORT: define orderAdd in subclass")

    def orderDel(self):
        sys.exit("ABORT: define orderDel in subclass")

    def findWalls(self):
        for order in self.orderBook - self.oldBook:
            # in orderBook, but not in oldBook (new wall)
            printf("new") # TODO : add alert
        for order in self.oldBook - self.orderBook:
            # in oldBook, but not in orderBook (wall pulled)
            printf("old") # TODO : add alert
        self.oldBook = self.orderBook # TODO : worry about concurrency?
