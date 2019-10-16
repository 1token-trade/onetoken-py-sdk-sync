import time

from onetoken_sync import AccountWs


def h(*args, **kwargs):
    """
    callback function
    :param args:
    :param kwargs:
    :return:
    """
    print(args, kwargs)


def sub_order():
    ws = AccountWs(symbol='binance/otplay')
    ws.setDaemon(True)
    ws.start()
    time.sleep(2)  # wait for websocket
    ws.subscribe_info(h)
    time.sleep(10)
    ws.close()
    time.sleep(5)


def send_message():
    ws = AccountWs(symbol='binance/otplay')
    ws.setDaemon(True)
    ws.start()
    time.sleep(2)  # wait for websocket
    ws.send_message("hello world")
    ws.send_json({'uri': 'ping', 'uuid': int(time.time())})
    time.sleep(5)


def main():
    sub_order()


if __name__ == '__main__':
    main()
