from __future__ import absolute_import

__all__ = ['DatadogMetricsBackend']

from datadog import initialize, ThreadStats
from datadog.util.hostname import get_hostname

from sentry.utils.cache import memoize

from .base import MetricsBackend


# XXX(dcramer): copied from sentry.utils.metrics
def _sampled_value(value, sample_rate):
    if sample_rate < 1:
        value = int(value * (1.0 / sample_rate))
    return value


class DatadogMetricsBackend(MetricsBackend):
    def __init__(self, prefix=None, **kwargs):
        self.tags = kwargs.pop('tags', None)
        if 'host' in kwargs:
            self.host = kwargs.pop('host')
        else:
            self.host = get_hostname()
        initialize(**kwargs)
        super(DatadogMetricsBackend, self).__init__(prefix=prefix)

    def __del__(self):
        self.stats.stop()

    @memoize
    def stats(self):
        instance = ThreadStats()
        instance.start()
        return instance

    def incr(self, key, instance=None, tags=None, amount=1, sample_rate=1):
        if tags is None:
            tags = {}
        if self.tags:
            tags.update(self.tags)
        if instance:
            tags['instance'] = instance
        if tags:
            tags = ['{}:{}'.format(*i) for i in tags.items()]
        # datadog does not implement sampling here
        amount = _sampled_value(amount, sample_rate)
        self.stats.increment(self._get_key(key), amount,
                             tags=tags,
                             host=self.host)

    def timing(self, key, value, instance=None, tags=None, sample_rate=1):
        if tags is None:
            tags = {}
        if self.tags:
            tags.update(self.tags)
        if instance:
            tags['instance'] = instance
        if tags:
            tags = ['{}:{}'.format(*i) for i in tags.items()]
        self.stats.timing(self._get_key(key), value, sample_rate=sample_rate,
                          tags=tags,
                          host=self.host)
