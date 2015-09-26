"""
sentry.quotas.redis
~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2010-2014 by the Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""
from __future__ import absolute_import

import time

from django.conf import settings
from rb import Cluster

from sentry.exceptions import InvalidConfiguration
from sentry.quotas.base import Quota, RateLimited, NotRateLimited


class RedisQuota(Quota):
    ttl = 60

    def __init__(self, **options):
        if not options:
            # inherit default options from REDIS_OPTIONS
            options = settings.SENTRY_REDIS_OPTIONS
        super(RedisQuota, self).__init__(**options)
        options.setdefault('hosts', {0: {}})
        self.cluster = Cluster(options['hosts'])

    def validate(self):
        try:
            with self.cluster.all() as client:
                client.ping()
        except Exception as e:
            raise InvalidConfiguration(unicode(e))

    def is_rate_limited(self, project):
        proj_quota = self.get_project_quota(project)
        if project.team:
            team_quota = self.get_team_quota(project.team)
        else:
            team_quota = 0
        system_quota = self.get_system_quota()

        if not (proj_quota or system_quota or team_quota):
            return NotRateLimited

        sys_result, team_result, proj_result = self._incr_project(project)

        if proj_quota and proj_result > proj_quota:
            return RateLimited(retry_after=self.get_time_remaining())

        if team_quota and team_result > team_quota:
            return RateLimited(retry_after=self.get_time_remaining())

        if system_quota and sys_result > system_quota:
            return RateLimited(retry_after=self.get_time_remaining())

        return NotRateLimited

    def get_time_remaining(self):
        return int(self.ttl - (
            time.time() - int(time.time() / self.ttl) * self.ttl))

    def _get_system_key(self):
        return 'quota:s:%s' % (int(time.time() / self.ttl),)

    def _get_team_key(self, team):
        return 'quota:t:%s:%s' % (team.id, int(time.time() / self.ttl))

    def _get_project_key(self, project):
        return 'quota:p:%s:%s' % (project.id, int(time.time() / self.ttl))

    def _incr_project(self, project):
        if project.team:
            team_key = self._get_team_key(project.team)
        else:
            team_key = None
            team_result = None

        proj_key = self._get_project_key(project)
        sys_key = self._get_system_key()
        with self.cluster.map() as client:
            proj_result = client.incr(proj_key)
            client.expire(proj_key, self.ttl)
            sys_result = client.incr(sys_key)
            client.expire(sys_key, self.ttl)
            if team_key:
                team_result = client.incr(team_key)
                client.expire(team_key, self.ttl)

        return (
            int(sys_result.value),
            int(team_result and team_result.value or 0),
            int(proj_result.value),
        )
