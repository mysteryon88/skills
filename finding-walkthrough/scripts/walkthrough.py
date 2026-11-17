"""Offline schema-2 bilingual finding reports; explicit read-only legacy inspection."""
import argparse
import json
from pathlib import Path
import sys

import legacy
from legacy import sha256
from bilingual import (validate_report, render_report, write_pair, check_pair,
                       review_check_pair, mermaid, verify_evidence)


def load_report(path):
    return validate_report(legacy._load_json(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('validate', 'render', 'check', 'show', 'review-check', 'migrate',
                 'legacy-validate', 'legacy-check', 'legacy-review-check', 'legacy-show'):
        command = commands.add_parser(name)
        command.add_argument('report')
        if name in ('render', 'migrate'):
            command.add_argument('--output-dir' if name == 'render' else '--output', required=True)
            if name == 'render':
                command.add_argument('--replace', action='store_true')
        elif name.endswith('check'):
            command.add_argument('output_dir' if not name.startswith('legacy-') else 'markdown')
            if name.endswith('review-check'):
                command.add_argument('receipt')
        elif name.endswith('show'):
            selection = command.add_mutually_exclusive_group(required=True)
            selection.add_argument('--step')
            selection.add_argument('--index', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command.startswith('legacy-') or args.command == 'migrate':
            data = legacy.load_report(args.report)
            if args.command == 'migrate':
                path = Path(args.output).absolute()
                legacy._reject_links(path)
                legacy.require(path.parent.is_dir(), 'migration output parent must already exist')
                for protected in legacy._protected(data, args.report):
                    legacy.require(path != protected.absolute(), 'migration output collides with protected input')
                draft = {'schema_version': 2, 'template_version': '2', 'trace': data, 'content': {}}
                with path.open('x', encoding='utf-8', newline='\n') as stream:
                    json.dump(draft, stream, ensure_ascii=False, indent=2)
                    stream.write('\n')
            elif args.command == 'legacy-check':
                legacy.check_markdown(data, args.report, args.markdown)
            elif args.command == 'legacy-review-check':
                legacy.review_check(data, args.report, args.markdown, args.receipt)
            elif args.command == 'legacy-show':
                selected = [{'ordinal': i, 'id': step['id'], 'title': step['title'], 'status': step['status'], 'next': step['next']} for i, step in enumerate(data['steps'], 1)] if args.index else legacy.select_step(data, args.step)
                print(json.dumps(selected, ensure_ascii=False, indent=2))
            return 0
        data = load_report(args.report)
        if args.command == 'render':
            write_pair(data, args.report, args.output_dir, args.replace)
        elif args.command == 'check':
            check_pair(data, args.report, args.output_dir)
        elif args.command == 'review-check':
            review_check_pair(data, args.report, args.output_dir, args.receipt)
        elif args.command == 'show':
            if args.index:
                selected = [{'ordinal': i, 'id': s['id'], 'title': s['title'], 'status': data['trace']['steps'][i-1]['status']} for i, s in enumerate(data['content']['steps'], 1)]
            else:
                matches = [i for i, s in enumerate(data['trace']['steps']) if s['id'] == args.step]
                legacy.require(matches, 'unknown step ID')
                i = matches[0]
                selected = {'trace': legacy.select_step(data['trace'], args.step), 'content': data['content']['steps'][i]}
            print(json.dumps(selected, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError, RecursionError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
