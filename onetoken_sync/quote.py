import json
from collections import defaultdict
import time
import _thread as thread
import queue
import arrow
import websocket
from websocket import ABNF
from .config import Config
from .logger import log
from .model import Tick, Contract, Candle, Zhubi


class Quote:
    def __init__(self, key, ws_url, data_parser):
        self.key = key
        self.ws_url = ws_url
        self.data_parser = data_parser
        self.ws = None
        self.queue_handlers = defaultdict(list)
        self.data_queue = {}
        self.authorized = False
        self.lock = thread.allocate_lock()
        self.pong = 0
        self.is_running = False

    def ws_connect(self):
        log.debug('Connecting to {}'.format(self.ws_url))
        sleep_seconds = 2
        while True:
            try:
                if self.ws:
                    self.ws.close()
                self.ws = websocket.WebSocketApp(self.ws_url,
                                                 on_open=self.on_open,
                                                 on_data=self.on_data,
                                                 on_error=self.on_error,
                                                 on_close=self.on_close)
            except Exception as e:
                try:
                    self.ws.close()
                except:
                    log.exception('close session fail')
                self.ws = None
                log.warning(f'try connect to {self.ws_url} failed, sleep for {sleep_seconds} seconds...', e)
                time.sleep(sleep_seconds)
                sleep_seconds = min(sleep_seconds * 2, 64)
            else:
                break
        self.ws.run_forever()

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

    def heart_beat_loop(self):
        def run():
            while self.ws and self.ws.keep_running:
                try:
                    if time.time() - self.pong > 20:
                        log.warning('connection heart beat lost')
                        self.ws.close()
                        break
                    else:
                        self.send_json({'uri': 'ping'})
                finally:
                    time.sleep(5)

        thread.start_new_thread(run, ())

    def on_data(self, msg, msg_type, *args):
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
                elif uri == 'subscribe-single-zhubi-verbose':
                    log.info(data)
                elif uri == 'subscribe-single-candle':
                    log.info(data)
                else:
                    q_key, parsed_data = self.data_parser(data)
                    if q_key is None:
                        log.warning('unknown message', data)
                        return
                    if q_key in self.data_queue:
                        self.data_queue[q_key].put(parsed_data)
        except Exception as e:
            log.warning('msg error...', e)

    def on_open(self):
        def run():
            self.pong = time.time()
            self.heart_beat_loop()
            self.send_json({'uri': 'auth'})
            wait_for_auth = time.time()
            while not self.authorized and time.time() - wait_for_auth < 5:
                time.sleep(0.1)
            if not self.authorized:
                log.warning('wait for auth success timeout')
                self.ws.close()
            q_keys = list(self.queue_handlers.keys())
            if q_keys:
                log.info('recover subscriptions', q_keys)
                for q_key in q_keys:
                    sub_data = json.loads(q_key)
                    self.subscribe_data(**sub_data)
                    print(sub_data)

        thread.start_new_thread(run, ())

    @staticmethod
    def on_error(error):
        """
        websocket 发生错误的回调
        :param error:
        :return: None
        """
        log.exception(error)

    def on_close(self):
        """
        websocket 关闭的回调
        :return: None
        """
        self.authorized = False
        log.info("### websocket closed ###")

    def subscribe_data(self, uri, on_update=None, **kwargs):
        log.info('subscribe', uri, **kwargs)
        while not self.ws or not self.ws.keep_running or not self.authorized:
            time.sleep(1)
        sub_data = {'uri': uri}
        sub_data.update(kwargs)
        q_key = json.dumps(sub_data, sort_keys=True)
        with self.lock:
            try:
                self.send_json(sub_data)
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

    def handle_q(self, q_key):
        def run():
            while q_key in self.data_queue:
                q = self.data_queue[q_key]
                try:
                    tk = q.get()
                except:
                    log.warning('get data from queue failed')
                    continue
                for callback in self.queue_handlers[q_key]:
                    try:
                        callback(tk)
                    except:
                        log.exception('quote callback fail')

        thread.start_new_thread(run, ())

    def run(self) -> None:
        """
        运行 websocket
        :return: None
        """

        def _run():
            while self.is_running:
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
        self.pong = 0
        self.queue_handlers = defaultdict(list)
        self.data_queue = {}
        self.authorized = False


class TickQuote(Quote):
    def __init__(self, key):
        super().__init__(key, Config.TICK_HOST_WS, self.parse_tick)
        self.channel = 'subscribe-single-tick-verbose'

    def parse_tick(self, data):
        try:
            tick = Tick.from_dict(data['data'])
            q_key = json.dumps({'contract': tick.contract, 'uri': self.channel}, sort_keys=True)
            return q_key, tick
        except Exception as e:
            log.warning('parse error', e)
        return None, None

    def subscribe_tick(self, contract, on_update):
        self.subscribe_data(self.channel, on_update=on_update, contract=contract)


class TickV3Quote(Quote):
    def __init__(self):
        super().__init__('tick.v3', Config.TICK_V3_HOST_WS, self.parse_tick)
        self.channel = 'subscribe-single-tick-verbose'
        print(Config.TICK_V3_HOST_WS)
        self.ticks = {}

    def parse_tick(self, data):
        try:
            c = data['c']
            tm = arrow.get(data['tm'])
            et = arrow.get(data['et']) if 'et' in data else None
            tp = data['tp']
            q_key = json.dumps({'contract': c, 'uri': self.channel}, sort_keys=True)
            if len(data['b']) > 0 and len(data['a']) > 0:
                bid1, _ = data['b'][0]
                ask1, _ = data['a'][0]
                if bid1 >= ask1:
                    log.warning('bid1 >= ask1', bid1, ask1)
            if tp == 's':
                bids = [{'price': p, 'volume': v} for p, v in data['b']]
                asks = [{'price': p, 'volume': v} for p, v in data['a']]
                tick = Tick(tm, data['l'], data['v'], bids, asks, c, 'tick.v3', et, data['vc'])
                self.ticks[tick.contract] = tick
                return q_key, tick
            elif tp == 'd':
                if c not in self.ticks:
                    log.warning('update arriving before snapshot', self.channel, data)
                    return None, None
                tick = self.ticks[c].copy()

                tick.time = tm.datetime
                tick.exchange_time = et.datetime
                tick.price = data['l']
                tick.volume = data['v']
                tick.amount = data['vc']
                bids = {p: v for p, v in data['b']}
                old_bids = {item['price']: item['volume'] for item in tick.bids}
                old_bids.update(bids)
                bids = [{'price': p, 'volume': v} for p, v in old_bids.items() if v > 0]
                bids = sorted(bids, key=lambda x: x['price'], reverse=True)

                asks = {p: v for p, v in data['a']}
                old_asks = {item['price']: item['volume'] for item in tick.asks}
                old_asks.update(asks)
                asks = [{'price': p, 'volume': v} for p, v in old_asks.items() if v > 0]
                asks = sorted(asks, key=lambda x: x['price'])

                tick.bids = bids
                tick.asks = asks
                self.ticks[c] = tick
                return q_key, tick
        except Exception as e:
            log.warning('parse error', e, data)
        return None, None

    def subscribe_tick_v3(self, contract, on_update):
        self.subscribe_data(self.channel, on_update=on_update, contract=contract)


class CandleQuote(Quote):
    def __init__(self, key):
        super().__init__(key, Config.CANDLE_HOST_WS, self.parse_candle)
        self.channel = 'subscribe-single-candle'

    def parse_candle(self, data):
        try:
            if 'data' in data:
                data = data['data']
            candle = Candle.from_dict(data)
            q_key = json.dumps({'contract': candle.contract, 'duration': candle.duration, 'uri': self.channel},
                               sort_keys=True)
            return q_key, candle
        except Exception as e:
            log.warning('parse error', e)
        return None, None

    def subscribe_candle(self, contract, duration, on_update):
        self.subscribe_data(self.channel, on_update=on_update, contract=contract, duration=duration)


class ZhubiQuote(Quote):
    def __init__(self, key):
        super().__init__(key, Config.TICK_HOST_WS, self.parse_zhubi)
        self.channel = 'subscribe-single-zhubi-verbose'

    def parse_zhubi(self, data):
        try:
            zhubi = [Zhubi.from_dict(data) for data in data['data']]
            q_key = json.dumps({'contract': zhubi[0].contract, 'uri': self.channel}, sort_keys=True)
            return q_key, zhubi
        except Exception as e:
            log.warning('parse error', e)
        return None, None

    def subscribe_zhubi(self, contract, on_update):
        self.subscribe_data(self.channel, on_update=on_update, contract=contract)


_client_pool = {}


def get_client(key='defalut'):
    if key in _client_pool:
        return _client_pool[key]
    else:
        c = TickQuote(key)
        _client_pool[key] = c
        return c


def subscribe_tick(contract, on_update):
    c = get_client()
    c.run()
    return c.subscribe_tick(contract, on_update)


_tick_v3_client = None


def get_v3_client():
    global _tick_v3_client
    if _tick_v3_client is None:
        _tick_v3_client = TickV3Quote()
    return _tick_v3_client


def subscribe_tick_v3(contract, on_update):
    c = get_v3_client()
    c.run()
    return c.subscribe_tick_v3(contract, on_update)


_candle_client_pool = {}


def get_candle_client(key='defalut'):
    if key in _candle_client_pool:
        return _candle_client_pool[key]
    else:
        c = CandleQuote(key)
        _candle_client_pool[key] = c
        return c


def subscribe_candle(contract, duration, on_update):
    c = get_candle_client()
    c.run()
    return c.subscribe_candle(contract, duration, on_update)


_zhubi_quote_pool = {}


def get_zhubi_client(key='defalut'):
    if key in _zhubi_quote_pool:
        return _zhubi_quote_pool[key]
    else:
        c = ZhubiQuote(key)
        _zhubi_quote_pool[key] = c
        return c


def subscribe_zhubi(contract, on_update):
    c = get_zhubi_client()
    c.run()
    return c.subscribe_zhubi(contract, on_update)


def get_last_tick(contract):
    from . import util
    sess = util.get_requests_sess()
    res, err = util.http_go(sess.get, '%s/quote/single-tick/%s' % (Config.HOST_REST, contract))
    if not err:
        res = Tick.from_dict(res)
    return res, err


def get_contracts(exchange):
    from . import util
    sess = util.get_requests_sess()
    res, err = util.http_go(sess.get, '%s/basic/contracts?exchange=%s' % (Config.HOST_REST, exchange))
    if not err:
        cons = []
        for x in res:
            con = Contract.from_dict(x)
            cons.append(con)
        return cons, err
    return res, err


def get_contract(symbol):
    exchange, name = symbol.split('/')
    from . import util
    sess = util.get_requests_sess()
    res, err = util.http_go(sess.get, '%s/basic/contracts?exchange=%s&name=%s' % (Config.HOST_REST, exchange, name))
    if not err:
        if not res:
            return None, 'contract-not-exist'
        con = Contract.from_dict(res[0])
        return con, err
    return res, err
