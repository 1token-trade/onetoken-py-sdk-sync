from pathlib import Path

import yaml


def test_demo():
    p = Path('~/.onetoken/config.yml').expanduser()
    from demo_private import demo, Secret
    if p.exists():
        x = p.read_text()
        x = yaml.load(x)
        print(x['ot_key'][:3])
        print(x['ot_secret'][:3])
        Secret.ot_key = x['ot_key']
        Secret.ot_secret = x['ot_secret']
    else:
        import os
        Secret.ot_key = os.environ['OTKEY']
        Secret.ot_secret = os.environ['OTSECRET']

    demo('okex/mock-1token-demo')
