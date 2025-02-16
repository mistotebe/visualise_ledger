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
    return value and value.to_amount() or ledger.Amount(0)

class StatefulAccounts:
    def __init__(self, journal):
        self.journal = journal.journal
        self.commodities = set()

        self.postings = defaultdict(dict)
        self.running_total = defaultdict(dict)
        self.total = defaultdict(ledger.Balance)

        self.aggregated_postings = defaultdict(dict)
        self.aggregated_running = defaultdict(dict)
        self.aggregated_total = defaultdict(ledger.Balance)

    @property
    def accounts(self):
        return {name: self.journal.find_account(name, False) for name in self.running_total.keys()}

    @property
    def aggregated_accounts(self):
        return {name: self.journal.find_account(name, False) for name in self.aggregated_running.keys()}

    def account_hierarchy(self):
        pass

    def _aggregate(self, post, account):
        name = account.fullname()
        total = self.aggregated_total[name]
        series = self.aggregated_running[name]
        postings = self.aggregated_postings[name]

        new_total = total + post.amount
        series[post.date] = self.aggregated_total[name] = new_total
        postings[post.date] = postings.get(post.date, ledger.Balance()) + post.amount

        if account.parent:
            self._aggregate(post, account.parent)

    def post_callback(self, post):
        self.commodities.add(post.amount.commodity.symbol)

        account = post.account

        name = account.fullname()
        total = self.total[name]
        series = self.running_total[name]
        postings = self.postings[name]

        new_total = total + post.amount
        series[post.date] = self.total[name] = new_total
        postings[post.date] = postings.get(post.date, ledger.Balance()) + post.amount
        self._aggregate(post, account)

class Journal:
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
        running_total = defaultdict(dict)
        total = defaultdict(ledger.Amount)
        for post in self.entries(filter):
            commodity = post.amount.commodity
            if merge:
                commodity = show_currency
            old = total[commodity.symbol]
            old.commodity = show_currency or commodity
            series = running_total[commodity.symbol]
            # TODO: move the currency valuation to display logic instead
            value = post.amount
            if show_currency:
                # Exchange does not always seem to pick up the conversion even
                # when available. We can try and hint it
                if value.value(show_currency) is None:
                    self.update_pricedb(value)
                value = value.value(show_currency)
            total[commodity.symbol] = series[post.date] = series.get(post.date, old) + value

        return running_total, total

    def account_series(self, filter):
        account_series = StatefulAccounts(self)
        for post in self.entries(filter):
            account_series.post_callback(post)

        return account_series
