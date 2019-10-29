import hashlib
import hmac
import json
import random
import string
import time
from urllib.parse import urlparse

import arrow
import requests

from .config import Config
from .logger import log


def rand_id(length=10):
    assert length >= 1

    first = random.choice(string.ascii_lowercase + string.ascii_uppercase)
    after = ''.join(random.choice(string.ascii_lowercase + string.ascii_uppercase + string.digits)
                    for _ in range(length - 1))

    r = first + after
    return r


def rand_client_oid(contract_symbol):
    """
        binance/btc.usdt-20190816152332asdfqwer123450
    :param contract_symbol:
    :return:
    """
    now = arrow.now().format('YYYYMMDDHHmmss')
    rand = rand_id(14)
    oid = '%s-%s%s' % (contract_symbol, now, rand)
    return oid


def rand_client_wid(exchange, currency):
    """
    binance/xxx-yearmonthday-hourminuteseconds-random
    :param exchange:
    :param currency:
    :return:
    """
    now = arrow.now().format('YYYYMMDD-HHmmss')
    rand = rand_id(5)
    cwid = '%s/%s-%s-%s' % (exchange, currency, now, rand)
    return cwid


def http_go(func, url, method='json', accept_4xx=False, **kwargs):
    """

    :param func:
    :param url:
    :param method:
        json -> return json dict
        raw -> return raw object
        text -> return string
    :param accept_4xx:
    :param kwargs:
    :return:
    """
    from . import HTTPError
    assert not accept_4xx
    assert method in ['json', 'text', 'raw']
    try:
        # if 'params' not in kwargs or kwargs['params'] is None:
        #     kwargs['params'] = {}
        # params = kwargs['params']
        # params['source'] = 'onetoken-py-sdk-sync'

        resp = func(url, **kwargs)
    except requests.Timeout:
        return None, HTTPError(HTTPError.TIMEOUT, '')
    except requests.HTTPError as e:
        return None, HTTPError(HTTPError.HTTP_ERROR, str(e))

    txt = resp.text
    if resp.status_code >= 500:
        return None, HTTPError(HTTPError.RESPONSE_5XX, txt)
    if 400 <= resp.status_code < 500:
        return None, HTTPError(HTTPError.RESPONSE_4XX, txt)

    if method == 'raw':
        return resp, None
    elif method == 'text':
        return txt, None
    elif method == 'json':
        try:
            return json.loads(txt), None
        except:
            return None, HTTPError(HTTPError.NOT_JSON, txt)


_requests_sess = None


def get_requests_sess():
    global _requests_sess
    if _requests_sess is None:
        _requests_sess = requests.session()
        _requests_sess.close()
    return _requests_sess


def load_ot_from_config_file():
    import os
    config = os.path.expanduser('~/.onetoken/config.yml')
    if os.path.isfile(config):
        log.info('load ot_key and ot_secret from %s' % config)
        import yaml
        js = yaml.safe_load(open(config).read())
        ot_key, ot_secret = js.get('ot_key'), js.get('ot_secret')
        return ot_key, ot_secret
    else:
        log.warning('load %s fail' % config)
        return None, None


def gen_nonce():
    return str(int(time.time() * 1000000))


def get_trans_host(exg):
    return '{}/{}'.format(Config.TRADE_HOST, exg)


def get_ws_host(exg, name):
    return '{}/{}/{}'.format(Config.TRADE_HOST_WS, exg, name)


def get_name_exchange(symbol):
    sp = symbol.split('/', 1)
    return sp[1], sp[0]


def gen_sign(secret, verb, endpoint, nonce, data_str):
    # Parse the url so we can remove the base and extract just the path.

    if data_str is None:
        data_str = ''

    parsed_url = urlparse(endpoint)
    path = parsed_url.path

    message = verb + path + str(nonce) + data_str
    signature = hmac.new(bytes(secret, 'utf8'), bytes(message, 'utf8'), digestmod=hashlib.sha256).hexdigest()
    return signature
