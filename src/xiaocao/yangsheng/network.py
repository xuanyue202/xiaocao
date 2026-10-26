"""Bounded PAC restoration guardian, invoked only around verified native refresh."""
import argparse
import json
import select
import subprocess
import sys
from pathlib import Path


def command(*args):
    return subprocess.check_output(['networksetup', *args], text=True, timeout=10).strip()


def snapshot():
    return {key: command(action, 'Wi-Fi') for key, action in [('pac', '-getautoproxyurl'), ('http', '-getwebproxy'), ('https', '-getsecurewebproxy'), ('socks', '-getsocksfirewallproxy')]}


def fields(value):
    return dict(line.split(': ', 1) for line in value.splitlines() if ': ' in line)


def restore(before, owned_url):
    if snapshot() == before:
        return {'restored': True, 'foreign_configuration_preserved': False}
    current = fields(command('-getautoproxyurl', 'Wi-Fi'))
    old = fields(before['pac'])
    if current.get('URL') != owned_url:
        return {'restored': snapshot() == before, 'foreign_configuration_preserved': True}
    command('-setautoproxystate', 'Wi-Fi', 'off')
    command('-setautoproxyurl', 'Wi-Fi', old['URL'])
    command('-setautoproxystate', 'Wi-Fi', 'on' if old.get('Enabled') == 'Yes' else 'off')
    return {'restored': snapshot() == before, 'foreign_configuration_preserved': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--receipt', required=True)
    parser.add_argument('--wait-for-owner', action='store_true')
    args = parser.parse_args()
    payload = json.loads(sys.stdin.readline())
    print('armed', flush=True)
    select.select([sys.stdin], [], [], None if args.wait_for_owner else 60)
    try: proof = restore(payload['before'], payload['owned_url'])
    except Exception as error: proof = {'restored': False, 'error_type': type(error).__name__}
    Path(args.receipt).write_text(json.dumps(proof, indent=2))
