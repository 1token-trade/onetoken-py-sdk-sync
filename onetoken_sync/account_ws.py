import _thread as thread
import json
import time
from datetime import datetime

import websocket

from . import util
from .logger import log
from .model import Info


class AccountWs:
    IDLE = 'idle'
    GOING_TO_CONNECT = 'going-to-connect'
    CONNECTING = 'connecting'
    READY = 'ready'
    GOING_TO_DICCONNECT = 'going-to-disconnect'

    def __init__(self, symbol: str, api_key: str = None, api_secret: str = None):
        """
        websocket 初始化
        :param symbol:
        :param api_key:
        :param api_secret:
        """
        self.symbol = symbol
        if api_key is None and api_secret is None:
            self.api_key, self.api_secret = util.load_ot_from_config_file()
        else:
            self.api_key = api_key
            self.api_secret = api_secret
        self.account, self.exchange = util.get_name_exchange(symbol)
        self.host_ws = util.get_ws_host(self.exchange, self.account)
        self.is_running = False
        self.ws = None  # type: (websocket.WebSocketApp, None)
        self.ws_state = self.IDLE
        self.ws_support = True
        self.last_pong = 0
        self.sub_queue = {}

    def set_ws_state(self, new, reason=''):
        """
        设置 ws 状态
        :param new: ws 状态
        :param reason:
        :return: None
        """
        log.info('set ws state from %s to %s' % (self.ws_state, new), reason)
        self.ws_state = new

    def keep_connection(self):
        """
        发送心跳包，保持连接
        :return:
        """
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
                            self.send_json({'uri': 'ping', 'uuid': ping})
                            time.sleep(10)
                            if self.last_pong < ping:
                                log.warning('ws connection heartbeat lost')
                                break
                    except:
                        log.exception('ws connection ping failed')
                    finally:
                        if self.is_running:
                            self.set_ws_state(self.GOING_TO_CONNECT, 'heartbeat lost')
                elif self.ws_state == self.GOING_TO_DICCONNECT:
                    self.ws.close()
                time.sleep(1)

        thread.start_new_thread(run, ())

    @property
    def ws_path(self):
        """
        websocket 地址
        :return: wss://1token.trade/api/v1/ws/trade/exg_name/acc_name
        """
        return self.host_ws

    def ws_connect(self):
        """
        连接 websocket
        :return: None
        """
        self.set_ws_state(self.CONNECTING)
        nonce = util.gen_nonce()
        sign = util.gen_sign(self.api_secret, 'GET', '/ws/' + self.account, nonce, None)
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

    def send_message(self, message):
        """
        通过 websocket 发送消息
        :param message: string
        :return: None
        """
        self.ws.send(message)

    def send_json(self, js):
        """
        通过 websocket 发送json
        :param js: dict
        :return: None
        """
        self.ws.send(json.dumps(js))

    def on_message(self, message):
        """
        websocket 收到消息的回调
        :param message: json
        :return: None
        """
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
                        self.send_json({'uri': 'sub-{}'.format(key)})
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
                        for handler in self.sub_queue['order'].values():
                            try:
                                handler(order)
                            except:
                                log.exception('handle info error')
                else:
                    # todo 这里处理order 拿到 error 的情况
                    log.warning('order update error message', data)
            else:
                log.info('receive message %s' % data)
        except Exception as e:
            log.warning('unexpected msg format', message, e)

    def subscribe_info(self, handler, handler_name=None):
        """
        websocket 订阅 用户信息
        :param handler: func 接收到信息的回调函数
        :param handler_name: 回调方法名称
        :return: None
        """
        if not self.ws_support:
            log.warning('ws push not supported for this exchange {}'.format(self.exchange))
            return
        if 'info' not in self.sub_queue:
            self.sub_queue['info'] = {}
        if handler_name is None:
            handler_name = 'default'
        if handler_name in self.sub_queue['info']:
            log.warning('handler %s is already exist, will overwrite' % handler_name)
        self.sub_queue['info'][handler_name] = handler
        if self.ws_state == self.READY:
            self.send_json({'uri': 'sub-info'})
        elif self.ws_state == self.IDLE:
            self.set_ws_state(self.GOING_TO_CONNECT, 'user sub info')

    def subscribe_orders(self, handler, handler_name=None):
        """
        websocket 订阅 订单信息
        :param handler: func 接收到信息的回调函数
        :param handler_name: 回调方法名称
        :return: None
        """
        if not self.ws_support:
            log.warning('ws push not supported for this exchange {}'.format(self.exchange))
            return
        if 'order' not in self.sub_queue:
            self.sub_queue['order'] = {}
        if handler_name is None:
            handler_name = 'default'
        if handler_name in self.sub_queue['order']:
            log.warning('handler %s is already exist, will overwrite' % handler_name)
        self.sub_queue['order'][handler_name] = handler
        if self.ws_state == self.READY:
            self.send_json({'uri': 'sub-order'})
        elif self.ws_state == self.IDLE:
            self.set_ws_state(self.GOING_TO_CONNECT, 'user sub order')

    @staticmethod
    def on_error(ws, error):
        """
        websocket 发生错误的回调
        :param ws:
        :param error:
        :return: None
        """
        log.exception(error)

    @staticmethod
    def on_close(ws):
        """
        websocket 关闭的回调
        :param ws:
        :return: None
        """
        log.info("### websocket closed ###")

    def run(self) -> None:
        """
        运行 websocket
        :return: None
        """
        def _run():
            while self.is_running:
                if self.ws:
                    self.ws.on_open = self.keep_connection
                    self.ws.run_forever()
                else:
                    self.ws_connect()

        if self.is_running:
            log.warning('ws is already running')
        else:
            self.is_running = True
            thread.start_new_thread(_run, ())

    def close(self):
        """
        关闭 websocket
        :return: None
        """
        self.is_running = False
        self.ws.close()
        self.ws = None  # type: (websocket.WebSocketApp, None)
        self.ws_state = self.IDLE
        self.last_pong = 0
        self.sub_queue = {}
