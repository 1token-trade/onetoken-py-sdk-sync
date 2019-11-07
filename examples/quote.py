import time

from onetoken_sync import get_v3_client


def callback_order(*args, **kwargs):
    """
    callback function
    :param args:
    :param kwargs:
    :return:
    """
    print(args, kwargs)


def main():
    tick_v3 = get_v3_client()
    tick_v3.run()
    tick_v3.subscribe_tick_v3(on_update=callback_order, contract="huobip/btc.usdt")
    time.sleep(60)
    tick_v3.close()


if __name__ == '__main__':
    main()
