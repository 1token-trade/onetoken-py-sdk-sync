import json
import queue
import time
from collections import defaultdict

import arrow
from websocket import create_connection

try:
    import thread
except ImportError:
    import _thread as thread
import threading
from .config import Config
from .logger import log
from .model import Tick, Contract, Candle
from websocket._abnf import ABNF


class Quote:
    def __init__(self, key, ws_url, data_parser):
        self.key = key
        self.ws_url = ws_url
        self.data_parser = data_parser
        self.ws = None
        self.queue_handlers = defaultdict(list)
        self.data_queue = {}
        self.connected = False
        self.authorized = False
        self.lock = threading.Lock()  # fixme: asyncio.Lock()
        self.ensure_connection = True
        self.pong = 0
        # todo task_list
        # self.task_list = []
        # self.task_list.append(asyncio.ensure_future(self.ensure_connected()))
        # self.task_list.append(asyncio.ensure_future(self.heart_beat_loop()))

    def ensure_connected(self):
        log.debug('Connecting to {}'.format(self.ws_url))
        sleep_seconds = 2
        while self.ensure_connection:
            if not self.connected:
                try:
                    if self.ws and self.ws.sock:
                        self.ws.close()
                    self.ws = create_connection(self.ws_url, timeout=30)
                    self.ws.send(json.dumps({'uri': 'auth'}))
                except Exception as e:
                    try:
                        self.ws.close()
                    except:
                        log.exception('close websocket fail')
                    self.ws = None
                    log.warning(f'try connect to {self.ws_url} failed, sleep for {sleep_seconds} seconds...', e)
                    time.sleep(sleep_seconds)
                    sleep_seconds = min(sleep_seconds * 2, 64)
                else:
                    log.debug('Connected to WS')
                    self.connected = True
                    sleep_seconds = 2
                    self.pong = arrow.now().timestamp
                    self.on_msg()
                    wait_for_auth = 0
                    while not self.authorized and wait_for_auth < 5:
                        time.sleep(0.1)
                        wait_for_auth += 0.1
                    if wait_for_auth >= 5:
                        log.warning('wait for auth success timeout')
                        self.ws.close()
                    with self.lock:
                        q_keys = list(self.queue_handlers.keys())
                        if q_keys:
                            log.info('recover subscriptions', q_keys)
                            for q_key in q_keys:
                                sub_data = json.loads(q_key)
                                self.subscribe_data(**sub_data)
            else:
                time.sleep(1)

    def heart_beat_loop(self):
        while True:
            try:
                if self.ws and not self.ws.closed:
                    if arrow.now().timestamp - self.pong > 20:
                        log.warning('connection heart beat lost')
                        self.ws.close()
                    else:
                        self.ws.send(json.dumps({'uri': 'ping'}))
            finally:
                time.sleep(5)

    def on_msg(self):
        def run():
            while not self.ws.closed:  # todo: how to get closed
                msg_type, msg = self.ws.recv_data()
                try:
                    if msg_type == ABNF.OPCODE_BINARY or msg_type == ABNF.OPCODE_TEXT:
                        import gzip
                        if msg_type == ABNF.OPCODE_TEXT:
                            data = json.loads(msg)
                        else:
                            data = json.loads(gzip.decompress(msg).decode())
                        uri = data.get('uri', 'data')
                        if uri == 'pong':
                            self.pong = arrow.now().timestamp
                        elif uri == 'auth':
                            log.info(data)
                            self.authorized = True
                        elif uri == 'subscribe-single-tick-verbose':
                            log.info(data)
                        elif uri == 'subscribe-single-candle':
                            log.info(data)
                        else:
                            q_key, parsed_data = self.data_parser(data)
                            if q_key is None:
                                log.warning('unknown message', data)
                                continue
                            if q_key in self.data_queue:
                                self.data_queue[q_key].put_nowait(parsed_data)
                    elif msg_type == ABNF.OPCODE_CLOSE:
                        log.warning('closed', msg)
                        break
                    else:
                        log.warning('error', msg)
                        break
                except Exception as e:
                    log.warning('msg error...', e)
                time.sleep(0.1)
            try:
                self.ws.close()
            except:
                pass
            self.connected = False
            self.authorized = False
            log.warning('ws was disconnected...')

        thread.start_new_thread(run(), ())

    def subscribe_data(self, uri, on_update=None, **kwargs):
        log.info('subscribe', uri, **kwargs)
        while not self.connected or not self.authorized:
            time.sleep(0.1)
        sub_data = {'uri': uri}
        sub_data.update(kwargs)
        q_key = json.dumps(sub_data, sort_keys=True)
        if uri == 'subscribe-single-candle':
            sub_data['uri'] = 'single-candle'
            q_key = json.dumps(sub_data, sort_keys=True)
            sub_data['uri'] = 'subscribe-single-candle'

        with self.lock:
            try:
                self.ws.send(json.dumps(sub_data))
                log.info('sub data', sub_data)
                if q_key not in self.data_queue:
                    self.data_queue[q_key] = queue.Queue()
                    if on_update:
                        if not self.queue_handlers[q_key]:
                            self.handle_q(q_key)
            except Exception as e:
                log.warning('subscribe {} failed...'.format(kwargs), e)
            else:
                if on_update:
                    self.queue_handlers[q_key].append(on_update)

    async def handle_q(self, q_key):
        while q_key in self.data_queue:
            q = self.data_queue[q_key]
            try:
                tk = await q.get()
            except:
                log.warning('get data from queue failed')
                continue
            for callback in self.queue_handlers[q_key]:
                try:
                    callback(tk)
                except:
                    log.exception('quote callback fail')

    async def close(self):
        self.ensure_connection = False
        # todo: cancel task
        # for task in self.task_list:
        #     task.cancel()
        if self.ws:
            self.ws.close()
