#!/usr/bin/env python

from flask import Flask
from flask_restplus import Resource, Api

import redis

import datetime
import os
import time

app = Flask(__name__)
api = Api(app)

REDIS = {
    'even': redis.StrictRedis(host='redis-even', port=6379, db=0),
    'odd': redis.StrictRedis(host='redis-odd', port=6379, db=0)
}

MAX_RETRIES = 3
MIN_DELAY = 1  # seconds
DELAY_FACTOR = 2


def backoff(func, *args, **kwargs):
    delay = kwargs.get('delay', 1)
    attempt = kwargs.get('attempt', 1)
    if attempt > MAX_RETRIES:
        api.abort(500)
    try:
        app.logger.error('*** attempt: %d\n' % attempt)
        func(args)
        return
    except Exception as ex:
        # TODO: if this were a real app, we'd probably try to
        # vary our approach based on the exception.
        app.logger.error(ex.message)
        app.logger.error(
            '*** backing off %d seconds\n' % delay)
        time.sleep(delay)
        delay = delay * DELAY_FACTOR
        backoff(func, args, delay=delay, attempt=attempt+1)


@api.route('/ingest')
class Ingest(Resource):
    def get(self):
        now = datetime.datetime.utcnow()
        sec = now.second
        ms = now.microsecond / 1000.0
        if sec % 2:
            parity = 'odd'
        else:
            parity = 'even'
        backoff(REDIS[parity].lpush, sec, ms)
        return {'parity': parity,
                'sec': sec,
                'ms': ms,
                'we watch': 'and we are always there'}

if __name__ == '__main__':
    app.run(debug=True if 'DEBUG' in os.environ else False,
            host='0.0.0.0',
            port=int(os.environ.get('PORT', 80)),
            threaded=True)
