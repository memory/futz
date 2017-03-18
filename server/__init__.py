#!/usr/bin/env python

from flask import Flask
from flask_restplus import Resource, Api

import redis

import datetime

app = Flask(__name__)
api = Api(app)

even_redis = redis.StrictRedis(host='localhost', port=6379, db=0)
odd_redis = redis.StrictRedis(host='localhost', port=6380, db=0)


@api.route('/ingest')
class Ingest(Resource):
    def get(self):
        now = datetime.datetime.utcnow()
        sec = now.second
        ms = now.microsecond / 1000.0
        if sec % 2:
            parity = 'odd'
            odd_redis.lpush(sec, ms)
        else:
            parity = 'even'
            even_redis.lpush(sec, ms)
        return {'parity': parity,
                'sec': sec,
                'ms': ms,
                'we watch': 'and we are always there'}

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
