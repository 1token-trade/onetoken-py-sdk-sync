# onetoken-py-sdk-sync
Synchronized python SDK for https://1token.trade based on requests



[![CircleCI](https://circleci.com/gh/1token-trade/onetoken-py-sdk-sync/tree/master.svg?style=svg)](https://circleci.com/gh/1token-trade/onetoken-py-sdk-sync/tree/master)
[![Python 3.5](https://img.shields.io/badge/python-3.5-blue.svg)](https://www.python.org/downloads/release/python-350/)
[![Python 3.6](https://img.shields.io/badge/python-3.6-blue.svg)](https://www.python.org/downloads/release/python-360/)
[![Python 3.7](https://img.shields.io/badge/python-3.7-blue.svg)](https://www.python.org/downloads/release/python-370/)

## Install

pip install onetoken-sync


## Usage

```python
import onetoken_sync as ot
acc = ot.Account('binance/demo')
info = acc.get_info()
print(info)
```


