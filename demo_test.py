import os

import yaml


def test_demo():
    p = os.path.expanduser('~/.onetoken/config.yml')
    from demo_private import demo, Secret
    if os.path.exists(p):
        x = open(p).read()
        x = yaml.safe_load(x)
        print(x['ot_key'][:3])
        print(x['ot_secret'][:3])
        Secret.ot_key = x['ot_key']
        Secret.ot_secret = x['ot_secret']
    else:
        Secret.ot_key = os.environ['OTKEY']
        Secret.ot_secret = os.environ['OTSECRET']

    demo('okex/mock-1token-demo')
