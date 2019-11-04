import json
import time
from typing import Tuple, Union

import requests

from . import util
from .logger import log
from .model import Info
from .account_ws import AccountWs


class Account:
    def __init__(self, symbol: str, api_key: str = None, api_secret: str = None, session: requests.sessions = None):
        """
        Account初始化
        :param symbol: account symbol, binance/test_user1
        :param api_key: ot-key in 1token
        :param api_secret: ot-secret in 1token
        """
        self.symbol = symbol
        if api_key is None and api_secret is None:
            self.api_key, self.api_secret = util.load_ot_from_config_file()
        else:
            self.api_key = api_key
            self.api_secret = api_secret
        log.debug('account init {}'.format(symbol))
        self.name, self.exchange = util.get_name_exchange(symbol)
        if '/' in self.name:
            self.name, margin_contract = self.name.split('/', 1)
            self.margin_contract = '%s/%s' % (self.exchange, margin_contract)
        else:
            self.margin_contract = None
        self.host = util.get_trans_host(self.exchange)
        if session is None:
            self.session = requests.session()
        else:
            self.session = session
        self._ws = AccountWs(self.symbol, self.api_key, self.api_secret)

    def __str__(self):
        return '<{}>'.format(self.symbol)

    def __repr__(self):
        return '<{}:{}>'.format(self.__class__.__name__, self.symbol)

    @property
    def ws(self):
        """
        获取websocket实例
        :return: AccountWS
        """
        return self._ws

    def ws_start(self):
        """
        开启websocket
        :return: None
        """
        self._ws.run()

    def ws_close(self):
        """
        关闭websocket
        :return: None
        """
        self._ws.close()

    def ws_subscribe_info(self, handler, handler_name=None):
        """
        websocket 订阅 账号信息
        :param handler: func 接收到信息的回调函数
        :param handler_name: 回调方法名称
        :return: None
        """
        self._ws.subscribe_info(handler, handler_name)

    def ws_subscribe_orders(self, handler, handler_name=None):
        """
        websocket 订阅 订单信息
        :param handler: func 接收到信息的回调函数
        :param handler_name: 回调方法名称
        :return: None
        """
        self._ws.subscribe_orders(handler, handler_name)

    @property
    def trans_path(self):
        """
        api url
        :return: https://1token.trade/api/v1/trade/exg_name/acc_name
        """
        return '{}/{}'.format(self.host, self.name)

    def get_pending_list(self, contract=None):
        """
        获取 active 状态订单
        :param contract: 交易对 binance/btc.usdt
        :return: dict
        """
        return self.get_order_list(contract)

    def get_order_list(self, contract=None, state=None):
        """
        获取订单
        :param contract: 交易对 binance/btc.usdt
        :param state: 订单状态 end
        :return: dict
        """
        data = {}
        if contract:
            data['contract'] = contract
        if state:
            data['state'] = state
        t = self.api_call('get', '/orders', params=data)
        return t

    def cancel_use_client_oid(self, oid, *oids):
        """
        使用client oid 撤单, 支持批量撤单
        :param oid: 单号 binance/btc.usdt-xxxxxxx
        :param oids:
        :return: dict
        """
        if oids:
            oid = oid + ',' + ",".join(oids)
        log.debug('Cancel use client oid', oid)

        data = {'client_oid': oid}
        t = self.api_call('delete', '/orders', params=data)
        return t

    def cancel_use_exchange_oid(self, oid, *oids):
        """
        使用exchange oid 撤单, 支持批量撤单
        :param oid: 单号 binance/btc.usdt-xxxxxxx
        :param oids:
        :return: dict
        """
        if oids:
            oid = oid + ',' + ",".join(oids)
        log.debug('Cancel use exchange oid', oid)
        data = {'exchange_oid': oid}
        t = self.api_call('delete', '/orders', params=data)
        return t

    def cancel_all(self, contract=None):
        """
        撤掉全部订单，contract 为None会撤掉所有交易对下的订单（需交易所支持）
        :param contract: 交易对 binance/btc.usdt
        :return: dict
        """
        log.debug('Cancel all')
        if contract:
            data = {'contract': contract}
        else:
            data = {}
        t = self.api_call('delete', '/orders/all', params=data)
        return t

    def get_info(self, timeout=15) -> Tuple[Union[Info, None], Union[Exception, None]]:
        """
        获取账户信息
        :param timeout: 超时时间
        :return: Info, Error
        """
        y, err = self.api_call('get', '/info', timeout=timeout)
        if err:
            return None, err
        if not isinstance(y, dict):
            return None, ValueError('%s not dict' % y)
        acc_info = Info(y)
        if self.margin_contract is not None:
            pos_symbol = self.margin_contract.split('/', 1)[-1]
            return acc_info.get_margin_acc_info(pos_symbol), None
        return acc_info, None

    def place_and_cancel(self, con, price, bs, amount, sleep, options=None):
        """
        下单后撤单
        :param con: 交易对 binance/btc.usdt
        :param price: 下单价格
        :param bs: 交易方向 b/s
        :param amount: 下单数量
        :param sleep: 下单后多久撤单 单位(s)
        :param options: 额外参数
        :return: dict
        """
        k = util.rand_client_oid(con)
        res1, err1 = self.place_order(con, price, bs, amount, client_oid=k, options=options)
        if err1:
            return (res1, None), (err1, None)
        time.sleep(sleep)
        res2, err2 = self.cancel_use_client_oid(k)
        if err1 or err2:
            return (res1, res2), (err1, err2)
        return [res1, res2], None

    def get_order_use_client_oid(self, oid, *oids):
        """
        使用client oid 查询订单, 支持批量查询
        :param oid: 单号 binance/btc.usdt-xxxxxxx
        :param oids:
        :return: dict
        """
        if oids:
            oid = oid + ',' + ",".join(oids)
        res = self.api_call('get', '/orders', params={'client_oid': oid})
        log.debug(res)
        return res

    def get_order_use_exchange_oid(self, oid, *oids):
        """
        使用exchange oid 查询订单, 支持批量查询
        :param oid: 单号 binance/btc.usdt-xxxxxxx
        :param oids:
        :return: dict
        """
        if oids:
            oid = oid + ',' + ",".join(oids)
        res = self.api_call('get', '/orders', params={'exchange_oid': oid})
        log.debug(res)
        return res

    def place_order(self, con, price, bs, amount, client_oid=None, options=None):
        """
        下单
        :param con: 交易对 binance/btc.usdt
        :param price: 下单价格
        :param bs: 交易方向 b/s
        :param amount: 下单数量
        :param client_oid: 用户id （需交易所支持）
        :param options: 额外参数 {}
        :return: dict
        """
        log.debug('Place order', con=con, price=price, bs=bs, amount=amount, client_oid=client_oid)

        data = {'contract': con,
                'price': price,
                'bs': bs,
                'amount': amount}
        if client_oid:
            data['client_oid'] = client_oid
        if options:
            data['options'] = options
        res = self.api_call('post', '/orders', data=data)
        log.debug(res)
        return res

    def get_dealt_trans(self, con=None):
        """
        获取成交记录
        :param con: 交易对 binance/btc.usdt
        :return: dict
        """
        data = {}
        if con is not None:
            data['contract'] = con
        res = self.api_call('get', '/trans', params=data)
        return res

    def api_call(self, method, endpoint, params=None, data=None, timeout=15):
        """

        :param method:
        :param endpoint:
        :param params:
        :param data:
        :param timeout:
        :return: dict, Error
        """
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

        nonce = util.gen_nonce()
        url = self.trans_path + endpoint
        json_str = json.dumps(data) if data else ''
        sign = util.gen_sign(self.api_secret, method, '/{}/{}{}'.format(self.exchange, self.name, endpoint), nonce,
                             json_str)
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
