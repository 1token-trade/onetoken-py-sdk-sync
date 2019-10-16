import re
from codecs import open

from setuptools import setup, find_packages

with open('onetoken_sync/__init__.py', 'r', encoding='utf8') as fd:
    version = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]', fd.read(), re.MULTILINE).group(1)
    print('regex find version', version)
if not version:
    raise RuntimeError('Cannot find version information')

setup(name='onetoken_sync',
      author='OneToken',
      url='https://github.com/1token-trade/onetoken-py-sdk-sync',
      author_email='admin@1token.trade',
      packages=find_packages(),
      version=version,
      description='OneToken Trade System Python SDK',
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'Intended Audience :: Financial and Insurance Industry',
          'Intended Audience :: Information Technology',
          'Topic :: Software Development :: Build Tools',
          'Topic :: Office/Business :: Financial :: Investment',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Operating System :: OS Independent',
          'Environment :: Console'
      ],
      install_requires=[
          'arrow>=0.12',
          'PyYAML>=3',
          'requests',
      ],
      zip_safe=False,
      )
