import sys
from collections import defaultdict
import ledger

def debug():
    from PyQt5.QtCore import pyqtRemoveInputHook; pyqtRemoveInputHook()
    import ipdb; ipdb.set_trace()

class Journal(object):
    def __init__(self, filename, effective_date=True):
        self.ledger = ledger
        self.journal = ledger.read_journal(filename)
        self.effective_date = effective_date

    @property
    def commodities(self):
        return self.ledger.commodities

    def set_effective_date(self, effective_date):
        self.effective_date = effective_date

    def entries(self, filter):
        options = ["--sort d"]
        if self.effective_date:
            options.append("--effective")
        return self.journal.query(" ".join(options + [filter]))

    def time_series(self, filter, show_currency=None, merge=False):
        if show_currency and isinstance(show_currency, str):
            show_currency = self.ledger.commodities.find(show_currency)
        data = defaultdict(dict)
        last = defaultdict(ledger.Amount)
        for post in self.entries(filter):
            commodity = post.amount.commodity
            if merge:
                commodity = show_currency
            old = last[commodity.symbol]
            old.commodity = show_currency or commodity
            series = data[commodity.symbol]
            # TODO: move the currency valuation to display logic instead
            value = post.amount
            if show_currency:
                value = value.value(show_currency)
            last[commodity.symbol] = series[post.date] = series.get(post.date, old) + value

        return data
