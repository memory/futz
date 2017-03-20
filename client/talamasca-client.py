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

# the even server will only have the even-numbered lists populated
# and vice versa
LISTS = {0: list(xrange(0, 59, 2)),
         1: list(xrange(1, 60, 2))}

ZK_HOSTS = 'zookeeper:2181'
# give me a unique Id for the party
ME = str(uuid.uuid4())

logging.basicConfig(
    format='{}:s%(levelname)s:%(message)s'.format(ME), level=logging.INFO)


def exit_handler(party):
    # try to clean up our ZK state as politely as possible;
    # if we end up getting SIGKILLed this if for naught, but
    # ZK will figure it out in a few seconds.
    party.leave()


def zk_state(state):
    ''' TODO: if this were more than a toy application, this is
    where the logic for detecting zookeeper failures
    and attempting to reconnect would live; in the interests
    of not spending days on this task we will just exit
    if we ever lose the connection. '''
    if state == KazooState.LOST:
        if PREV_STATE == KazooState.LOST:
            # lost=>lost == initial startup
            logging.info('starting up...')
        if PREV_STATE == KazooState.CONNECTED:
            # connected => lost
            logging.warning('zookeeper connection lost')
            sys.exit(1)
        if PREV_STATE == KazooState.SUSPENDED:
            # suspended => lost
            logging.warning('zookeeper connection lost')
            sys.exit(1)
    elif state == KazooState.SUSPENDED:
        # Handle being disconnected from Zookeeper
        logging.warning('zookeeper connection suspended')
        sys.exit(1)
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
    # fast exit if there are 1 or >60 workers
    if my_position > 60:
        logging.fatal('There are already 60 clients, exiting')
        sys.exit(0)
    elif party_size == 1:
        logging.warning('only one client in the pool, taking all comers')
        return list(itertools.product(range(2), range(60)))
    my_parity = my_position % 2
    if my_parity:
        logging.info('targeting odd server')
        servers = (1,)
    else:
        servers = (0,)
        logging.info('targeting even server')
    peer_pool_size = count_peers(party_size, my_position)
    logging.info('%d clients with my parity', peer_pool_size)
    peer_pool_position = ((my_position + my_parity) / 2) - 1
    columns = LISTS[my_parity][peer_pool_position::peer_pool_size]
    work = list(itertools.product(servers, columns))
    logging.info('my work: %s', work)
    return work


def compute_averages(targets):
    for server in (0, 1):
        for column in [x[1] for x in targets if x[0] == server]:
            with REDIS[server].pipeline(transaction=True) as pipe:
                # grab all values
                pipe.lrange(column, 0, -1)
                # truncate list in place
                pipe.ltrim(column, 1, 0)
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
