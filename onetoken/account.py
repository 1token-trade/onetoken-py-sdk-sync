import json
import threading

try:
    import thread
except ImportError:
    import _thread as thread
import time
import queue
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
import websocket


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


class WS(threading.Thread):
    IDLE = 'idle'
    GOING_TO_CONNECT = 'going-to-connect'
    CONNECTING = 'connecting'
    READY = 'ready'
    GOING_TO_DICCONNECT = 'going-to-disconnect'

    def __init__(self, api_key, api_secret, exchange, account):
        super().__init__()
        self.is_running = True
        self.api_key = api_key
        self.api_secret = api_secret
        self.account = account
        self.exchange = exchange
        self.host_ws = get_ws_host(exchange, account)
        self.ws = None  # type: (websocket.WebSocketApp, None)
        self.ws_state = self.IDLE
        self.ws_support = True
        self.last_pong = 0
        self.sub_queue = {}

    def set_ws_state(self, new, reason=''):
        log.info(f'set ws state from {self.ws_state} to {new}', reason)
        self.ws_state = new

    def keep_connection(self):
        def run():
            while self.is_running:
                if not self.ws_support:
                    break
                if self.ws_state == self.GOING_TO_CONNECT:
                    self.ws_connect()
                elif self.ws_state == self.READY:
                    try:
                        while self.ws.keep_running:
                            ping = datetime.now().timestamp()
                            self.ws.send(json.dumps({'uri': 'ping', 'uuid': ping}))
                            time.sleep(10)
                            if self.last_pong < ping:
                                log.warning('ws connection heartbeat lost')
                                break
                    except:
                        log.exception('ws connection ping failed')
                    finally:
                        self.set_ws_state(self.GOING_TO_CONNECT, 'heartbeat lost')
                elif self.ws_state == self.GOING_TO_DICCONNECT:
                    self.ws.close()
                time.sleep(1)

        thread.start_new_thread(run, ())

    @property
    def ws_path(self):
        return self.host_ws

    def ws_connect(self):
        self.set_ws_state(self.CONNECTING)
        nonce = gen_nonce()
        sign = gen_sign(self.api_secret, 'GET', f'/ws/{self.account}', nonce, None)
        headers = {'Api-Nonce': str(nonce), 'Api-Key': self.api_key, 'Api-Signature': sign}
        url = self.ws_path
        try:
            self.ws = websocket.WebSocketApp(url,
                                             header=headers,
                                             on_message=self.on_message,
                                             on_error=self.on_error,
                                             on_close=self.on_close)

        except:
            self.set_ws_state(self.GOING_TO_CONNECT, 'ws connect failed')
            log.exception('ws connect failed')
            time.sleep(5)
        else:
            log.info('ws connected.')

    def on_message(self, message):
        try:
            data = json.loads(message)
            log.debug(data)
            if 'uri' not in data:
                if 'code' in data:
                    code = data['code']
                    if code == 'no-router-found':
                        log.warning('ws push not supported for this exchange {}'.format(self.exchange))
                        self.ws_support = False
                        return
                log.warning('unexpected msg get', data)
                return
            action = data['uri']
            if action == 'pong':
                self.last_pong = datetime.now().timestamp()
                return
            if action in ['connection', 'status']:
                if data.get('code', data.get('status', None)) in ['ok', 'connected']:
                    self.set_ws_state(self.READY, 'Connected and auth passed.')
                    for key in self.sub_queue.keys():
                        self.ws.send(json.dumps({'uri': 'sub-{}'.format(key)}))
                else:
                    self.set_ws_state(self.GOING_TO_CONNECT, data['message'])
            elif action == 'info':
                if data.get('status', 'ok') == 'ok':
                    if 'info' not in self.sub_queue:
                        return
                    info = data['data']
                    info = Info(info)
                    for handler in self.sub_queue['info'].values():
                        try:
                            handler(info)
                        except:
                            log.exception('handle info error')
            elif action == 'order' and 'order' in self.sub_queue:
                if data.get('status', 'ok') == 'ok':
                    for order in data['data']:
                        exg_oid = order['exchange_oid']
                        log.debug('order info updating', exg_oid, status=order['status'])
                        if exg_oid not in self.sub_queue['order']:
                            q = queue.Queue()
                            self.sub_queue['order'][exg_oid] = q
                            self.order_dequeued(exg_oid)
                        self.sub_queue['order'][exg_oid].put(order)
                        if '*' in self.sub_queue['order']:
                            h = self.sub_queue['order']['*']
                            h(order)
                else:
                    # todo 这里处理order 拿到 error 的情况
                    log.warning('order update error message', data)
            else:
                log.info(f'receive message {data}')
        except Exception as e:
            log.warning('unexpected msg format', message, e)

    def order_dequeued(self, exg_oid):
        def run():
            timeout = 10
            bg = datetime.now()
            while 'order' in self.sub_queue and exg_oid in self.sub_queue['order'] \
                    and not self.sub_queue['order'][exg_oid].empty():
                if (datetime.now() - bg).total_seconds() > timeout:
                    del self.sub_queue['order'][exg_oid]
                    break
                time.sleep(2)

        thread.start_new_thread(run, ())

    def subscribe_info(self, handler, handler_name=None):
        if not self.ws_support:
            log.warning('ws push not supported for this exchange {}'.format(self.exchange))
            return
        if 'info' not in self.sub_queue:
            self.sub_queue['info'] = {}
        if handler_name is None:
            handler_name = 'default'
        self.sub_queue['info'][handler_name] = handler
        if self.ws_state == self.READY:
            self.ws.send(json.dumps({'uri': 'sub-info'}))
        elif self.ws_state == self.IDLE:
            self.set_ws_state(self.GOING_TO_CONNECT, 'user sub info')

    def unsubscribe_info(self, handler_name=None):
        if handler_name is None:
            handler_name = 'default'
        if 'info' in self.sub_queue:
            del self.sub_queue['info'][handler_name]
            if len(self.sub_queue['info']) == 0 and self.ws_state == self.READY:
                self.ws.send(json.dumps({'uri': 'unsub-info'}))
                del self.sub_queue['info']
            if not self.sub_queue and self.ws_state != self.IDLE:
                self.set_ws_state(self.GOING_TO_DICCONNECT, 'subscribe nothing')

    def subscribe_orders(self, handler=None):
        if 'order' not in self.sub_queue:
            self.sub_queue['order'] = {}
        if handler is not None:
            self.sub_queue['order']['*'] = handler
        if self.ws_state == self.READY:
            self.ws.send(json.dumps({'uri': 'sub-order'}))
        elif self.ws_state == self.IDLE:
            self.set_ws_state(self.GOING_TO_CONNECT, 'user sub order')

    def unsubcribe_orders(self):
        if 'order' in self.sub_queue:
            del self.sub_queue['order']
        if self.ws_state == self.READY:
            self.ws.send(json.dumps({'uri': 'unsub-order'}))
        if not self.sub_queue and self.ws_state != self.IDLE:
            self.set_ws_state(self.GOING_TO_DICCONNECT, 'subscribe nothing')

    @staticmethod
    def on_error(ws, error):
        print(error)

    @staticmethod
    def on_close(ws):
        print("### closed ###")

    def run(self) -> None:
        while self.is_running:
            if self.ws:
                self.ws.on_open = self.keep_connection
                self.ws.run_forever()
            else:
                self.ws_connect()


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
        self.ws = WS(api_key=self.api_key, api_secret=self.api_secret, exchange=self.exchange, account=self.name)
        self.ws.setDaemon(True)
        self.ws.start()
        self.host = get_trans_host(self.exchange)
        if session is None:
            self.session = requests.session()
        else:
            self.session = session
        self.sub_queue = {}

    def __str__(self):
        return '<{}>'.format(self.symbol)

    def __repr__(self):
        return '<{}:{}>'.format(self.__class__.__name__, self.symbol)

    @property
    def trans_path(self):
        return '{}/{}'.format(self.host, self.name)

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
