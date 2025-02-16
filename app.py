#!/usr/bin/env python3

import os
import sys
from collections import defaultdict
from datetime import timedelta

import PyQt5.QtCore
from PyQt5.QtCore import (
        pyqtSignal,
)
from PyQt5.QtWidgets import (
        QApplication, QWidget, QTabWidget,
        QVBoxLayout, QHBoxLayout,
        QLabel, QMessageBox, QGroupBox,
        QLineEdit, QPushButton, QFileDialog, QComboBox, QCheckBox, QSpinBox,
)
from datasource import Journal, get_value

import matplotlib
matplotlib.use("Qt5Agg")

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.pyplot import subplots
from matplotlib.figure import Figure
from matplotlib import colormaps

def debug():
    from PyQt5.QtCore import pyqtRemoveInputHook; pyqtRemoveInputHook()
    import ipdb; ipdb.set_trace()

class Options(QWidget):
    reset = pyqtSignal()
    redraw = pyqtSignal()

    def __init__(self, window):
        super(Options, self).__init__()
        self.window = window
        layout = QVBoxLayout(self)

        self.button = QPushButton("Click to select a file to open", self)
        self.button.clicked.connect(self.select_file)

        layout.addWidget(self.button)

        currencyLayout = QHBoxLayout()

        label = QLabel("Show in terms of")
        self.show_currency = QComboBox()

        currencyLayout.addWidget(label)
        currencyLayout.addWidget(self.show_currency)

        viewLayout = QHBoxLayout()

        self.merge = QCheckBox("Merge")
        self.merge.stateChanged.connect(self.reset)

        self.effective_date = QCheckBox("Use Effective Dates")
        self.effective_date.stateChanged.connect(self.reset)

        depthLayout = QHBoxLayout()

        label = QLabel("Account depth to show")
        self.depth_limit = QSpinBox()
        self.depth_limit.setSpecialValueText("Unlimited")
        self.depth_limit.setMinimum(0)
        self.depth_limit.setValue(0)
        self.depth_limit.valueChanged.connect(self.redraw)

        depthLayout.addWidget(label)
        depthLayout.addWidget(self.depth_limit)

        viewLayout.addLayout(currencyLayout)
        viewLayout.addWidget(self.merge)
        viewLayout.addWidget(self.effective_date)
        viewLayout.addLayout(depthLayout)

        filterLayout = QHBoxLayout()

        label = QLabel("Filter:")
        self.filter = QLineEdit()

        filterLayout.addWidget(label)
        filterLayout.addWidget(self.filter)

        layout.addLayout(viewLayout)
        layout.addLayout(filterLayout)

        if app.arguments():
            self.select_file(app.arguments()[-1])

    def select_file(self, selected_file=None):
        if not selected_file:
            selected_file, _ = QFileDialog(self, "Ledger file to open").getOpenFileName()
        if selected_file:
            try:
                journal = Journal(selected_file, effective_date=self.effective_date)
                self.journal = journal
                self.effective_date.stateChanged.connect(journal.set_effective_date)

                self.button.setText(selected_file)
                self.filename = selected_file
                self.window.setWindowTitle("Ledger visualizer - " + selected_file)

                self.filter.editingFinished.connect(self.reset)

                self.show_currency.addItems(journal.commodities.keys())
                self.show_currency.currentTextChanged.connect(self.reset)

                self.reset.emit()
            except RuntimeError:
                message = QMessageBox(self)
                message.setText("Ledger could not parse the selected file")
                message.exec()

class CommodityBox(QGroupBox):
    changed = pyqtSignal()

    def __init__(self, options, title="Commodities"):
        super(CommodityBox, self).__init__(title)
        self.options = options
        self.options.reset.connect(self.reset)

        self.setToolTip("Show only selected commodities")

        self.setCheckable(True)
        self.setChecked(False)
        self.toggled.connect(self.changed)

        self.layout = QVBoxLayout(self)
        self.checkboxes = {}

    def __contains__(self, commodity):
        if not self.isChecked():
            return True
        checkbox = self.checkboxes.get(commodity)
        return checkbox and checkbox.isChecked()

    def reset(self):
        for checkbox in self.checkboxes.values():
            self.layout.removeWidget(checkbox)
        self.checkboxes = {}

        commodities = self.options.journal.commodities
        for commodity in commodities.keys():
            checkbox = QCheckBox(commodity, self)
            self.checkboxes[commodity] = checkbox
            self.layout.addWidget(checkbox)
            checkbox.stateChanged.connect(self.changed)

class GraphTab(QWidget):
    def __init__(self, options):
        super(GraphTab, self).__init__()
        self.options = options
        self.options.reset.connect(self.reset)
        self.options.redraw.connect(self.redraw)

        self.commodities = CommodityBox(options)
        self.commodities.changed.connect(self.redraw)

        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

        self.mpl_toolbar = NavigationToolbar(self.canvas, self)
        self.cmap = colormaps['gist_ncar']

        graphLayout = QVBoxLayout()
        graphLayout.addWidget(self.canvas)
        graphLayout.addWidget(self.mpl_toolbar)

        layout = QHBoxLayout(self)
        layout.addWidget(self.commodities)
        layout.addLayout(graphLayout)

        self.running_total = None

    def reset(self):
        options = self.options
        self.commodity = options.show_currency.currentText()
        self.merge = bool(self.commodity and options.merge.isChecked())

        filter = options.filter.text()
        self.running_total, self.total = options.journal.time_series(filter, self.commodity, self.merge)
        self.redraw()

    def redraw(self):
        self.ax.clear()
        self.ax.grid(True)
        if not self.running_total:
            return

        lines = len(self.total)
        colors = map(self.cmap, ((x+0.5)/lines for x in range(lines)))

        for color, (commodity, amount) in zip(colors, sorted(self.total.items(), key=lambda x: x[1].number(), reverse=True)):
            if commodity not in self.commodities:
                continue
            series = self.running_total[commodity]
            x = sorted(series.keys())
            y = [series[i].number() for i in x]
            label = ("%s (%." + str(amount.commodity.precision) + "f %s)") % (commodity, amount.number(), amount.commodity.symbol)
            self.ax.plot_date(x, y, fmt='o-', color=color, label=label)

        if self.commodity:
            self.ax.set_ylabel(self.commodity)
        self.ax.legend(loc='upper left')
        self.fig.canvas.draw()

class AccountTab(QWidget):
    def __init__(self, options):
        super(AccountTab, self).__init__()
        self.options = options
        self.options.reset.connect(self.reset)
        self.options.redraw.connect(self.redraw)

        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

        self.mpl_toolbar = NavigationToolbar(self.canvas, self)
        self.cmap = colormaps['gist_ncar']

        graphLayout = QVBoxLayout()
        graphLayout.addWidget(self.canvas)
        graphLayout.addWidget(self.mpl_toolbar)

        layout = QHBoxLayout(self)
        layout.addLayout(graphLayout)

        self.series = None
        self.commodity = None

    def reset(self):
        options = self.options
        self.commodity = options.show_currency.currentText()
        self.merge = bool(self.commodity and options.merge.isChecked())

        filter = options.filter.text()
        self.series = options.journal.account_series(filter)

        self.redraw()

    def redraw(self):
        self.ax.clear()
        self.ax.grid(True)
        if not self.series or not self.commodity:
            return

        def useable_accounts(limit):
            aggregate = {}

            for name in self.series.running_total:
                account = self.series.accounts[name]

                if limit and account.depth >= limit:
                    while account.depth > limit:
                        account = account.parent
                    name = account.fullname()

                    aggregate[name] = (get_value(self.series.aggregated_total[name], commodity),
                                       self.series.aggregated_running[name])
                elif name not in aggregate:
                    aggregate[name] = (get_value(self.series.total[name], commodity),
                                       self.series.running_total[name])

            accounts = len(aggregate)
            colors = map(self.cmap, ((x+0.5)/accounts for x in range(accounts)))

            return ((name, next(colors), aggregate[name]) for name in
                sorted(aggregate, key=lambda x: aggregate[x][0], reverse=True))

        commodity = self.options.journal.commodities[self.commodity]
        limit = self.options.depth_limit.value()
        for name, color, (total, running_total) in useable_accounts(limit):
            label = ("%s (%s)") % (name, total)
            running_total = {date: get_value(amount, commodity, date) for (date, amount) in running_total.items()}
            x, y = zip(*sorted(running_total.items()))
            self.ax.plot_date(x, y, fmt='o-', label=label, color=color)

        self.ax.set_ylabel(self.commodity)
        self.ax.legend(loc='upper left')
        self.fig.canvas.draw()

class BarTab(QWidget):
    def __init__(self, options):
        super(BarTab, self).__init__()
        self.options = options
        self.options.reset.connect(self.reset)
        self.options.redraw.connect(self.redraw)

        self.classifiers = self.monthly

        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

        self.mpl_toolbar = NavigationToolbar(self.canvas, self)
        self.cmap = colormaps['gist_ncar']

        graphLayout = QVBoxLayout()
        graphLayout.addWidget(self.canvas)
        graphLayout.addWidget(self.mpl_toolbar)

        #optionLayout = QVBoxLayout(self)
        #optionLayout.addWidget(self.classifiers)

        layout = QHBoxLayout(self)
        layout.addLayout(graphLayout)

        self.series = None
        self.commodity = None

    def monthly(self, name, date, amount, to_commodity):
        return (date.replace(day=1), name, get_value(amount, to_commodity, date))

    def reset(self):
        options = self.options
        self.commodity = options.show_currency.currentText()
        self.merge = bool(self.commodity and options.merge.isChecked())

        filter = options.filter.text()
        self.series = options.journal.account_series(filter)

        self.redraw()

    def redraw(self):
        self.ax.clear()
        self.ax.grid(True)
        if not self.series or not self.commodity:
            return

        accounts = {}
        accounts_sorted = []
        data = defaultdict(dict)
        commodity = self.options.journal.commodities[self.commodity]
        classifier = self.classifiers
        limit = self.options.depth_limit.value()
        width = timedelta(10)

        Balance = self.options.journal.ledger.Balance
        Amount = self.options.journal.ledger.Amount

        def useable_accounts(series, commodity, limit):
            aggregate = {}

            for name in series.running_total:
                account = series.accounts[name]

                if limit and account.depth >= limit:
                    while account.depth > limit:
                        account = account.parent
                    name = account.fullname()

                    aggregate[name] = (get_value(series.aggregated_total[name], commodity),
                                       series.aggregated_postings[name])
                elif name not in aggregate:
                    aggregate[name] = (get_value(series.total[name], commodity),
                                       series.postings[name])

            accounts = len(aggregate)

            return ((name, aggregate[name]) for name in
                sorted(aggregate, key=lambda x: aggregate[x][0], reverse=True))

        for name, (total, postings) in useable_accounts(self.series, commodity, limit):
            label = ("%s (%s)") % (name, total)
            accounts_sorted.append(label)
            number = accounts[name] = (len(accounts), label)
            for group, bucket, value in (
                    classifier(accounts[name], date, amount, commodity)
                        for (date, amount) in postings.items()):
                data[group][bucket] = data[group].get(bucket, Balance()) + value
            postings = {date: get_value(amount, commodity, date)
                    for (date, amount) in postings.items()}

        view = defaultdict(dict)
        for group, buckets in data.items():
            offsets = [Balance(), Balance()]
            sum_neg = Balance()
            for account in sorted(accounts.values()):
                if account not in buckets:
                    continue
                value = buckets[account]
                value = value and value.to_amount() or Amount(0)
                negative = int(value < 0)

                offset = offsets[negative]
                view[account][group] = [negative, offset, value]
                offsets[negative] = offset + value
                if negative:
                    sum_neg += value

            for account, l in view.items():
                if group not in l:
                    continue
                value = l[group]
                if value[0]:
                    new = value[1] + value[2] - sum_neg
                    value[2].in_place_negate()
                else:
                    new = value[1]
                value[1] = new and float(new.to_amount().number()) or 0
                value[2] = float(value[2].number())

        horizontal_offsets = [ -width/2, width/2 ]

        for key, data in view.items():
            index, label = key
            label = accounts_sorted[index]
            color = self.cmap((index+0.5)/len(accounts_sorted))
            bars = [defaultdict(list), defaultdict(list)]
            for group in sorted(data.keys()):
                negative, offset, height = data[group]
                bars[negative]['group'].append(group+horizontal_offsets[negative])
                bars[negative]['offset'].append(offset)
                bars[negative]['height'].append(height)
            self.ax.bar(bars[0]['group'], bars[0]['height'], width.days,
                bottom=bars[0]['offset'], color=color, label=label)
            self.ax.bar(bars[1]['group'], bars[1]['height'], width.days,
                bottom=bars[1]['offset'], color=color)

        self.ax.set_ylabel(self.commodity)
        #self.ax.legend(loc='upper left')
        self.fig.canvas.draw()


class PieTab(QWidget):
    def __init__(self, options):
        super(PieTab, self).__init__()
        self.options = options
        self.options.reset.connect(self.reset)
        self.options.redraw.connect(self.redraw)

        self.fig, self.ax = subplots()

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

        self.mpl_toolbar = NavigationToolbar(self.canvas, self)
        self.cmap = colormaps['gist_ncar']

        self.account = QLineEdit(self)
        self.account.editingFinished.connect(self.redraw)

        graphLayout = QVBoxLayout(self)
        graphLayout.addWidget(self.account)
        graphLayout.addWidget(self.canvas)
        graphLayout.addWidget(self.mpl_toolbar)

        self.series = None
        self.commodity = None

    def reset(self):
        options = self.options
        self.commodity = options.show_currency.currentText()
        if not self.commodity:
            return

        filter = options.filter.text()
        self.series = options.journal.account_series(filter)

        self.redraw()

    def wedges(self, values, threshold=0.01):
        """Generates wedges as long as the new one would be
           at least (threshold * current total), then one more
           for the rest of the data"""
        out = []
        total = 0
        while values:
            current = values[0]
            value, name = current
            if total and float(value / total) < threshold and len(values) > 1:
                remainder = sum((x[0] for x in values))
                current = (remainder, 'long tail of {} below {:.2%}'.format(len(values), threshold))
                out.append(current)
                total += remainder
                break
            else:
                out.append(current)
                total += value
                values.pop(0)

        if total:
            out = [(value.abs(), "{} ({:.2%})".format(name, float(value / total))) for (value, name) in out]

        # the graph gets drawn counter-clockwise, reverse to get it clockwise
        return zip(*reversed(out))

    def redraw(self):
        self.ax.clear()
        if not self.series or not self.commodity:
            return

        commodity = self.options.journal.commodities[self.commodity]

        data = []
        processed = set()
        for name, account in self.series.accounts.items():
            limit = self.options.depth_limit.value()
            aggregate = limit and account.depth >= limit

            if aggregate:
                while account.depth > limit:
                    account = account.parent

                name = account.fullname()
                value = self.series.aggregated_total[name]
            else:
                value = self.series.total[name]

            if name in processed:
                continue

            data.append((get_value(value, commodity), name))
            processed.add(name)

        if not data:
            return

        data = sorted(data, reverse=True, key=lambda x: x[0].abs())

        sizes, labels = self.wedges(data)
        colors = map(self.cmap, (1 - float(x)/len(sizes) for x in range(len(sizes))))
        self.ax.pie(sizes, labels=labels, colors=list(colors), startangle=90)
        self.fig.canvas.draw()

class Window(QWidget):
    def __init__(self):
        super(Window, self).__init__()
        self.setWindowTitle("Ledger visualizer")

        # Create a layout Object, attached to the window.
        layout = QVBoxLayout(self)

        self.options = Options(self)
        layout.addWidget(self.options)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        graph = GraphTab(self.options)
        tabs.addTab(graph, "Time series")

        graph = AccountTab(self.options)
        tabs.addTab(graph, "Account breakdown")

        graph = BarTab(self.options)
        tabs.addTab(graph, "Timed breakdown")

        text = PieTab(self.options)
        tabs.addTab(text, "Pie charts")

        button = QPushButton("Quit", self)
        layout.addWidget(button)

        button.clicked.connect(app.quit)

if __name__=='__main__':
    app = QApplication(sys.argv[1:])

    window = Window()
    window.show()

    sys.exit(app.exec_())
