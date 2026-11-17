"""Closed schema-2 content, mandatory templates and evidence-bound paired output."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import tempfile
import textwrap

import legacy as v1

require, obj, text, array = v1.require, v1.obj, v1.text, v1.array
TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'
LANGUAGES = ('ru', 'en')
SLOTS = ('opening', 'comparison', 'diagram', 'initial', 'steps', 'impact',
         'reproduction', 'remediation', 'unknowns', 'appendix')
PLACEHOLDER = re.compile(r'\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b|\{\{.*?\}\}|<insert\b|<fill\b', re.I)
NUMBERS = re.compile(r'\d+(?:[.,]\d+)*')
STATUS = {
    'ru': {'source-supported': 'По исходному коду', 'observed': 'Наблюдалось в сохранённом выполнении', 'hypothetical': 'Предположение', 'unknown': 'Не установлено'},
    'en': {'source-supported': 'Source-supported', 'observed': 'Observed in saved execution', 'hypothetical': 'Hypothetical', 'unknown': 'Unknown'},
}
LABELS = {
    'ru': dict(severity='Критичность', conditions='Условия', scope='Границы вывода', stage='Этап', normal='Нормальный путь', finding='Путь находки', setup='Подготовка', input='Точный вход', values='Значения', meaning='Значение в сценарии', name='Имя', value='Значение', unit='Единица', explanation='Что происходит и почему', checks='Проверки и ветвление', condition='Условие', result='Результат проверки', state='Состояние и результат', next='Переход дальше', sources='Исходный код', no_sources='Фрагменты исходного кода отсутствуют; см. классификацию и пробелы.', no_checks='Проверки не указаны; см. классификацию и пробелы.', evidence='Доказательства', gaps='Пробелы', description='Что неизвестно', needed='Что требуется', verification='Как проверить', impact='Что ограничено', environment='Среда', history='История выполнения', expected='Ожидаемый результат', saved='Сохранённые результаты', control='Контрольная проверка', commands='Команды рецепта', cause='Причина', required='Требуемое поведение', proposal='Предложенное исправление', validation='Проверка исправления', context='Контекст', prerequisites='Предпосылки', entities='Участники', outcome='Итог', review='Независимое ревью', repository='Репозиторий', revision='Ревизия', reproduction_status='Статус выполнения', author='Автор', fingerprints='Файлы и отпечатки', none='Не указано.', diagram_note='Стрелка обозначает классифицированный переход; сама по себе она не доказывает доставку или успех. Подробности и проверки приведены в шагах.', pending='Запись в приложении не заменяет отдельную проверенную квитанцию ревью.'),
    'en': dict(severity='Severity', conditions='Conditions', scope='Scope', stage='Stage', normal='Normal path', finding='Finding path', setup='Setup', input='Exact input', values='Values', meaning='Scenario meaning', name='Name', value='Value', unit='Unit', explanation='What happens and why', checks='Checks and branching', condition='Condition', result='Check result', state='State and result', next='Next transition', sources='Source code', no_sources='No source excerpts are selected; see classification and gaps.', no_checks='No checks are declared; see classification and gaps.', evidence='Evidence', gaps='Gaps', description='What is unknown', needed='What is needed', verification='How to verify', impact='Conclusion limited', environment='Environment', history='Execution history', expected='Expected result', saved='Saved results', control='Control check', commands='Recipe commands', cause='Cause', required='Required behavior', proposal='Proposed remediation', validation='Remediation validation', context='Context', prerequisites='Prerequisites', entities='Participants', outcome='Outcome', review='Independent review', repository='Repository', revision='Revision', reproduction_status='Execution status', author='Author', fingerprints='Files and fingerprints', none='None declared.', diagram_note='An arrow describes a classified transition; it alone does not prove delivery or success. Numbered steps provide details and checks.', pending='Appendix prose does not replace a separately verified review receipt.'),
}
SEVERITY = {'ru': {'Critical': 'Критическая', 'High': 'Высокая', 'Medium': 'Средняя', 'Low': 'Низкая', 'undetermined': 'Не определена'}, 'en': {key: key for key in ('Critical', 'High', 'Medium', 'Low', 'undetermined')}}


def localized(value, label):
    obj(value, 'ru en', label)
    for language in LANGUAGES:
        text(value[language], f'{label}.{language}')
        require(not PLACEHOLDER.search(value[language]), f'{label}: incomplete placeholder text')
    require(NUMBERS.findall(value['ru']) == NUMBERS.findall(value['en']), f'{label}: numeric tokens differ between languages')


def verify_evidence(trace):
    """Check every declared file and every excerpt, including unselected sources."""
    for entry in trace['evidence']:
        path = Path(entry['path'])
        v1._reject_links(path)
        if entry['sha256'] is None:
            require(not path.exists(), f'declared missing evidence is now available: {entry["id"]}')
        else:
            require(path.is_file() and stat.S_ISREG(path.lstat().st_mode), f'evidence is not a regular file: {path}')
            require(v1.sha256(path) == entry['sha256'], f'evidence changed: {entry["id"]}')
    for step in trace['steps']:
        for source in step['sources']:
            language(source['language'])
            lines = Path(source['path']).read_text(encoding='utf-8').splitlines()
            require(source['end_line'] <= len(lines), 'source excerpt exceeds current file')
            actual = '\n'.join(lines[source['start_line'] - 1:source['end_line']])
            require(source['code'].replace('\r\n', '\n') in (actual, actual + '\n'), f'source excerpt differs at {source["path"]}:{source["start_line"]}')


def templates(version='2'):
    paths = {lang: TEMPLATES / f'REPORT.{lang}.template.md' for lang in LANGUAGES}
    for path in (TEMPLATES / 'VERSION', *paths.values()):
        v1._reject_links(path)
        require(path.is_file() and stat.S_ISREG(path.lstat().st_mode), f'missing regular template: {path}')
    require(version == '2' and (TEMPLATES / 'VERSION').read_text(encoding='utf-8').strip() == version, 'template version mismatch')
    contents = {lang: path.read_text(encoding='utf-8') for lang, path in paths.items()}
    for lang, content in contents.items():
        require(tuple(re.findall(r'\{\{(.*?)\}\}', content)) == SLOTS, f'{lang} template slots missing, duplicated, unknown or out of order')
        require(content.count('{{') == len(SLOTS) and content.count('}}') == len(SLOTS), 'invalid template delimiters')
    return contents


def validate_report(data):
    obj(data, 'schema_version template_version trace content', 'report')
    require(type(data['schema_version']) is int and data['schema_version'] == 2, 'schema_version must be 2; use explicit legacy commands or migrate')
    require(data['template_version'] == '2', 'template_version must be string 2')
    trace = v1.validate_report(data['trace'])
    evidence = {e['id']: e for e in trace['evidence']}
    gaps = {g['id']: g for g in trace['gaps']}
    claims = []

    def claim(value, label):
        obj(value, 'text status evidence_ids gap_ids', label)
        localized(value['text'], f'{label}.text')
        v1.claim(value, evidence, gaps, label)
        claims.append(value)

    def claim_list(value, label):
        array(value, label)
        require(value, f'{label} must not be empty')
        for i, item in enumerate(value):
            claim(item, f'{label}[{i}]')

    content = data['content']
    obj(content, 'title opening comparison initial steps impact reproduction remediation gaps appendix', 'content (migration drafts require complete bilingual authoring)')
    localized(content['title'], 'title')
    opening = content['opening']
    obj(opening, 'story severity conditions scope', 'opening')
    for key in ('story', 'conditions', 'scope'):
        claim(opening[key], f'opening.{key}')
    obj(opening['severity'], 'level reason', 'severity')
    require(isinstance(opening['severity']['level'], str) and opening['severity']['level'] in SEVERITY['en'], 'invalid severity level')
    localized(opening['severity']['reason'], 'severity.reason')
    array(content['comparison'], 'comparison')
    require(content['comparison'], 'comparison must not be empty')
    for row in content['comparison']:
        obj(row, 'stage normal finding', 'comparison row')
        localized(row['stage'], 'comparison.stage')
        claim(row['normal'], 'comparison.normal')
        claim(row['finding'], 'comparison.finding')
    initial = content['initial']
    obj(initial, 'setup input values', 'initial')
    claim_list(initial['setup'], 'initial.setup')
    obj(initial['input'], 'language value', 'initial.input')
    text(initial['input']['value'], 'initial.input.value', empty=True)
    language(initial['input']['language'])
    array(initial['values'], 'initial.values')
    require(initial['values'], 'initial.values must not be empty')
    for value in initial['values']:
        obj(value, 'name value unit meaning', 'initial value')
        for key in ('name', 'value', 'unit'):
            text(value[key], f'initial.values.{key}')
        localized(value['meaning'], 'initial.values.meaning')
    array(content['steps'], 'content.steps')
    require(len(content['steps']) == len(trace['steps']), 'content steps must match complete trace order')
    for index, step in enumerate(content['steps']):
        obj(step, 'id title diagram explanation sources checks state next', 'content step')
        original = trace['steps'][index]
        require(step['id'] == original['id'], 'content step IDs/order must match trace')
        localized(step['title'], 'step.title')
        localized(step['diagram'], 'step.diagram')
        for key in ('explanation', 'state', 'next'):
            claim(step[key], f'step.{key}')
        array(step['sources'], 'step.sources')
        require(all(type(i) is int and 0 <= i < len(original['sources']) for i in step['sources']), 'source index must select a source of this trace step')
        require(len(step['sources']) == len(set(step['sources'])), 'duplicate source indexes')
        array(step['checks'], 'step.checks')
        for check in step['checks']:
            obj(check, 'condition values result', 'check')
            for key in ('condition', 'values'):
                text(check[key], f'check.{key}')
            claim(check['result'], 'check.result')
    claim_list(content['impact'], 'impact')
    for section, keys in (('reproduction', 'environment setup history expected saved control commands'), ('remediation', 'cause required proposal validation checks')):
        obj(content[section], keys, section)
        for key in keys.split():
            if key == 'commands':
                array(content[section][key], 'commands')
                require(content[section][key], 'commands must not be empty')
                for command in content[section][key]:
                    text(command, 'command')
            else:
                claim_list(content[section][key], f'{section}.{key}')
    require(isinstance(content['gaps'], dict) and set(content['gaps']) == set(gaps), 'localized gap IDs must exactly match trace')
    for gap in content['gaps'].values():
        obj(gap, 'description needed verification impact', 'localized gap')
        for key in gap:
            localized(gap[key], f'gap.{key}')
    appendix = content['appendix']
    obj(appendix, 'context prerequisites entities evidence outcome review', 'appendix')
    for key, expected in (('context', set(trace['context'])), ('prerequisites', {p['id'] for p in trace['prerequisites']}), ('entities', {e['id'] for e in trace['entities']}), ('evidence', set(evidence))):
        require(isinstance(appendix[key], dict) and set(appendix[key]) == expected, f'appendix.{key} keys must match trace')
        for ident, value in appendix[key].items():
            localized(value, f'appendix.{key}.{ident}')
    for key in ('outcome', 'review'):
        localized(appendix[key], f'appendix.{key}')
    if trace['context']['reproduction_status'] != 'run':
        require(not any(c['status'] == 'observed' for c in claims), 'not-run cannot contain observed content claims, including check.result')
    templates(data['template_version'])
    verify_evidence(trace)
    return data


def language(value):
    text(value, 'code language')
    require(re.fullmatch(r'[A-Za-z0-9_+.-]+', value), 'code language must be a plain fence language token')


def mermaid(value, limit=None):
    """Keep Unicode/underscores readable; encode only sequence grammar controls."""
    flat = ' '.join(str(value).split())
    if limit is not None and len(flat) > limit:
        flat = flat[:limit - 1] + '…'
    # Semicolon, colon and hashes are grammar controls; markup is never trusted.
    lines = []
    for line in textwrap.wrap(flat, width=56, break_long_words=False, break_on_hyphens=False):
        encoded = ''.join(f'#{ord(c)};' if c in '#;&<>"\\:[]{}|`' else c for c in line)
        lines.append(re.sub(r'\bend\b', '#101;nd', encoded))
    return '<br/>'.join(lines)


def render_report(data, language):
    validate_report(data)
    require(language in LANGUAGES, 'language must be ru or en')
    lang = language
    t, c = data['trace'], data['content']
    labels = LABELS[lang]
    escape = v1.literal
    gap_anchors = {gap['id']: f'gap-{i}' for i, gap in enumerate(t['gaps'], 1)}

    def prose(value):
        return escape(value[lang])

    def fence(value, language=''):
        # Normalize accepted code line endings without changing legacy receipts.
        return v1.fence(value.replace('\r\n', '\n'), language)

    def claim(value):
        rendered = prose(value['text']) + ' *(' + STATUS[lang][value['status']] + ')*'
        if value['gap_ids']:
            links = [f'[{prose(c["gaps"][ident]["description"])}](#{gap_anchors[ident]})' for ident in value['gap_ids']]
            rendered += '\n\n' + labels['gaps'] + ': ' + ' '.join(links)
        return rendered

    def claims(values):
        return '\n\n'.join(claim(value) for value in values)

    def subsection(key, value, level=3):
        return f'{"#" * level} {labels[key]}\n\n{value}'

    def table_cell(value):
        return value.replace('\n', '<br/>')

    opening = [f'# {prose(c["title"])}', claim(c['opening']['story']),
               f'**{labels["severity"]}: {SEVERITY[lang][c["opening"]["severity"]["level"]]}**. {prose(c["opening"]["severity"]["reason"])}',
               subsection('conditions', claim(c['opening']['conditions'])),
               subsection('scope', claim(c['opening']['scope']))]
    comparison = [f'| {labels["stage"]} | {labels["normal"]} | {labels["finding"]} |', '| --- | --- | --- |']
    for row in c['comparison']:
        comparison.append('| ' + ' | '.join(table_cell(v) for v in (prose(row['stage']), claim(row['normal']), claim(row['finding']))) + ' |')
    participants = {entity['id']: f'p{i}' for i, entity in enumerate(t['entities'])}
    diagram = ['sequenceDiagram']
    for entity in t['entities']:
        diagram.append(f'    participant {participants[entity["id"]]} as {mermaid(c["appendix"]["entities"][entity["id"]][lang])}')
    for i, (step, original) in enumerate(zip(c['steps'], t['steps']), 1):
        arrow = '-->>' if original['kind'] == 'return' else '->>'
        label = mermaid(f'{i}. {step["diagram"][lang]}') + '<br/>' + mermaid(STATUS[lang][step['explanation']['status']])
        diagram.append(f'    {participants[original["from"]]}{arrow}{participants[original["to"]]}: {label}')
    initial = [subsection('setup', claims(c['initial']['setup'])), subsection('input', fence(c['initial']['input']['value'], c['initial']['input']['language']))]
    value_table = [f'### {labels["values"]}\n\n| {labels["name"]} | {labels["value"]} | {labels["unit"]} | {labels["meaning"]} |', '| --- | --- | --- | --- |']
    for value in c['initial']['values']:
        value_table.append('| ' + ' | '.join((escape(value['name']), escape(value['value']), escape(value['unit']), prose(value['meaning']))) + ' |')
    initial.append('\n'.join(value_table))
    steps = []
    for i, (step, original) in enumerate(zip(c['steps'], t['steps']), 1):
        steps += [f'### {i}. {prose(step["title"])}', subsection('explanation', claim(step['explanation']), 4), f'#### {labels["sources"]}']
        if not step['sources']:
            steps.append(labels['no_sources'])
        for index in step['sources']:
            source = original['sources'][index]
            label = f'{Path(source["path"]).name}:{source["start_line"]}–{source["end_line"]}'
            steps += [f'[{escape(label)}](<{v1.source_uri(source["path"], source["start_line"])}>)', fence(source['code'], source['language'])]
        steps.append(f'#### {labels["checks"]}')
        if not step['checks']:
            steps.append(labels['no_checks'])
        for check in step['checks']:
            steps += [f'**{labels["condition"]}:** {escape(check["condition"])}', f'**{labels["values"]}:** {escape(check["values"])}', f'**{labels["result"]}:** {claim(check["result"])}']
        steps += [subsection('state', claim(step['state']), 4), subsection('next', claim(step['next']), 4)]
    reproduction = []
    for key in ('environment', 'setup', 'history', 'expected', 'saved', 'control'):
        reproduction.append(subsection(key, claims(c['reproduction'][key])))
    reproduction.append(subsection('commands', '\n'.join(fence(command, 'text') for command in c['reproduction']['commands'])))
    remediation = [subsection(key, claims(c['remediation'][key])) for key in ('cause', 'required', 'proposal', 'validation', 'checks')]
    unknowns = []
    for i, entry in enumerate(t['gaps'], 1):
        ident = entry['id']
        gap = c['gaps'][ident]
        unknowns.append(f'<a id="{gap_anchors[ident]}"></a>')
        unknowns.append(f'### {i}. {prose(gap["description"])}')
        unknowns.extend(f'**{labels[key]}:** {prose(gap[key])}' for key in ('needed', 'verification', 'impact'))
    if not unknowns:
        unknowns.append(labels['none'])
    appendix = [f'**{labels["author"]}:** {escape(t["author"])}', f'**ID:** {escape(t["finding"]["id"])} · schema_version=2 · template_version=2', f'### {labels["context"]}']
    for key, value in c['appendix']['context'].items():
        appendix.append(f'**{labels[key]}:** {prose(value)}')
    appendix.append(f'### {labels["prerequisites"]}')
    for item in t['prerequisites']:
        appendix.append(f'**{escape(item["id"])}:** {prose(c["appendix"]["prerequisites"][item["id"]])} · {STATUS[lang][item["status"]]}\n\n' + escape(json.dumps({key: item[key] for key in ('evidence_ids', 'gap_ids')}, ensure_ascii=False)))
    if not t['prerequisites']:
        appendix.append(labels['none'])
    appendix.append(f'### {labels["entities"]}')
    for entity in t['entities']:
        appendix.append(f'**{escape(entity["id"])}:** {prose(c["appendix"]["entities"][entity["id"]])} · {escape(entity["kind"])}')
    appendix.append(f'### {labels["evidence"]} · {labels["fingerprints"]}')
    for entry in t['evidence']:
        appendix += [f'**{escape(entry["id"])}:** {prose(c["appendix"]["evidence"][entry["id"]])}',
                     fence(json.dumps({key: entry[key] for key in ('id', 'kind', 'path', 'sha256')}, ensure_ascii=False, indent=2), 'json')]
    if not t['evidence']:
        appendix.append(labels['none'])
    # Include even unselected source locations for inspection without duplicating prose.
    for original in t['steps']:
        metadata = {key: original[key] for key in ('id', 'from', 'to', 'kind', 'status', 'input', 'next', 'evidence_ids', 'gap_ids')}
        metadata['sources'] = [{key: source[key] for key in ('path', 'symbol', 'start_line', 'end_line', 'language', 'evidence_id')} for source in original['sources']]
        appendix.append(fence(json.dumps(metadata, ensure_ascii=False, indent=2), 'json'))
    appendix.append(f'### {labels["gaps"]}')
    for entry in t['gaps']:
        ident = entry['id']
        gap = c['gaps'][ident]
        appendix.append(f'**{escape(ident)}:** {prose(gap["description"])}')
    if not c['gaps']:
        appendix.append(labels['none'])
    appendix += [subsection('outcome', prose(c['appendix']['outcome'])), fence(json.dumps({key: t['outcome'][key] for key in ('status', 'evidence_ids', 'gap_ids')}, ensure_ascii=False, indent=2), 'json'), subsection('review', prose(c['appendix']['review']) + '\n\n' + labels['pending'])]
    sections = dict(opening='\n\n'.join(opening), comparison='\n'.join(comparison), diagram=labels['diagram_note'] + '\n\n' + fence('\n'.join(diagram), 'mermaid'), initial='\n\n'.join(initial), steps='\n\n'.join(steps), impact=claims(c['impact']), reproduction='\n\n'.join(reproduction), remediation='\n\n'.join(remediation), unknowns='\n\n'.join(unknowns), appendix='\n\n'.join(appendix))
    template = templates(data['template_version'])[lang]
    return re.sub(r'\{\{(.*?)\}\}', lambda match: sections[match[1]], template).rstrip() + '\n'


def _protected(data, report_path, receipt_path=None):
    protected = v1._protected(data['trace'], report_path)
    protected += [TEMPLATES / 'VERSION', *(TEMPLATES / f'REPORT.{lang}.template.md' for lang in LANGUAGES)]
    if receipt_path is not None:
        protected.append(Path(receipt_path))
    return protected


def _pair_paths(data, report_path, output_dir, receipt_path=None):
    require(v1._load_json(report_path) == data, 'report JSON differs from supplied content; reload current JSON')
    directory = Path(os.path.abspath(output_dir))
    v1._reject_links(directory)
    require(directory.is_dir(), 'output directory must already exist')
    protected = _protected(data, report_path, receipt_path)
    paths = {lang: v1._output_path(directory / f'REPORT.{lang}.md', protected) for lang in LANGUAGES}
    for path in paths.values():
        if path.exists():
            require(path.stat().st_nlink == 1, 'output must not have hardlink aliases')
            # A receipt placed at a Markdown output path is still protected data.
            try:
                existing = v1._load_json(path)
            except (ValueError, UnicodeError):
                existing = None
            require(not isinstance(existing, dict) or not {'reviewer', 'verdict', 'json_sha256'} <= set(existing), 'output contains a protected review receipt')
    if all(path.exists() for path in paths.values()):
        require(not os.path.samefile(paths['ru'], paths['en']), 'outputs alias each other')
    return paths


def write_pair(data, report_path, output_dir, replace=False):
    validate_report(data)
    paths = _pair_paths(data, report_path, output_dir)
    rendered = {lang: render_report(data, lang).encode('utf-8') for lang in LANGUAGES}
    pending = []
    for lang, path in paths.items():
        if path.exists() and path.read_bytes() == rendered[lang]:
            continue
        require(not path.exists() or replace, 'different output already exists; use --replace explicitly')
        require(os.access(path.parent, os.W_OK), 'output directory is not writable')
        pending.append(lang)
    staged = {}
    try:
        # Stage BOTH complete files before either destination changes.
        for lang in pending:
            with tempfile.NamedTemporaryFile(prefix='.walkthrough-', suffix='.tmp', dir=paths[lang].parent, delete=False) as stream:
                staged[lang] = Path(stream.name)
                stream.write(rendered[lang])
                stream.flush()
                os.fsync(stream.fileno())
        verify_evidence(data['trace'])
        _pair_paths(data, report_path, output_dir)
        for lang in pending:
            path = paths[lang]
            if path.exists():
                require(replace, 'output appeared during preflight; use --replace explicitly')
                os.replace(staged[lang], path)
            else:
                # Exclusive creation prevents overwriting a late external file.
                with path.open('xb') as stream:
                    stream.write(rendered[lang])
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def check_pair(data, report_path, output_dir, receipt_path=None):
    validate_report(data)
    paths = _pair_paths(data, report_path, output_dir, receipt_path)
    for lang, path in paths.items():
        require(path.is_file(), f'missing {lang} Markdown')
        require(path.read_bytes() == render_report(data, lang).encode('utf-8'), f'stale {lang} Markdown: regenerate pair')


def review_check_pair(data, report_path, output_dir, receipt_path):
    check_pair(data, report_path, output_dir, receipt_path)
    receipt_file = Path(receipt_path)
    v1._reject_links(receipt_file)
    require(receipt_file.is_file() and stat.S_ISREG(receipt_file.lstat().st_mode), 'receipt must be a regular file')
    receipt = v1._load_json(receipt_file)
    obj(receipt, 'schema_version author reviewer verdict json_sha256 markdown_sha256 template_version template_sha256 evidence_sha256 findings', 'receipt')
    require(type(receipt['schema_version']) is int and receipt['schema_version'] == 2, 'receipt.schema_version must be 2')
    for key in ('author', 'reviewer'):
        text(receipt[key], f'receipt.{key}')
    require(receipt['author'] == data['trace']['author'] and receipt['reviewer'].strip().casefold() != receipt['author'].strip().casefold(), 'receipt requires matching author and distinct independently dispatched reviewer')
    array(receipt['findings'], 'receipt.findings')
    require(receipt['verdict'] == 'accepted' and not receipt['findings'], 'review not accepted or unresolved findings remain')
    v1.digest(receipt['json_sha256'], 'receipt.json_sha256')
    require(receipt['json_sha256'] == v1.sha256(report_path), 'stale receipt JSON fingerprint')
    require(receipt['template_version'] == data['template_version'], 'stale receipt template version')
    for key in ('markdown_sha256', 'template_sha256'):
        obj(receipt[key], 'ru en', f'receipt.{key}')
        for lang in LANGUAGES:
            v1.digest(receipt[key][lang], f'receipt.{key}.{lang}')
            path = Path(output_dir) / f'REPORT.{lang}.md' if key == 'markdown_sha256' else TEMPLATES / f'REPORT.{lang}.template.md'
            require(receipt[key][lang] == v1.sha256(path), f'stale receipt {key}.{lang}')
    expected = {entry['id']: entry['sha256'] for entry in data['trace']['evidence']}
    require(isinstance(receipt['evidence_sha256'], dict) and receipt['evidence_sha256'] == expected, 'receipt must bind complete current evidence map')
