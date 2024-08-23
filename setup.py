from setuptools import setup, find_packages


setup(
    name='volcengine_kit',
    version='0.0.1',
    url='https://github.com/wjk376/volcengine-kit',
    author='Jiankun Wang',
    packages=find_packages(),
    install_requires=[
        'volcengine==1.0.148',
        'loguru==0.7.2',
        'pydantic>=2.8.0',
        'lark-oapi>=1.2.5',
    ],
    python_requires='>=3.8',
    platforms='any',
)