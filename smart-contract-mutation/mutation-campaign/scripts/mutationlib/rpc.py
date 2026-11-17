"""Read-only EVM and Toncenter block pinning; no transaction submission surface."""
import json
import os
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .storage import CampaignError, now


READ_METHODS = {'eth_chainId', 'eth_getBlockByNumber', 'eth_getBlockByHash', 'eth_getCode', 'eth_getBalance', 'eth_getStorageAt', 'eth_call'}


def rpc_request(url, method, params):
    if method not in READ_METHODS:
        raise CampaignError('RPC method is not on the read-only allowlist')
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    request = Request(url, data=body, headers={'Content-Type': 'application/json', 'User-Agent': 'local-mutation-campaign'})
    with urlopen(request, timeout=20) as response:
        raw = json.loads(response.read(4 * 1024 * 1024))
    if 'error' in raw or raw.get('result') is None:
        raise CampaignError('RPC endpoint did not supply the requested pinned state')
    return raw['result']


def pin_evm(endpoints, requested=None, chain_id=None, request=rpc_request):
    expected_hash = requested.get('hash') if isinstance(requested, dict) else None
    number = requested.get('number') if isinstance(requested, dict) else requested
    if number is None and expected_hash is None:
        selector, method = 'finalized', 'eth_getBlockByNumber'
    elif isinstance(number, str) and len(number) == 66:
        selector, method, expected_hash = number, 'eth_getBlockByHash', number
    elif number is None:
        selector, method = expected_hash, 'eth_getBlockByHash'
    else:
        selector = hex(int(number, 0) if isinstance(number, str) else number)
        method = 'eth_getBlockByNumber'
    errors = []
    for index, url in enumerate(endpoints):
        try:
            actual_chain = int(request(url, 'eth_chainId', []), 16)
            if chain_id is not None and actual_chain != chain_id:
                raise CampaignError('endpoint chain ID differs from project configuration')
            block = request(url, method, [selector, False])
            if expected_hash and block['hash'].lower() != expected_hash.lower():
                raise CampaignError('pinned block hash mismatch/reorg')
            actual_number = int(block['number'], 16)
            if method == 'eth_getBlockByNumber' and selector != 'finalized' and actual_number != int(selector, 16):
                raise CampaignError('endpoint returned a different historical block')
            return {'kind': 'evm', 'chain_id': actual_chain, 'number': actual_number, 'hash': block['hash'], 'selection': selector, 'endpoint_index': index, 'endpoint_host': urlsplit(url).hostname, 'checked_at': now(), 'read_semantics': 'local execution with lazy read-only RPC; not an offline chain snapshot'}
        except (OSError, ValueError, KeyError, CampaignError) as exc:
            errors.append(type(exc).__name__)
    raise CampaignError('all endpoints failed to validate the exact requested EVM block (' + ','.join(errors) + '); historical pin was not replaced')


def ton_request(url, method, params):
    if method not in ('getMasterchainInfo', 'lookupBlock'):
        raise CampaignError('unsupported read-only TON pin method')
    with urlopen(Request(url.rstrip('/') + '/' + method + ('?' + urlencode(params) if params else ''), headers={'User-Agent': 'local-mutation-campaign'}), timeout=20) as response:
        raw = json.loads(response.read(1024 * 1024))
    if not raw.get('ok'):
        raise CampaignError('TON endpoint did not supply requested masterchain state')
    return raw['result']


def pin_ton(endpoints, requested=None, request=ton_request):
    fields = ('workchain', 'shard', 'seqno', 'root_hash', 'file_hash')
    for index, endpoint in enumerate(endpoints):
        try:
            if requested is None:
                block = request(endpoint, 'getMasterchainInfo', {})['last']
            else:
                seqno = requested['seqno'] if isinstance(requested, dict) else int(requested)
                block = request(endpoint, 'lookupBlock', {'workchain': -1, 'shard': '-9223372036854775808', 'seqno': seqno})
            if int(block['workchain']) != -1:
                raise CampaignError('TON pin is not a masterchain block')
            pin = {k: block[k] for k in fields}
            if requested is not None:
                expected = requested if isinstance(requested, dict) else {'seqno': int(requested)}
                if any(str(pin[k]) != str(v) for k, v in expected.items() if k in fields):
                    raise CampaignError('TON block identity differs on fallback/reorg')
            return {'kind': 'ton', **pin, 'endpoint_index': index, 'endpoint_host': urlsplit(endpoint).hostname, 'checked_at': now()}
        except (OSError, ValueError, KeyError, CampaignError):
            continue
    raise CampaignError('no endpoint validated the requested TON block; do not replace it')


def pin_from_scope(config, previous=None):
    names = config.get('rpc_envs', [])
    if not names or any(not os.environ.get(name) for name in names):
        raise CampaignError('configured RPC environment variable missing; endpoint/key is never saved in report')
    endpoints = [os.environ[name] for name in names]
    if config['kind'] == 'evm':
        requested = {'number': previous['number'], 'hash': previous['hash']} if previous else config.get('block')
        if previous and config.get('chain_id') is not None and config['chain_id'] != previous['chain_id']:
            raise CampaignError('project chain ID differs from stored fork identity')
        pin = pin_evm(endpoints, requested, previous['chain_id'] if previous else config.get('chain_id'))
    elif config['kind'] == 'ton':
        requested = {k: previous[k] for k in ('workchain', 'shard', 'seqno', 'root_hash', 'file_hash')} if previous else config.get('block')
        pin = pin_ton(endpoints, requested)
    else:
        raise CampaignError('unknown fork protocol')
    pin['endpoint_env'] = names[pin['endpoint_index']]
    return pin
