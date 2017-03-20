#!/usr/bin/env python

# stdlib imports
import atexit
import itertools
import logging
import signal
import sys
import time
import uuid

# third party imports
import redis

from kazoo.client import KazooClient, KazooState
from kazoo.recipe.party import Party

# we watch, and we are always there
PREFIX = '/talamasca'
# this always starts at lost
PREV_STATE = KazooState.LOST

REDIS = {0: redis.StrictRedis(host='redis-even', port=6379, db=0),
         1: redis.StrictRedis(host='redis-odd', port=6379, db=0)}

ZK_HOSTS = ['zookeeper:2181']
# 60 lists, 0-59, on each server
LISTS = range(60)
# give me a unique Id
ME = str(uuid.uuid4())

logging.basicConfig(
    format='{}:s%(levelname)s:%(message)s'.format(ME), level=logging.INFO)


def exit_handler(party):
    # try to clean up our ZK state as politely as possible;
    # if we end up getting SIGKILLed this if for naught, but
    # ZK will figure it out in a few seconds.
    party.leave()


def zk_state(state):
    if state == KazooState.LOST:
        if PREV_STATE == KazooState.LOST:
            # lost=>lost == initial startup
            logging.info('starting up...')
        if PREV_STATE == KazooState.CONNECTED:
            # connected => lost
            logging.warning('zookeeper connection lost')
        if PREV_STATE == KazooState.SUSPENDED:
            # suspended => lost
            logging.warning('zookeeper connection lost')
    elif state == KazooState.SUSPENDED:
        # Handle being disconnected from Zookeeper
        logging.warning('zookeeper connection suspended')
    else:
        # Handle being connected/reconnected to Zookeeper
        logging.info('connected to zookeeper')
        pass


def get_my_position(party, me):
    # there doesn't seem to be a way to do this in constant time :(
    for count, ident in enumerate(party, start=1):
        if ident == me:
            return count


def count_peers(party_size, my_position):
    # there's probably a oneliner to do this but I have a headache
    party_parity = party_size % 2
    my_parity = my_position % 2
    if party_parity:
        if my_parity:
            # party size odd, I am odd
            return (party_size + 1) / 2
        else:
            # party size odd, I am even
            return ((party_size + 1) / 2) - 1
    else:
        # party size is even, so always equally divided
        return party_size / 2


def get_work(party_size, my_position):
    # fast exit if there are 1 or >120 workers
    if my_position > 120:
        logging.fatal('There are already 120 clients, exiting')
        sys.exit(0)
    elif party_size == 1:
        logging.warning('only one client in the pool, taking all comers')
        return list(itertools.product(range(2), range(60)))
    my_parity = my_position % 2
    if my_parity:
        logging.info('targeting odd servers')
        servers = (1,)
    else:
        servers = (0,)
        logging.info('targeting even servers')
    peer_pool_size = count_peers(party_size, my_position)
    logging.info('%d clients with my parity', peer_pool_size)
    peer_pool_position = ((my_position + my_parity) / 2) - 1
    lists = LISTS[peer_pool_position::peer_pool_size]
    return list(itertools.product(servers, lists))


def compute_averages(targets):
    for server in (0, 1):
        for column in [x[1] for x in targets if x[0] == server]:
            # don't bother fetching from empty lists
            if server % 2 == column % 2:
                pipe = REDIS[server].pipeline(transaction=True)
                pipe.lrange(column, 0, -1)
                pipe.ltrim(column, -1, 0)
                vals = pipe.execute()[0]
                if len(vals) is 0:
                    avg = 'NaN'
                else:
                    avg = sum([float(x) for x in vals]) / len(vals)
                logging.info('average ms for server %s, list %s: %s',
                             server, column, avg)


def summarize_me(signum, frame):
    party_size = len(party)
    logging.info('there are %s clients in the party', party_size)
    my_position = get_my_position(party, ME)
    logging.info('my place in the party is: %d', (my_position))
    targets = get_work(party_size, my_position)
    logging.debug('%d assigned targets: %s', len(targets), targets)
    compute_averages(targets)
    # reset the alarm
    signal.alarm(1)


zk = KazooClient(hosts=ZK_HOSTS)
zk.start()
zk.add_listener(zk_state)
zk.ensure_path(PREFIX)
party = Party(zk, PREFIX, identifier=ME)
atexit.register(exit_handler, party)
party.join()

signal.signal(signal.SIGALRM, summarize_me)
signal.alarm(5)

while True:
    time.sleep(300)
