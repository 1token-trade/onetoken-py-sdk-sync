from onetoken import Account


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


def h(*args, **kwargs):
    """
    callback function
    :param args:
    :param kwargs:
    :return:
    """
    print(args, kwargs)


def main():
    get_info()


if __name__ == '__main__':
    main()
