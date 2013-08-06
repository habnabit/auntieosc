# Copyright (c) Aaron Gallagher <_@habnab.it>
# See COPYING for details.

import datetime
from itertools import izip_longest
import subprocess

import yaml


term_height, term_width = map(int, subprocess.check_output(['stty', 'size']).split())


def rankify(data):
    pad = len(str(len(data)))
    return ['%*d. %s' % (pad, e, x) for e, x in enumerate(data, start=1)]


def partition(data, groups):
    if groups == 1:
        return [data]
    span = (len(data) + groups) // groups
    ret = []
    for start in xrange(0, len(data), span):
        ret.append(data[start:start+span])
    return ret


def columnify(data):
    if not data:
        return

    best_columns = 0
    while best_columns < len(data):
        new_partitioned = partition(data, best_columns + 1)
        new_lengths = [max(len(x) for x in group) for group in new_partitioned]
        if sum(new_lengths) + len(new_lengths) * 2 > term_width - 1:
            break
        best_columns += 1
        partitioned = new_partitioned
        lengths = new_lengths
    for row in izip_longest(*partitioned, fillvalue=''):
        for length, cell in zip(lengths, row):
            sys.stdout.write(cell.ljust(length + 2))
        print


def main(infile_path):
    with open(infile_path) as infile:
        data = yaml.safe_load(infile)

    deduped = []
    seen_ids = set()
    for k, v in data.iteritems():
        if id(v) in seen_ids:
            continue
        deduped.append(v)
        seen_ids.add(id(v))

    data = {}
    for v in deduped:
        nicks = v['nicks']
        most_used_nick = max(nicks, key=nicks.get)
        data[most_used_nick] = v

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=999)
    new_data = {}
    for k, v in data.iteritems():
        if v['last-in-at'] < cutoff:
            continue
        new_data[k] = v

    data = new_data

    def idler_key(nick):
        visits = data[nick].get('visits', {})
        def g(bucket):
            return visits.get(bucket, 0)
        said_nothing = g(0) and not (g(1) or g(10) or g(100) or g(None))
        said_not_much = (g(0) or g(1)) and not (g(10) or g(100) or g(None))
        adjusted_time_spent = g(0) + g(1) - g(100) - g(None)
        return said_nothing, said_not_much, adjusted_time_spent

    keyed_data = sorted(((idler_key(k), k) for k in data), reverse=True)

    print 'top said-nothingers by time spent in channel:'
    columnify(rankify([k for key, k in keyed_data if key[0]]))
    print

    print 'top said-almost-nothingers by time spent in channel:'
    columnify(rankify([k for key, k in keyed_data if key[1] and not key[0]]))
    print

    print 'top idle-exceeds-active-visitors by time spent in channel:'
    columnify(rankify([k for key, k in keyed_data if key[2] > 0]))
    print

    print 'most talkative irc-ers:'
    columnify(rankify(['%s (%.3g)' % (k, data[k]['efficiency'])
                       for k in sorted(data, key=lambda k: data[k].get('total-lines', 0), reverse=True)
                       if data[k]['efficiency'] is not None]))


if __name__ == '__main__':
    import sys
    main(sys.argv[1])
