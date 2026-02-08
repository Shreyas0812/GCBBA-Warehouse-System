# setup.py
from setuptools import setup, find_packages

setup(
    name="gcbba_warehouse_system",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        'numpy',
        'pyyaml',
        'matplotlib',
        'networkx',
    ],
)