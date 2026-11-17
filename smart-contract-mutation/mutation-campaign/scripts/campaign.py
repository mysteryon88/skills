#!/usr/bin/env python3
"""Run project-local mutation campaigns; see references/protocol.md for scope JSON."""
import argparse
import json
from pathlib import Path
import sys

from mutationlib.isolation import init_campaign
from mutationlib.storage import CampaignError, load_campaign, read_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init'); init.add_argument('--project', required=True); init.add_argument('--scope', required=True)
    successor = sub.add_parser('successor', help='freeze named baseline test/config repairs in a hash-linked child campaign')
    successor.add_argument('parent'); successor.add_argument('--lane', required=True); successor.add_argument('--destination', required=True)
    successor.add_argument('--scope', required=True, help='updated scope JSON for the successor'); successor.add_argument('--repair', required=True, action='append')
    successor.add_argument('--specification', required=True, action='append'); successor.add_argument('--reason', required=True)
    for command in ('run', 'resume', 'status', 'cancel', 'finish', 'bind-runtime', 'deliver', 'verify'):
        s = sub.add_parser(command); s.add_argument('campaign')
        if command in ('run', 'resume'):
            s.add_argument('--background', action='store_true')
    triage = sub.add_parser('triage'); triage.add_argument('campaign'); triage.add_argument('--file', required=True)
    retest = sub.add_parser('retest'); retest.add_argument('campaign'); retest.add_argument('--file', required=True)
    job = sub.add_parser('agent-job'); job.add_argument('campaign'); job.add_argument('--file', required=True)
    args = p.parse_args()
    try:
        if args.command == 'init':
            result = {'campaign': str(init_campaign(Path(args.project), read_json(args.scope)))}
        elif args.command == 'successor':
            from mutationlib.successor import create_successor
            result = create_successor(Path(args.parent), args.lane, Path(args.destination), read_json(args.scope), args.repair, args.specification, args.reason)
        elif args.command == 'status':
            result = load_campaign(args.campaign)[0]
        elif args.command in ('run', 'resume'):
            from mutationlib.runner import launch, supervise
            result = launch(args.campaign, args.command == 'resume') if args.background else supervise(args.campaign, args.command == 'resume')
        elif args.command == 'cancel':
            from mutationlib.runner import cancel
            result = cancel(args.campaign)
        elif args.command == 'triage':
            from mutationlib.results import save_triage, report
            result = save_triage(Path(args.campaign), read_json(args.file))
            report(Path(args.campaign))
        elif args.command == 'retest':
            from mutationlib.retest import run_retest
            result = run_retest(Path(args.campaign), read_json(args.file))
        elif args.command == 'agent-job':
            from mutationlib.runtimes import agent_job
            result = agent_job(Path(args.campaign), read_json(args.file))
        elif args.command in ('bind-runtime', 'deliver', 'verify'):
            from mutationlib.runtimes import start_runtime, deliver_event, verify_campaign
            result = {'bind-runtime': start_runtime, 'deliver': lambda run: deliver_event(run, reset_attempts=True), 'verify': verify_campaign}[args.command](Path(args.campaign))
        else:
            from mutationlib.results import finish
            result = finish(Path(args.campaign))
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except (CampaignError, OSError, ValueError, KeyError) as exc:
        from mutationlib.storage import redact
        print(json.dumps({'error': redact(str(exc))}, ensure_ascii=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
