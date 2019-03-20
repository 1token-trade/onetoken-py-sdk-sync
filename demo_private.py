# -*- coding: utf-8 -*-
import json
import time
import requests
import sys

try:
    from urllib.parse import urlparse
except:
    # noinspection PyUnresolvedReferences
    from urlparse import urlparse
import hmac
import hashlib


class Secret:
    ot_key = ''
    ot_secret = ''


def gen_nonce():
    return str(int(time.time() * 1000000))


py3 = sys.version_info > (3, 0)


def gen_sign(secret, verb, url, nonce, data_str):
    """Generate a request signature compatible with BitMEX."""
    # Parse the url so we can remove the base and extract just the path.

    if data_str is None:
        data_str = ''

    parsed_url = urlparse(url)
    path = parsed_url.path

    # print "Computing HMAC: %s" % verb + path + str(nonce) + data
    message = verb + path + str(nonce) + data_str
    # print(message)

    if py3:
        signature = hmac.new(bytes(secret, 'utf8'), bytes(message, 'utf8'), digestmod=hashlib.sha256).hexdigest()
    else:
        signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return signature


def api_call(method, endpoint, params=None, data=None, timeout=15):
    assert params is None or isinstance(params, dict)
    assert data is None or isinstance(data, dict)
    method = method.upper()

    nonce = gen_nonce()

    url = "https://1token.trade/api/v1/trade" + endpoint

    json_str = json.dumps(data) if data else ''
    sign = gen_sign(Secret.ot_secret, method, endpoint, nonce, json_str)
    headers = {'Api-Nonce': str(nonce), 'Api-Key': Secret.ot_key, 'Api-Signature': sign,
               'Content-Type': 'application/json'}
    res = requests.request(method, url=url, data=json_str, params=params, headers=headers, timeout=timeout)
    return res


def demo(account):
    print('查看账户信息')
    r = api_call('GET', '/{}/info'.format(account))
    print(r.json())

    print('撤销所有订单')
    r = api_call('DELETE', '/{}/orders/all'.format(account))
    print(r.json())

    print('下单')
    r = api_call('POST', '/{}/orders'.format(account),
                 data={'contract': 'okex/btc.usdt', 'price': 10, 'bs': 'b', 'amount': 1})
    print(r.json())
    exg_oid = r.json()['exchange_oid']

    print('查询挂单 应该有一个挂单')
    r = api_call('GET', '/{}/orders'.format(account))
    print(r.json())

    print('用 exchange oid撤单')
    r = api_call('DELETE', '/{}/orders'.format(account), params={'exchange_oid': exg_oid})
    print(r.json())

    print('查询挂单 应该没有挂单')
    r = api_call('GET', '/{}/orders'.format(account))
    print(r.json())


def main():
    ot_key = input('ot-key: ')
    ot_secret = input('ot-secret: ')
    account = input('请输入交易账号 账号格式是 {交易所}/{交易账户名} 比如 okex/mock-1token: ')
    Secret.ot_key = ot_key
    Secret.ot_secret = ot_secret

    demo(account)


if __name__ == '__main__':
    main()
