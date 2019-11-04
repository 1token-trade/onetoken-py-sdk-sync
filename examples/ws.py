import time

from onetoken_sync import AccountWs


# 下面所有方法为示例方法，用户使用时需要替换交易所名称、交易所账号、订单信息

def h(*args, **kwargs):
    """
    callback function
    :param args:
    :param kwargs:
    :return:
    """
    print(args, kwargs)


def sub_info():
    """
    websocket 订阅 info 示例
    :return: None
    """
    ws = AccountWs(symbol='binance/otplay2')
    ws.run()
    time.sleep(2)  # wait for websocket
    ws.subscribe_info(h)
    time.sleep(10)
    ws.close()
    time.sleep(2)

    ws.run()  # websocket run again after close
    time.sleep(2)  # wait for websocket
    ws.subscribe_info(h)
    time.sleep(10)
    ws.close()
    time.sleep(5)


def send_message():
    """
    websocket 发生消息 示例
    :return: None
    """
    ws = AccountWs(symbol='binance/otplay')
    ws.run()
    time.sleep(2)  # wait for websocket
    ws.send_message("hello world")
    ws.send_json({'uri': 'ping', 'uuid': int(time.time())})
    time.sleep(5)


def main():
    sub_info()


if __name__ == '__main__':
    main()
