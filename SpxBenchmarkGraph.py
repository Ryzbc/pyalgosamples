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
from pyalgotrade.stratanalyzer import drawdown, returns, sharpe, trades
from pyalgotrade.utils import stats
from pyalgoext import volatility

class MyStrategy(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument):
        strategy.BacktestingStrategy.__init__(self, feed, 10000)
        self.__position = None
        self.__instrument = instrument
        # We'll use adjusted close values instead of regular close values.
        self.setUseAdjustedValues(True)
        self.getBroker().getFillStrategy().setVolumeLimit(None)

    def onEnterOk(self, position):
        execInfo = position.getEntryOrder().getExecutionInfo()
        self.info("BUY %i shares at $%.2f Portfolio $%.2f" % (execInfo.getQuantity(), execInfo.getPrice(), self.getBroker().getEquity()))

    def onEnterCanceled(self, position):
        self.__position = None

    def onBars(self, bars):
        # Wait for enough bars to be available to calculate a SMA.
        bar = bars[self.__instrument]
        # If a position was not opened, check if we should enter a long position.
        if self.__position is None:
            # Enter a buy market order for as many shares as we can. The order is good till canceled.
            amount = int(0.95 * self.getBroker().getEquity() / bar.getAdjClose())
            self.__position = self.enterLong(self.__instrument, amount, True)

def run_strategy(index, startYear, endYear):

    # Load the yahoo feed from the CSV file
    feed = yahoofeed.Feed()
    feed.sanitizeBars(True)
    for year in range(startYear, endYear):
        feed.addBarsFromCSV(index, "./data/" + index + "-" + str(year) + ".csv")

    # Evaluate the strategy with the feed.
    myStrategy = MyStrategy(feed, index)

    # Attach analyzers to the strategy.
    # Returns first in case others use it (DataSeries)
    returnsAnalyzer = returns.Returns()
    myStrategy.attachAnalyzer(returnsAnalyzer)
    returnsAnalyzer.getReturns().setMaxLen(300000)

    sharpeAnalyzer = sharpe.SharpeRatio()
    myStrategy.attachAnalyzer(sharpeAnalyzer)

    drawDownAnalyzer = drawdown.DrawDown()
    myStrategy.attachAnalyzer(drawDownAnalyzer)

    tradesAnalyzer = trades.Trades()
    myStrategy.attachAnalyzer(tradesAnalyzer)

    volaAnalyzer = volatility.VolaAnalyzer(120)
    myStrategy.attachAnalyzer(volaAnalyzer)

    # Attach a plotter to the strategy
    plt = plotter.StrategyPlotter(myStrategy)

    volaSeries = volaAnalyzer.getVolaSeries()
    plt.getOrCreateSubplot("Volatility").addDataSeries("Volatility", volaSeries)

    # Run the strategy
    myStrategy.run()

    # Show basic information
    myStrategy.info("Valor final de la cartera: $%.2f" % myStrategy.getBroker().getEquity())

    myStrategy.info("Ratio de Sharpe Anualizado: " + str(sharpeAnalyzer.getSharpeRatio(0.0036, True)))

    myStrategy.info("DrawDown Maximo: " + str(drawDownAnalyzer.getMaxDrawDown()))
    myStrategy.info("DrawDown Mas Largo: " + str(drawDownAnalyzer.getLongestDrawDownDuration()))

    meanProfit = stats.mean(tradesAnalyzer.getProfits())
    myStrategy.info("Ganancia Media: " + str(meanProfit))
    meanLoss = stats.mean(tradesAnalyzer.getLosses())
    myStrategy.info("Perdida Media: " + str(meanLoss))
    myStrategy.info("Num Ops Igual: " + str(tradesAnalyzer.getEvenCount()))
    myStrategy.info("Num Ops Gano: " + str(tradesAnalyzer.getProfitableCount()))
    myStrategy.info("Num Ops Pierdo: " + str(tradesAnalyzer.getUnprofitableCount()))

    allRet = returnsAnalyzer.getReturns()
    #print len(allRet)
    myStrategy.info("Rent Media: " + str(stats.mean(allRet)))
    posRet = []
    negRet = []
    allRet = returnsAnalyzer.getReturns()
    for ret in allRet:
        if ret > 0:
            posRet.append(ret)
        elif ret < 0:
            negRet.append(ret)
    myStrategy.info("Ganancia Media: " + str(stats.mean(posRet)))
    myStrategy.info("Perdida Media: " + str(stats.mean(negRet)))

    myStrategy.info("Vola Media: " + str(stats.mean(volaSeries[-60:])))

    # Plot the strategy.
    plt.plot()

run_strategy("^GSPC", 1950, 2016)