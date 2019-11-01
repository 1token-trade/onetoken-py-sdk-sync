import time

from onetoken_sync import Account, AccountWs


# you need to configure ot_key and ot_secret at ~/.onetoken/config.yml
# look like
# ot_key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# ot_secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

def get_account_with_key():
    acc = Account(symbol='binance/otplay', api_key='xxxxxxxxxxxxxxxxxx', api_secret='xxxxxxxxxxxxxxxxxxxxxx')
    return acc


def get_info():
    acc = Account(symbol='binance/otplay')
    print(acc.get_info())


def place_order():
    acc = Account(symbol='binance/otplay')
    print(acc.place_order(con='binance/eos.usdt', price=10, bs='s', amount=1))


def get_order():
    acc = Account(symbol='binance/otplay')
    print(acc.get_order_use_exchange_oid(oid='binance/eos.usdt-xxxxxxxxxxxxxxxx'))


def cancel_order():
    acc = Account(symbol='binance/otplay')
    print(acc.cancel_use_exchange_oid(oid='binance/eos.usdt-xxxxxxxxxxxxxxxx'))


def cancel_all():
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
