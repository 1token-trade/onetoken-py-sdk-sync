import json
import random
import string

import arrow
import requests


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
    oid = f'{contract_symbol}-{now}{rand}'
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
    cwid = f'{exchange}/{currency}-{now}-{rand}'
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
