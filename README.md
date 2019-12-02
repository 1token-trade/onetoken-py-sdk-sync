# onetoken-py-sdk-sync
Synchronized python SDK for https://1token.trade based on requests



[![CircleCI](https://circleci.com/gh/1token-trade/onetoken-py-sdk-sync/tree/master.svg?style=svg)](https://circleci.com/gh/1token-trade/onetoken-py-sdk-sync/tree/master)
[![Python 3.5](https://img.shields.io/badge/python-3.5-blue.svg)](https://www.python.org/downloads/release/python-350/)
[![Python 3.6](https://img.shields.io/badge/python-3.6-blue.svg)](https://www.python.org/downloads/release/python-360/)
[![Python 3.7](https://img.shields.io/badge/python-3.7-blue.svg)](https://www.python.org/downloads/release/python-370/)

## Install

pip install onetoken-sync

## Config
在`~/.onetoken` 或者 `~/_onetoken` 目录下创建配置文件 `config.json`，配置文件内容如下：
(`~/`为用户根目录，例如：`C:\Users\用户名`)

### ~/.onetoken/config.json
```json
{
    "ot_key": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "ot_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

## Usage

```python
import onetoken_sync as ot
acc = ot.Account('binance/demo') # binance/demo 换成 自己申请的账号
info = acc.get_info()
print(info)
```


