#!/usr/bin/env python3

import os, sys

import PyQt5.QtCore
from PyQt5.QtCore import (
        pyqtSignal,
        )
from PyQt5.QtWidgets import (
        QApplication, QWidget, QTabWidget,
        QVBoxLayout, QHBoxLayout,
        QLabel, QMessageBox, QGroupBox,
        QLineEdit, QPushButton, QFileDialog, QComboBox, QCheckBox,
    )
from datasource import Journal

import matplotlib
matplotlib.use("Qt5Agg")

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

def debug():
    from PyQt5.QtCore import pyqtRemoveInputHook; pyqtRemoveInputHook()
    import ipdb; ipdb.set_trace()

class Options(QWidget):
    reset = pyqtSignal()

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

        self.effective_date = QCheckBox("Use Effective Dates")
        self.effective_date.stateChanged.connect(self.reset)

        viewLayout.addLayout(currencyLayout)
        viewLayout.addWidget(self.effective_date)

        filterLayout = QHBoxLayout()

        label = QLabel("Filter:")
        self.filter = QLineEdit()

        filterLayout.addWidget(label)
        filterLayout.addWidget(self.filter)

        layout.addLayout(viewLayout)
        layout.addLayout(filterLayout)

    def select_file(self):
        selected_file, ignored = QFileDialog(self, "Ledger file to open").getOpenFileName()
        if selected_file:
            try:
                journal = Journal(selected_file, effective_date=self.effective_date)
                self.journal = journal
                self.effective_date.stateChanged.connect(journal.set_effective_date)

                self.button.setText(selected_file)
                self.filename = selected_file
                self.window.setWindowTitle("Ledger visualizer - " + selected_file)

                self.filter.editingFinished.connect(self.reset.emit)

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

        self.commodities = CommodityBox(options)
        self.commodities.changed.connect(self.redraw)

        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

        self.mpl_toolbar = NavigationToolbar(self.canvas, self)

        graphLayout = QVBoxLayout()
        graphLayout.addWidget(self.canvas)
        graphLayout.addWidget(self.mpl_toolbar)

        layout = QHBoxLayout(self)
        layout.addWidget(self.commodities)
        layout.addLayout(graphLayout)

    def reset(self):
        options = self.options
        self.show_currency = options.show_currency.currentText()

        filter = options.filter.text()
        self.data = options.journal.time_series(filter, self.show_currency)
        self.redraw()

    def redraw(self):
        self.ax.clear()

        for commodity, series in self.data.items():
            if commodity not in self.commodities:
                continue
            x = sorted(series.keys())
            y = [series[i].number() for i in x]
            self.ax.plot_date(x, y, fmt='o-', label=commodity)

        if self.show_currency:
            self.ax.set_ylabel(self.show_currency)
        self.ax.legend(loc='upper left')
        self.fig.canvas.draw()


class PieTab(QWidget):
    def __init__(self):
        super(PieTab, self).__init__()

        self.fig = Figure()

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)

        self.mpl_toolbar = NavigationToolbar(self.canvas, self)

        graphLayout = QVBoxLayout(self)
        graphLayout.addWidget(self.canvas)
        graphLayout.addWidget(self.mpl_toolbar)

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

        text = PieTab()
        tabs.addTab(text, "Pie charts")

        button = QPushButton("Quit", self)
        layout.addWidget(button)

        button.clicked.connect(app.quit)

if __name__=='__main__':
    app = QApplication(sys.argv)

    window = Window()
    window.show()

    sys.exit(app.exec_())
