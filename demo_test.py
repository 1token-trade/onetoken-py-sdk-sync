from pathlib import Path

import yaml


def test_demo():
    x = Path('~/.onetoken/config.yml').expanduser().read_text()
    x = yaml.load(x)
    print(x['ot_key'][:3])
    print(x['ot_secret'][:3])
    from demo_private import demo, Secret
    Secret.ot_key = x['ot_key']
    Secret.ot_secret = x['ot_secret']
    demo('okex/mock-1token')
