import json
import time
from queue import Queue
from typing import Tuple, Union
from datetime import datetime
import jwt
import requests

from . import log
from .config import Config
from . import util

try:
    from urllib.parse import urlparse
except ImportError:
    # noinspection PyUnresolvedReferences
    from urlparse import urlparse
import hmac
import hashlib
from .model import Info, Order


def gen_nonce():
    return str(int(time.time() * 1000000))


def get_trans_host(exg):
    return '{}/{}'.format(Config.TRADE_HOST, exg)


def get_ws_host(exg, name):
    return '{}/{}/{}'.format(Config.TRADE_HOST_WS, exg, name)


def get_name_exchange(symbol):
    sp = symbol.split('/', 1)
    return sp[1], sp[0]


def gen_jwt(secret, uid):
    payload = {
        'user': uid,
    }
    c = jwt.encode(payload, secret, algorithm='RS256', headers={'iss': 'qb-trade', 'alg': 'RS256', 'typ': 'JWT'})
    return c.decode('ascii')


def gen_sign(secret, verb, endpoint, nonce, data_str):
    # Parse the url so we can remove the base and extract just the path.

    if data_str is None:
        data_str = ''

    parsed_url = urlparse(endpoint)
    path = parsed_url.path

    message = verb + path + str(nonce) + data_str
    signature = hmac.new(bytes(secret, 'utf8'), bytes(message, 'utf8'), digestmod=hashlib.sha256).hexdigest()
    return signature


IDLE = 'idle'
GOING_TO_CONNECT = 'going-to-connect'
CONNECTING = 'connecting'
READY = 'ready'
GOING_TO_DICCONNECT = 'going-to-disconnect'


class Account:
    def __init__(self, symbol: str, api_key: str = None, api_secret: str = None, session: requests.sessions = None):
        """
        :param symbol: account symbol, binance/test_user1
        :param api_key: ot-key in 1token
        :param api_secret: ot-secret in 1token
        """
        self.symbol = symbol
        if api_key is None and api_secret is None:
            self.api_key, self.api_secret = self.load_ot_from_config_file()
        else:
            self.api_key = api_key
            self.api_secret = api_secret
        log.debug('account init {}'.format(symbol))
        self.name, self.exchange = get_name_exchange(symbol)
        if '/' in self.name:
            self.name, margin_contract = self.name.split('/', 1)
            self.margin_contract = f'{self.exchange}/{margin_contract}'
        else:
            self.margin_contract = None
        self.host = get_trans_host(self.exchange)
        self.host_ws = get_ws_host(self.exchange, self.name)
        if session is None:
            self.session = requests.session()
        else:
            self.session = session
        self.ws = None
        self.ws_state = IDLE
        self.ws_support = True
        self.last_pong = 0
        self.closed = False
        self.sub_queue = {}

    def close(self):
        if self.ws and not self.ws.closed:
            self.ws.close()
        if self.session and not self.session.closed:
            self.session.close()
        self.closed = True

    def __str__(self):
        return '<{}>'.format(self.symbol)

    def __repr__(self):
        return '<{}:{}>'.format(self.__class__.__name__, self.symbol)

    @property
    def trans_path(self):
        return '{}/{}'.format(self.host, self.name)

    @property
    def ws_path(self):
        return self.host_ws

    def get_pending_list(self, contract=None):
        return self.get_order_list(contract)

    def get_order_list(self, contract=None, state=None, source=None):
        data = {}
        if contract:
            data['contract'] = contract
        if state:
            data['state'] = state
        if source is not None:
            data['helper'] = source
        t = self.api_call('get', '/orders', params=data)
        return t

    def get_order_list_from_db(self, contract=None, state=None):
        return self.get_order_list(contract, state, source='db')

    def cancel_use_client_oid(self, oid, *oids):
        """
        cancel order use client oid, support batch
        :param oid:
        :param oids:
        :return:
        """
        if oids:
            oid = f'{oid},{",".join(oids)}'
        log.debug('Cancel use client oid', oid)

        data = {'client_oid': oid}
        t = self.api_call('delete', '/orders', params=data)
        return t

    def cancel_use_exchange_oid(self, oid, *oids):
        """
        cancel order use exchange oid, support batch
        :param oid:
        :param oids:
        :return:
        """
        if oids:
            oid = f'{oid},{",".join(oids)}'
        log.debug('Cancel use exchange oid', oid)
        data = {'exchange_oid': oid}
        t = self.api_call('delete', '/orders', params=data)
        return t

    def cancel_all(self, contract=None):
        log.debug('Cancel all')
        if contract:
            data = {'contract': contract}
        else:
            data = {}
        t = self.api_call('delete', '/orders/all', params=data)
        return t

    def get_info(self, timeout=15) -> Tuple[Union[Info, None], Union[Exception, None]]:
        y, err = self.api_call('get', '/info', timeout=timeout)
        if err:
            return None, err
        if not isinstance(y, dict):
            return None, ValueError(f'{y} not dict')
        acc_info = Info(y)
        if self.margin_contract is not None:
            pos_symbol = self.margin_contract.split('/', 1)[-1]
            return acc_info.get_margin_acc_info(pos_symbol), None
        return acc_info, None

    def place_and_cancel(self, con, price, bs, amount, sleep, options=None):
        k = util.rand_client_oid(con)
        res1, err1 = self.place_order(con, price, bs, amount, client_oid=k, options=options)
        if err1:
            return (res1, None), (err1, None)
        time.sleep(sleep)
        res2, err2 = self.cancel_use_client_oid(k)
        if err1 or err2:
            return (res1, res2), (err1, err2)
        return [res1, res2], None

    def get_status(self):
        return self.api_call('get', '/status')

    def get_order_use_client_oid(self, oid, *oids):
        """
        :param oid:
        :param oids:
        :return:
        """
        if oids:
            oid = f'{oid},{",".join(oids)}'
        res = self.api_call('get', '/orders', params={'client_oid': oid})
        log.debug(res)
        return res

    def get_order_use_exchange_oid(self, oid, *oids):
        """
        :param oid:
        :param oids:
        :return:
        """
        if oids:
            oid = f'{oid},{",".join(oids)}'
        res = self.api_call('get', '/orders', params={'exchange_oid': oid})
        log.debug(res)
        return res

    def amend_order_use_client_oid(self, client_oid, price, amount):
        """
        :param price:
        :param amount:
        :param client_oid:
        :return:
        """
        log.debug('Amend order use client oid', client_oid, price, amount)

        data = {'price': price,
                'amount': amount}
        params = {'client_oid': client_oid}
        res = self.api_call('patch', '/orders', data=data, params=params)
        log.debug(res)
        return res

    def amend_order_use_exchange_oid(self, exchange_oid, price, amount):
        """
        :param price:
        :param amount:
        :param exchange_oid:
        :return:
        """
        log.debug('Amend order use exchange oid', exchange_oid, price, amount)

        data = {'price': price,
                'amount': amount}
        params = {'exchange_oid': exchange_oid}
        res = self.api_call('patch', '/orders', data=data, params=params)
        log.debug(res)
        return res

    def place_order(self, con, price, bs, amount, client_oid=None, tags=None, options=None):
        """
        just pass request, and handle order update --> fire callback and ref_key
        :param options:
        :param con:
        :param price:
        :param bs:
        :param amount:
        :param client_oid:
        :param tags: a key value dict
        :return:
        """
        log.debug('Place order', con=con, price=price, bs=bs, amount=amount, client_oid=client_oid)

        data = {'contract': con,
                'price': price,
                'bs': bs,
                'amount': amount}
        if client_oid:
            data['client_oid'] = client_oid
        if tags:
            data['tags'] = ','.join(['{}:{}'.format(k, v) for k, v in tags.items()])
        if options:
            data['options'] = options
        res = self.api_call('post', '/orders', data=data)
        log.debug(res)
        return res

    def get_dealt_trans(self, con=None, source=None):
        """
        get recent dealt transactions
        :param source:
        :param con:
        :return:
        """
        # log.debug('Get dealt trans', con=con)
        data = {}
        if con is not None:
            data['contract'] = con
        if source is not None:
            data['helper'] = source
        res = self.api_call('get', '/trans', params=data)
        # log.debug(res)
        return res

    def get_dealt_trans_from_db(self, con=None):
        """
       get recent dealt transactions
       :param con:
       :return:
       """
        return self.get_dealt_trans(con, source='db')

    def post_withdraw(self, currency, amount, address, fee=None, client_wid=None, options=None):
        log.debug('Post withdraw', currency=currency, amount=amount, address=address, fee=fee, client_wid=client_wid)
        if client_wid is None:
            client_wid = util.rand_client_wid(self.exchange, currency)
        data = {
            'currency': currency,
            'amount': amount,
            'address': address
        }
        if fee is not None:
            data['fee'] = fee
        if client_wid:
            data['client_wid'] = client_wid
        if options:
            data['options'] = json.dumps(options)
        res = self.api_call('post', '/withdraws', data=data)
        log.debug(res)
        return res

    def cancel_withdraw_use_exchange_wid(self, exchange_wid):
        log.debug('Cancel withdraw use exchange_wid', exchange_wid)
        data = {'exchange_wid': exchange_wid}
        return self.api_call('delete', '/withdraws', params=data)

    def cancel_withdraw_use_client_wid(self, client_wid):
        log.debug('Cancel withdraw use client_wid', client_wid)
        data = {'client_wid': client_wid}
        return self.api_call('delete', '/withdraws', params=data)

    def get_withdraw_use_exchange_wid(self, exchange_wid):
        log.debug('Cancel withdraw use exchange_wid', exchange_wid)
        data = {'exchange_wid': exchange_wid}
        return self.api_call('get', '/withdraws', params=data)

    def get_withdraw_use_client_wid(self, client_wid):
        log.debug('Cancel withdraw use client_wid', client_wid)
        data = {'client_wid': client_wid}
        return self.api_call('get', '/withdraws', params=data)

    def get_deposit_list(self, currency):
        log.debug('Get deposit list', currency)
        data = {'currency': currency}
        return self.api_call('get', '/deposits', params=data)

    def get_deposit_addr_list(self, currency):
        log.debug('Get deposit address list', currency)
        data = {'currency': currency}
        return self.api_call('get', '/deposits/addresses', params=data)

    def get_loan_records(self, contract=None):
        if contract is None:
            contract = self.margin_contract
        log.debug('Get loan orders', contract)
        data = {'contract': contract}
        return self.api_call('get', '/loan-records', params=data)

    def borrow(self, currency, amount, contract=None):
        if contract is None:
            contract = self.margin_contract
        log.debug('Borrow', contract, currency, amount)
        data = {'contract': contract, 'currency': currency, 'amount': amount}
        return self.api_call('post', '/borrow', data=data)

    def repay(self, exchange_loan_id, currency, amount):
        log.debug('Repay', exchange_loan_id, currency, amount)
        data = {'exchange_loan_id': exchange_loan_id, 'currency': currency, 'amount': amount}
        return self.api_call('post', '/return', data=data)

    def margin_transfer_in(self, currency, amount, contract=None):
        if contract is None:
            contract = self.margin_contract
        log.debug('Margin transfer in', contract, currency, amount)
        data = {'contract': contract, 'currency': currency, 'amount': amount, 'target': 'margin'}
        return self.api_call('post', '/assets-internal', data=data)

    def margin_transfer_out(self, currency, amount, contract=None):
        if contract is None:
            contract = self.margin_contract
        log.debug('Margin transfer out', contract, currency, amount)
        data = {'contract': contract, 'currency': currency, 'amount': amount, 'target': 'spot'}
        return self.api_call('post', '/assets-internal', data=data)

    @property
    def is_running(self):
        return not self.closed

    def api_call(self, method, endpoint, params=None, data=None, timeout=15):
        method = method.upper()
        if method == 'GET':
            func = self.session.get
        elif method == 'POST':
            func = self.session.post
        elif method == 'PATCH':
            func = self.session.patch
        elif method == 'DELETE':
            func = self.session.delete
        else:
            raise Exception('Invalid http method:{}'.format(method))

        nonce = gen_nonce()

        url = self.trans_path + endpoint

        json_str = json.dumps(data) if data else ''
        sign = gen_sign(self.api_secret, method, '/{}/{}{}'.format(self.exchange, self.name, endpoint), nonce, json_str)
        headers = {
            'Api-Nonce': str(nonce),
            'Api-Key': self.api_key,
            'Api-Signature': sign,
            'Content-Type': 'application/json'
        }
        res, err = util.http_go(func, url=url, data=json_str, params=params, headers=headers, timeout=timeout)
        if err:
            return None, err
        return res, None

    @staticmethod
    def load_ot_from_config_file():
        import os
        config = os.path.expanduser('~/.onetoken/config.yml')
        if os.path.isfile(config):
            log.info(f'load ot_key and ot_secret from {config}')
            import yaml
            js = yaml.safe_load(open(config).read())
            ot_key, ot_secret = js.get('ot_key'), js.get('ot_secret')
            if ot_key is None:
                ot_key = js.get('api_key')
            if ot_secret is None:
                ot_secret = js.get('api_secret')
            return ot_key, ot_secret
        else:
            log.warning(f'load {config} fail')
            return None, None
