from __future__ import division

import argparse
import datetime

from dateutil.parser import parse as parse_datetime
import parsley
import yaml


irssi_grammar_source = """

nl = '\n'
skip_to_end = <(~nl anything)*>:content nl -> content
word = <(~' ' ~nl anything)+>
nick = <(~' ' ~nl ~':' ~'>' anything)+>:channel (':' (~' ' ~'>' anything)+)? -> channel
timestamp = <digit{2}>:hour ':' <digit{2}>:minute -> datetime.time(int(hour), int(minute))

log_opened = '--- Log opened ' skip_to_end:when -> ('base', None, parse_datetime(when))
log_closed = '--- Log closed ' skip_to_end -> ('cruft', None, None)
day_changed = '--- Day changed ' skip_to_end:when -> ('base', None, parse_datetime(when))
date_line = log_opened | log_closed | day_changed

presence_action_word = ('joined' | 'left' | 'quit')
presence_action = '(-) ' nick:nick ' ' word ' has ' presence_action_word:action ' ' skip_to_end -> (action, nick)
kicked = '(-) ' nick:nick ' was kicked ' skip_to_end -> ('kicked', nick)
privmsg = '<' anything nick:nick '> ' skip_to_end -> ('msg', nick)
emote = ' * ' nick:nick ' ' skip_to_end -> ('msg', nick)
nick_change = '(-) ' nick:oldnick ' is now known as ' nick:newnick skip_to_end -> ('nick', (oldnick, newnick))
cruft = skip_to_end:cruft -> ('cruft', cruft)

line = timestamp:when ' ' (presence_action | privmsg | emote | nick_change | cruft):(action, arg) -> (action, when, arg)

document = (date_line | line)*

"""

irssi_parser = parsley.makeGrammar(
    irssi_grammar_source, dict(parse_datetime=parse_datetime, datetime=datetime))


class Auntieosc(object):
    lines_buckets = [0, 1, 10, 100]

    def __init__(self):
        self.users = {}

    def main(self, argv=()):
        parser = argparse.ArgumentParser()
        parser.add_argument('infiles', type=argparse.FileType('rb'), nargs='+')
        parser.add_argument('-r', '--read')
        parser.add_argument('-w', '--write')
        args = parser.parse_args(argv)

        if args.read:
            with open(args.read, 'rb') as infile:
                self.users = yaml.safe_load(infile)

        base_datetime = None
        for infile in args.infiles:
            with infile:
                contents = infile.read()
            events = irssi_parser(contents).document()
            for action, when, arg in events:
                if action == 'base':
                    base_datetime = arg
                    continue
                if when is not None:
                    when = base_datetime.combine(base_datetime, when)
                action_method = getattr(self, 'action_' + action, None)
                if action_method is not None:
                    action_method(when, arg)

        if args.write:
            with open(args.write, 'wb') as outfile:
                yaml.safe_dump(self.users, outfile, default_flow_style=False)

    def user(self, nick):
        return self.users.setdefault(nick, {'nicks': {nick: 1}, 'n-visits': 1})

    def action_joined(self, when, nick):
        user = self.user(nick)
        user['joined-at'] = when
        user['lines'] = 0
        # do something with this eventually
        user.pop('last-in-at', None)

    def action_msg(self, when, nick):
        user = self.user(nick)
        user.setdefault('joined-at', when)
        user['lines'] = user.get('lines', 0) + 1
        user['last-talked-at'] = when

    def action_quit(self, when, nick):
        user = self.user(nick)
        user['last-in-at'] = when
        joined_at = user.pop('joined-at', None)
        if not joined_at:
            return
        time_spent = (when - joined_at).total_seconds()
        lines = user.pop('lines', 0)
        for bucket in self.lines_buckets:
            if lines <= bucket:
                break
        else:
            bucket = None
        visits = user.setdefault('visits', {})
        visits[bucket] = visits.get(bucket, 0) + time_spent
        user['n-visits'] = user.get('n-visits', 0) + 1

    action_left = action_kicked = action_quit

    def action_nick(self, when, (oldnick, newnick)):
        user = self.user(oldnick)
        user['nicks'][newnick] = user['nicks'].get(newnick, 0) + 1
        if newnick not in self.users:
            self.users[newnick] = user
        self.action_quit(when, oldnick)
        self.action_joined(when, newnick)

if __name__ == '__main__':
    import sys
    Auntieosc().main(sys.argv[1:])
