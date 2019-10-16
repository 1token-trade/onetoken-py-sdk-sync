import _thread as thread
import json
import queue
import threading
import time
from datetime import datetime

import websocket

from . import util
from .logger import log
from .model import Info


class AccountWs(threading.Thread):
    IDLE = 'idle'
    GOING_TO_CONNECT = 'going-to-connect'
    CONNECTING = 'connecting'
    READY = 'ready'
    GOING_TO_DICCONNECT = 'going-to-disconnect'

    def __init__(self, symbol: str, api_key: str = None, api_secret: str = None):
        super().__init__()
        self.symbol = symbol
        if api_key is None and api_secret is None:
            self.api_key, self.api_secret = util.load_ot_from_config_file()
        else:
            self.api_key = api_key
            self.api_secret = api_secret
        self.account, self.exchange = util.get_name_exchange(symbol)
        self.host_ws = util.get_ws_host(self.exchange, self.account)
        self.is_running = True
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
        return self.host_ws

    def ws_connect(self):
        self.set_ws_state(self.CONNECTING)
        nonce = util.gen_nonce()
        sign = util.gen_sign(self.api_secret, 'GET', f'/ws/{self.account}', nonce, None)
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
        self.ws.send(message)

    def send_json(self, js):
        self.ws.send(json.dumps(js))

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
            self.send_json({'uri': 'sub-info'})
        elif self.ws_state == self.IDLE:
            self.set_ws_state(self.GOING_TO_CONNECT, 'user sub info')

    def unsubscribe_info(self, handler_name=None):
        if handler_name is None:
            handler_name = 'default'
        if 'info' in self.sub_queue:
            del self.sub_queue['info'][handler_name]
            if len(self.sub_queue['info']) == 0 and self.ws_state == self.READY:
                self.send_json({'uri': 'unsub-info'})
                del self.sub_queue['info']
            if not self.sub_queue and self.ws_state != self.IDLE:
                self.set_ws_state(self.GOING_TO_DICCONNECT, 'subscribe nothing')

    def subscribe_orders(self, handler=None):
        if 'order' not in self.sub_queue:
            self.sub_queue['order'] = {}
        if handler is not None:
            self.sub_queue['order']['*'] = handler
        if self.ws_state == self.READY:
            self.send_json({'uri': 'sub-order'})
        elif self.ws_state == self.IDLE:
            self.set_ws_state(self.GOING_TO_CONNECT, 'user sub order')

    def unsubcribe_orders(self):
        if 'order' in self.sub_queue:
            del self.sub_queue['order']
        if self.ws_state == self.READY:
            self.send_json({'uri': 'unsub-order'})
        if not self.sub_queue and self.ws_state != self.IDLE:
            self.set_ws_state(self.GOING_TO_DICCONNECT, 'subscribe nothing')

    @staticmethod
    def on_error(ws, error):
        print(error)

    @staticmethod
    def on_close(ws):
        print("### websocket closed ###")

    def run(self) -> None:
        while self.is_running:
            if self.ws:
                self.ws.on_open = self.keep_connection
                self.ws.run_forever()
            else:
                self.ws_connect()

    def close(self):
        self.is_running = False
        self.set_ws_state(self.GOING_TO_DICCONNECT, 'close')
        self.ws.close()
