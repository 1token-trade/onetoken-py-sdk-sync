import pytest
import logging

from onetoken import Account

logging.basicConfig(level=logging.INFO)
contract = 'binance/eos.usdt'
place_order_params = {'con': contract, 'price': 10, 'bs': 's', 'amount': 1}


@pytest.fixture(scope='session')
def acc():
    acc = Account(symbol='zb/otplay')
    return acc


def post_order_get_oid(acc):
    oid, err = acc.place_order(**place_order_params)
    logging.info(oid)
    assert not err
    assert oid['exchange_oid']
    return oid['exchange_oid']


# @pytest.mark.skip(reason=None)
def test_get_info(acc: Account):
    info, err = acc.get_info()
    logging.info(info)
    assert not err
    assert info.balance


# @pytest.mark.skip(reason=None)
def test_place_order(acc: Account):
    post_order_get_oid(acc)


# @pytest.mark.skip(reason=None)
def test_get_order_list(acc: Account):
    ol, err = acc.get_order_list(contract, 'end')
    logging.info(ol)
    assert not err
    assert type(ol) is list


# @pytest.mark.skip(reason=None)
def test_get_pending_list(acc: Account):
    oid = post_order_get_oid(acc)
    pl, err = acc.get_pending_list(contract)
    logging.info(pl)
    assert not err
    assert type(pl) is list
    assert oid in [i['exchange_oid'] for i in pl]


# @pytest.mark.skip(reason=None)
def test_cancel_use_exchange_oid(acc: Account):
    oid = post_order_get_oid(acc)
    res, err = acc.cancel_use_exchange_oid(oid)
    logging.info(res)
    assert not err
    assert res[0]['exchange_oid'] == oid
    pl, err = acc.get_pending_list(contract)
    assert not err
    assert oid not in [i['exchange_oid'] for i in pl]


# @pytest.mark.skip(reason=None)
def test_order_use_exchange_oid(acc: Account):
    oid = post_order_get_oid(acc)
    order, err = acc.get_order_use_exchange_oid(oid)
    logging.info(order)
    assert not err
    assert order[0]['exchange_oid'] == oid


# @pytest.mark.skip(reason=None)
def test_cancel_all(acc: Account):
    res, err = acc.cancel_all(contract)
    logging.info(res)
    assert not err
    assert res['status'] == 'success'
    pl, err = acc.get_pending_list(contract)
    assert not err
    assert type(pl) is list
    assert len(pl) == 0
