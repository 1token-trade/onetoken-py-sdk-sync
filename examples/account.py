import time

from onetoken_sync import Account


# you need to configure ot_key and ot_secret at ~/onetoken/config.yml
# look like
# ot_key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# ot_secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 下面所有方法为示例方法，用户使用时需要替换交易所名称、交易所账号、订单信息

def get_account_with_key():
    """
    使用 api_key 和 api_secret 初始化 Account 示例
    :return:
    """
    acc = Account(symbol='binance/otplay', api_key='xxxxxxxxxxxxxxxxxx', api_secret='xxxxxxxxxxxxxxxxxxxxxx')
    return acc


def get_info():
    """
    查看用户信息 示例
    :return:
    """
    acc = Account(symbol='binance/otplay')
    print(acc.get_info())


def place_order():
    """
    下单 示例
    :return:
    """
    acc = Account(symbol='binance/otplay')
    print(acc.place_order(con='binance/eos.usdt', price=10, bs='s', amount=1))


def get_order():
    """
    查询订单 示例
    :return:
    """
    acc = Account(symbol='binance/otplay')
    print(acc.get_order_use_exchange_oid(oid='binance/eos.usdt-xxxxxxxxxxxxxxxx'))


def cancel_order():
    """
    撤单 示例
    :return:
    """
    acc = Account(symbol='binance/otplay')
    print(acc.cancel_use_exchange_oid(oid='binance/eos.usdt-xxxxxxxxxxxxxxxx'))


def cancel_all():
    """
    撤销全部订单 示例
    :return:
    """
    acc = Account(symbol='binance/otplay')
    print(acc.cancel_all())


def callback_order(*args, **kwargs):
    """
    callback function
    :param args:
    :param kwargs:
    :return:
    """
    print(args, kwargs)


def place_order_with_ws():
    """
    通过 websocket 订阅订单信息并下单 示例
    :return:
    """
    acc = Account(symbol='binance/otplay2')
    acc.ws_start()
    time.sleep(2)  # wait for websocket
    acc.ws_subscribe_orders(callback_order)

    print(acc.place_order(con='binance/eos.usdt', price=10, bs='s', amount=1))
    time.sleep(2)
    print(acc.cancel_all(contract='binance/eos.usdt'))
    time.sleep(10)
    acc.ws_close()
    time.sleep(3)


def main():
    place_order_with_ws()


if __name__ == '__main__':
    main()
