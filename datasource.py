import sys
from collections import defaultdict
import ledger

def debug():
    from PyQt5.QtCore import pyqtRemoveInputHook; pyqtRemoveInputHook()
    import ipdb; ipdb.set_trace()

def get_value(amount, commodity, *maybe_date):
    # there is an optional parameter, date
    value = amount.value(commodity, *maybe_date)
    # for zero balance, to_amount() will throw an ArithmeticError
    return value and value.to_amount().number() or ledger.Amount(0)

class StatefulAccounts(object):
    def __init__(self, journal):
        self.journal = journal.journal
        self.commodities = set()

        self.data = defaultdict(dict)
        self.last = defaultdict(ledger.Balance)

        self.aggregated = defaultdict(dict)
        self.aggregated_last = defaultdict(ledger.Balance)

    @property
    def accounts(self):
        return {name: self.journal.find_account(name, False) for name in self.data.keys()}

    @property
    def aggregated_accounts(self):
        return {name: self.journal.find_account(name, False) for name in self.aggregated.keys()}

    def account_hierarchy(self):
        pass

    def _aggregate(self, post, account):
        name = account.fullname()
        last = self.aggregated_last[name]
        series = self.aggregated[name]

        value = last + post.amount
        series[post.date] = self.aggregated_last[name] = value

        if account.parent:
            self._aggregate(post, account.parent)

    def post_callback(self, post):
        self.commodities.add(post.amount.commodity.symbol)

        account = post.account

        name = account.fullname()
        last = self.last[name]
        series = self.data[name]

        value = last + post.amount
        series[post.date] = self.last[name] = value
        self._aggregate(post, account)

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

    def update_pricedb(self, amount):
        if amount.has_annotation() and amount.annotation.price:
            self.ledger.commodities.exchange(amount.commodity,
                                             amount.annotation.price)

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
                # Exchange does not always seem to pick up the conversion even
                # when available. We can try and hint it
                if value.value(show_currency) is None:
                    self.update_pricedb(value)
                value = value.value(show_currency)
            last[commodity.symbol] = series[post.date] = series.get(post.date, old) + value

        return data

    def account_series(self, filter):
        account_series = StatefulAccounts(self)
        for post in self.entries(filter):
            account_series.post_callback(post)

        return account_series
