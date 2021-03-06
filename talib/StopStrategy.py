# PyAlgoTrade
#
# Copyright 2011-2015 Gabriel Martin Becedillas Ruiz
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
.. moduleauthor:: Gabriel Martin Becedillas Ruiz <gabriel.becedillas@gmail.com>
"""

SCENARIO = 2
DBFEED = False
TRAILING = False

from pyalgotrade import strategy, plotter, dataseries
from pyalgotrade.technical import ma, macd, cross
from pyalgotrade.stratanalyzer import drawdown, returns, sharpe
from pyalgotrade.utils import stats
import datetime
import pyalgotrade.logger as logger
import math
from pyalgotrade import broker
from pyalgotrade.broker import backtesting
from pyalgoext import dbfeed
from pyalgotrade.barfeed import yahoofeed
from pyalgotrade.talibext import indicator


class SessionOpenStopOrder(backtesting.StopOrder):
    def __init__(self, action, position, pricePer, quantity, instrumentTraits):
        if action == broker.Order.Action.SELL:
            pricePer = 1 - pricePer
        else:
            pricePer = 1 + pricePer
        self._dateTime = position.getStrategy().getCurrentDateTime()
        self._pricePer = pricePer
        self._position = position

        backtesting.StopOrder.__init__(self, action, position.getInstrument(), position.getLastPrice() * pricePer, quantity, instrumentTraits)
        position.getStrategy().getBarsProcessedEvent().subscribe(self.__onBars)

    def __onBars(self, strategy, bars):
        instrument = self._position.getInstrument()
        if self._dateTime.date != bars.getDateTime().date:
            if instrument in bars:
                self._StopOrder__stopPrice = bars[instrument].getPrice() * self._pricePer
                self._dateTime = bars.getDateTime()


class TrailingStopOrder(backtesting.StopOrder):
    def __init__(self, action, position, pricePer, quantity, instrumentTraits):
        backtesting.StopOrder.__init__(self, action, position.getInstrument(), 0, quantity, instrumentTraits)
        if action == broker.Order.Action.SELL:
            pricePer = 1 - pricePer
        else:
            pricePer = 1 + pricePer
        self._pricePer = pricePer
        self._position = position
        self._refPrice = 0

    def getStopPrice(self):
        lastPrice = self._position.getLastPrice()
        if self.getAction() == broker.Order.Action.SELL:
            if self._refPrice < lastPrice:
                self._refPrice = lastPrice
        else:
            if self._refPrice > lastPrice:
                self._refPrice = lastPrice
        return self._refPrice * self._pricePer


class MyBenchmark(strategy.BacktestingStrategy):
    def __init__(self, feed, stopPer, stopTrailing, delay):
        myBroker = backtesting.Broker(1000000, feed, backtesting.TradePercentage(0.002))
        myBroker.setAllowNegativeCash(True)
        myBroker.getFillStrategy().setVolumeLimit(None)

        super(MyBenchmark, self).__init__(feed, myBroker)

        self._delay = delay
        self._feed = feed
        self._session = 0
        self._liquidity = 0.05
        self._posMax = len(feed.getRegisteredInstruments())
        self._posLong = {}
        self._posShort = {}
        self.startDateTime = None
        self.endDateTime = None

        self._stopPer = stopPer
        self._stopTrailing = stopTrailing

        self.setUseAdjustedValues(True)

    def onEnterOk(self, position):
        order = position.getEntryOrder()
        if order.getAction() == broker.Order.Action.BUY:
            self.logOp("COMPRA", order)
            if self._stopTrailing:
                stopOrder = TrailingStopOrder(broker.Order.Action.SELL, position, self._stopPer, position.getShares(), order.getInstrumentTraits())
                stopOrder.setGoodTillCanceled(True)
                position._Position__submitAndRegisterOrder(stopOrder)
                position._Position__exitOrder = stopOrder
            else:
                position.exitStop(order.getExecutionInfo().getPrice() * (1 - self._stopPer), True)
        else:
            self.logOp("VENTA CORTA", order)
            if self._stopTrailing:
                stopOrder = TrailingStopOrder(broker.Order.Action.BUY_TO_COVER, position, self._stopPer, math.fabs(position.getShares()), order.getInstrumentTraits())
                stopOrder.setGoodTillCanceled(True)
                position._Position__submitAndRegisterOrder(stopOrder)
                position._Position__exitOrder = stopOrder
            else:
                position.exitStop(order.getExecutionInfo().getPrice() * (1 + self._stopPer), True)

    def onEnterCanceled(self, position):
        order = position.getEntryOrder()
        if order.getAction() == broker.Order.Action.BUY:
            del self._posLong[position.getInstrument()]
            self.logOp("COMPRA CANCELADA", order)
        else:
            del self._posShort[position.getInstrument()]
            self.logOp("VENTA CORTA CANCELADA", order)

    def onExitOk(self, position):
        order = position.getExitOrder()
        if order.getAction() == broker.Order.Action.SELL:
            del self._posLong[position.getInstrument()]
            self.logOp("VENTA", order)
        else:
            del self._posShort[position.getInstrument()]
            self.logOp("COMPRA PARA CUBRIR", order)

    def onExitCanceled(self, position):
        # If the exit was canceled, re-submit it.
        position.exitMarket()
        order = position.getExitOrder()
        if order.getAction() == broker.Order.Action.SELL:
            self.logOp("VENTA CANCELADA en %s" % (self.getCurrentDateTime().date()), order)
        else:
            self.logOp("COMPRA PARA CUBRIR CANCELADA en %s" % (self.getCurrentDateTime().date()), order)

    def onBars(self, bars):
        # Wait for the same bar than the strategy
        if self._delay > 0:
            self._delay -= 1
            return

        for instrument, bar in bars.items():
            if instrument not in self._posLong:
                self.prepareEnter(instrument, bars)

    def prepareEnter(self, instrument, bars, action=broker.Order.Action.BUY):
        if (len(self._posLong) + len(self._posShort)) < self._posMax:
            bar = bars[instrument]
            perInstrument = self.getBroker().getEquity() / self._posMax
            cash = self.getBroker().getCash()
            if perInstrument > cash:
                perInstrument = cash
            perInstrument *= (1 - self._liquidity)
            amount = int(perInstrument / bar.getPrice())
            if amount > 0:
                if (action == broker.Order.Action.BUY):
                    self._posLong[instrument] = self.enterLong(instrument, amount, True)
                else:
                    self._posShort[instrument] = self.enterShort(instrument, amount, True)

    def prepareExit(self, position):
        order = position.getExitOrder()
        if not order:
            position.exitMarket()
        elif isinstance(order, broker.StopOrder):
            # order._Order__state = broker.Order.State.CANCELED
            # position.exitMarket()
            position.cancelExit()

    def onStart(self):
        startDateTime =  self.getCurrentDateTime()
        # Problem at Yahoo Feeds start with None
        if not startDateTime:
            startDateTime = self.getFeed().peekDateTime()
        self.startDateTime = startDateTime

    def onFinish(self, bars):
        self.endDateTime = bars.getDateTime()

    def logOp(self, type, order):
        self.info("%s %s %s" % (type, order.getInstrument(), order.getExecutionInfo()))


class MyBasicStrategy(MyBenchmark):
    def __init__(self, feed, stopPer, stopTrailing, smaShort, smaLong):
        MyBenchmark.__init__(self, feed, stopPer, stopTrailing, smaLong)

        self._smaShort = {}
        self._smaLong = {}
        self._macdPrice = {}
        self._macdVol = {}
        for instrument in feed.getRegisteredInstruments():
            self._smaShort[instrument] = ma.SMA(self._feed[instrument].getPriceDataSeries(), smaShort)
            self._smaLong[instrument] = ma.SMA(self._feed[instrument].getPriceDataSeries(), smaLong)
            self._macdPrice[instrument] = macd.MACD(self._feed[instrument].getPriceDataSeries(), 12, 26, 9)
            self._macdVol[instrument] = macd.MACD(self._feed[instrument].getVolumeDataSeries(), 12, 26, 9)

    def getSMAShorts(self):
        return self._smaShort

    def getSMALongs(self):
        return self._smaLong

    def onBars(self, bars):
        for instrument, bar in bars.items():
            # Wait for enough bars to be available to calculate a SMA.
            if not self._smaLong[instrument] or self._smaLong[instrument][-1] is None:
                return

            pri = self._macdPrice[instrument]
            vol = self._macdVol[instrument]
            if instrument in self._posLong:
                if cross.cross_below(self._smaShort[instrument], self._smaLong[instrument]):
                    position = self._posLong[instrument]
                    self.prepareExit(position)

            elif instrument in self._posShort:
                if cross.cross_above(pri.getSignal(), pri):
                    position = self._posShort[instrument]
                    self.prepareExit(position)

            if cross.cross_above(self._smaShort[instrument], self._smaLong[instrument]):
                self.prepareEnter(instrument, bars)
            elif cross.cross_below(pri.getSignal(), pri) and cross.cross_above(vol.getSignal(), vol):
                self.prepareEnter(instrument, bars, broker.Order.Action.SELL_SHORT)


class MyTaLibStrategy(MyBasicStrategy):
    def __init__(self, feed, stopPer, stopTrailing, smaShort, smaLong, aroonPeriod):
        MyBasicStrategy.__init__(self, feed, stopPer, stopTrailing, smaShort, smaLong)

        self._aroon = {}
        self._aroonPeriod = aroonPeriod
        for instrument in feed.getRegisteredInstruments():
            self._aroon[instrument] = dataseries.SequenceDataSeries()

    def onBars(self, bars):
        for instrument, bar in bars.items():
            # Wait for enough bars to be available to calculate a SMA.
            if not self._smaLong[instrument] or self._smaLong[instrument][-1] is None:
                return

            barDs = self.getFeed().getDataSeries(instrument)
            #closeDs = barDs.getCloseDataSeries()
            aroon = indicator.AROONOSC(barDs, self._aroonPeriod + 1, self._aroonPeriod)
            self._aroon[instrument].appendWithDateTime(self.getCurrentDateTime(), aroon[-1])

            pri = self._macdPrice[instrument]
            vol = self._macdVol[instrument]
            if instrument in self._posLong:
                if cross.cross_below(self._smaShort[instrument], self._smaLong[instrument]) and aroon[-1] < -25:
                    position = self._posLong[instrument]
                    self.prepareExit(position)
            elif instrument in self._posShort:
                if cross.cross_above(pri.getSignal(), pri) and aroon[-1] > 25:
                    position = self._posShort[instrument]
                    self.prepareExit(position)

            if cross.cross_above(self._smaShort[instrument], self._smaLong[instrument]) and aroon[-1] > 25:
                self.prepareEnter(instrument, bars)
            elif cross.cross_below(pri.getSignal(), pri) and cross.cross_above(vol.getSignal(), vol) and aroon[-1] < -25:
                    self.prepareEnter(instrument, bars, broker.Order.Action.SELL_SHORT)


if __name__ == "__main__":


    config = {
      'user': 'root',
      'password': '',
      'host': '127.0.0.1',
      'database': 'ibex35',
      'raise_on_warnings': True,
    }

    logger.log_format = "[%(levelname)s] %(message)s"

    stopPer = 0.15

    smaShort = 50
    smaLong = 200
    aroonPeriod = 25

    startDate = datetime.date(2001, 05, 24)
    endDate = datetime.date(2015, 12, 21)

    instrument = 'GAS.MC'

    feed = None

    if DBFEED:
        feed = dbfeed.DbFeed(config, [], 100, startDate, endDate)
        feed.registerInstrument(instrument)
    else:
        feed = yahoofeed.Feed()
        feed.sanitizeBars(True)
        feed.addBarsFromCSV(instrument, instrument + ".csv")

    myStrategy = None
    if SCENARIO == 2:
        myStrategy = MyBasicStrategy(feed, stopPer, TRAILING, smaShort, smaLong)
    elif SCENARIO == 3:
        myStrategy = MyTaLibStrategy(feed, stopPer, TRAILING, smaShort, smaLong, aroonPeriod)
    else:
        myStrategy = MyBenchmark(feed, stopPer, TRAILING, smaLong)

    # Strategy
    returnsAnalyzer = returns.Returns()
    myStrategy.attachAnalyzer(returnsAnalyzer)
    returnsAnalyzer.getReturns().setMaxLen(1000000)

    sharpeAnalyzer = sharpe.SharpeRatio()
    myStrategy.attachAnalyzer(sharpeAnalyzer)

    drawDownAnalyzer = drawdown.DrawDown()
    myStrategy.attachAnalyzer(drawDownAnalyzer)

    # Attach a plotter to the strategy
    plt = plotter.StrategyPlotter(myStrategy, True)

    if hasattr(myStrategy, '_aroon'):
        subPlot = plt.getOrCreateSubplot("Aroon")
        subPlot.addDataSeries("Aroon", myStrategy._aroon[instrument])

    if hasattr(myStrategy, '_smaShort'):
        subPlot = plt.getOrCreateSubplot("SMA")
        subPlot.addDataSeries("SMALong", myStrategy._smaLong[instrument])
        subPlot.addDataSeries("SMAShort", myStrategy._smaShort[instrument])
        subPlot = plt.getOrCreateSubplot("MACD")
        subPlot.addDataSeries("MACDPrice", myStrategy._macdPrice[instrument])
        subPlot.addDataSeries("MACDVolume", myStrategy._macdVol[instrument])

    capStart = myStrategy.getBroker().getEquity()
    myStrategy.info("CAPITAL INICIAL: $%.4f" % capStart)

    # Run the strategy
    myStrategy.run()

    # Show basic information
    allRet = returnsAnalyzer.getReturns()
    capEnd = myStrategy.getBroker().getEquity()

    myStrategy.info("CAPITAL FINAL: $%.4f" % capEnd)
    myStrategy.info(" ")
    myStrategy.info("Rentabilidad: %.4f%%" % (100 * (capEnd - capStart) / capStart))
    myStrategy.info("Rentabilidad Anualizada: %.4f%%" % (100 * (math.pow((capEnd / capStart), (365.0 / ((myStrategy.endDateTime - myStrategy.startDateTime).days))) - 1)))
    myStrategy.info("Volatilidad Anualizada: %.4f%%" % (100 * stats.stddev(allRet, 1) * math.sqrt(252)))
    myStrategy.info("Ratio de Sharpe Anualizado: %.4f" % (100 * sharpeAnalyzer.getSharpeRatio(0.0036, True)))

    myStrategy.info("DrawDown Maximo: %.4f%%" % (100 * drawDownAnalyzer.getMaxDrawDown()))
    myStrategy.info("DrawDown Mas Largo: %s dias" % (drawDownAnalyzer.getLongestDrawDownDuration().days))

    # Plot the strategy.
    plt.plot()
