# PyAlgoSamples
# Examples using the PyAlgoTrade Library
#
# Copyright 2015-2017 Isaac de la Pena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
.. moduleauthor:: Isaac de la Pena <isaacdlp@agoraeafi.com>
"""

from pyalgotrade import strategy, plotter
from pyalgotrade.barfeed import yahoofeed
from pyalgotrade.technical import ma
import os
import logging

class MyStrategy(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument, smaShort, smaLong):
        strategy.BacktestingStrategy.__init__(self, feed, 10000)
        self.__position = None
        self.__instrument = instrument
        # We'll use adjusted close values instead of regular close values.
        self.setUseAdjustedValues(True)
        self.__smaShort = ma.SMA(feed[instrument].getPriceDataSeries(), smaShort)
        self.__smaLong = ma.SMA(feed[instrument].getPriceDataSeries(), smaLong)
        self.getBroker().getFillStrategy().setVolumeLimit(None)

    def onEnterOk(self, position):
        execInfo = position.getEntryOrder().getExecutionInfo()
        self.info("BUY %i shares at $%.2f Portfolio $%.2f" % (execInfo.getQuantity(), execInfo.getPrice(), self.getBroker().getEquity()))

    def onEnterCanceled(self, position):
        self.__position = None

    def onExitOk(self, position):
        execInfo = position.getExitOrder().getExecutionInfo()
        self.info("SELL %i shares at $%.2f Portfolio $%.2f" % (execInfo.getQuantity(), execInfo.getPrice(), self.getBroker().getEquity()))
        self.__position = None

    def onExitCanceled(self, position):
        # If the exit was canceled, re-submit it.
        self.__position.exitMarket()

    def onBars(self, bars):
        # Wait for enough bars to be available to calculate a SMA.
        if self.__smaLong[-1] is None:
            return

        bar = bars[self.__instrument]
        # If a position was not opened, check if we should enter a long position.
        if self.__position is None:
            if self.__smaShort[-1] > self.__smaLong[-1]:
                # Enter a buy market order for as many shares as we can. The order is good till canceled.
                amount = int(0.95 * self.getBroker().getEquity() / bar.getAdjClose())
                self.__position = self.enterLong(self.__instrument, amount, True)
        # Check if we have to exit the position.
        elif self.__smaShort[-1] < self.__smaLong[-1] and not self.__position.exitActive():
            self.__position.exitMarket()

def run_strategy(index, startYear, endYear, smaShort, smaLong):

    folder = "./SpxResults/"
    if not os.path.isdir(folder):
        os.mkdir(folder)
    resFile = folder + index + "-" + str(startYear) + "-" + str(endYear)

    # Load the yahoo feed from the CSV file
    feed = yahoofeed.Feed()
    feed.sanitizeBars(True)
    for year in range(startYear, endYear):
        feed.addBarsFromCSV(index, "./data/" + index + "-" + str(year) + ".csv")

    # Evaluate the strategy with the feed.
    myStrategy = MyStrategy(feed, index, smaShort, smaLong)

    # Attach a file handler
    fileHandler = logging.FileHandler(resFile + ".txt")
    myStrategy.getLogger().addHandler(fileHandler)

    # Attach a plotter to the strategy
    plt = plotter.StrategyPlotter(myStrategy)

    # Run the strategy
    myStrategy.run()

    myStrategy.info("Final portfolio value: $%.2f" % myStrategy.getBroker().getEquity())

    # Detach the file handler
    myStrategy.getLogger().removeHandler(fileHandler)

    #Plot the strategy
    fig = plt.buildFigure(None, None)
    fig.savefig(resFile + ".png")


index = "^GSPC"
for startYear in range (1950, 2016, 10):
    endYear = startYear + 10
    if endYear > 2016:
        endYear = 2016
    run_strategy(index, startYear, endYear, 50, 200)