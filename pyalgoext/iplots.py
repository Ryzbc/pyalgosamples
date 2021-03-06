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


from pyalgotrade import plotter
from plotly.offline import plot as do_plot
import plotly.tools as tls
import os
import re
import webbrowser

def series_plot(self, mplSubplot, dateTimes, color):
   values = []
   for dateTime in dateTimes:
       values.append(self.getValue(dateTime))
   mplSubplot.plot(dateTimes, values, color=color, marker=self.getMarker(), label=self.name)

plotter.Series.plot = series_plot

def subplot_plot(self, mplSubplot, dateTimes):
    for series in self._Subplot__series.values():
        color = None
        if series.needColor():
            color = self._Subplot__getColor(series)
        series.plot(mplSubplot, dateTimes, color)

    # Legend
    # mplSubplot.legend(self._Subplot__series.keys(), shadow=True, loc="best")
    self.customizeSubplot(mplSubplot)

def subplot_getSeries(self, name, defaultClass=plotter.LineMarker):
    try:
        ret = self._Subplot__series[name]
    except KeyError:
        ret = defaultClass()
        ret.name = name
        self._Subplot__series[name] = ret
    return ret

plotter.Subplot.plot = subplot_plot
plotter.Subplot.getSeries = subplot_getSeries

def plot(fig, resize=True, strip_style=False, strip_notes=False, filename='temp-plot.html', auto_open=True):
    plotly_fig = tls.mpl_to_plotly(fig, resize=resize, strip_style=strip_style)

    fl = plotly_fig['layout']
    fl['showlegend'] = True
    fl['legend'] = {}
    fl['legend'].update({'x': 1.01, 'y': 1, 'borderwidth': 1, 'bgcolor': 'rgb(217,217,217)'})
    if strip_notes:
        fl['annotations'] = []
    for key, value in fl.items():
        if key.startswith("xaxis"):
            value['hoverformat'] = '%Y-%m-%d'

    do_plot(plotly_fig, filename=filename, auto_open=auto_open)

def augment(filename):
    dir = os.path.dirname(__file__)
    with open(dir + "/iplots_1.js", "r") as f:
        script_1 = f.read()
    with open(dir + "/iplots_2.js", "r") as f:
        script_2 = f.read()
    with open(filename, 'r') as f:
        text = f.read()
    m = re.findall("Plotly.newPlot\(\"([0-9a-zA-Z\-]*)\",", text)
    if len(m) == 0:
        return
    text = text.replace('{"linkText": "Export to plot.ly", "showLink": true}', script_1)
    script_2 = script_2.replace("[PLOTID]", m[0])
    text = text.replace("</body>", "<script type=\"text/javascript\">%s</script></body>" % script_2)
    with open(filename, 'w') as f:
        f.write(text)
    url = 'file://' + os.path.abspath(filename)
    webbrowser.open(url)