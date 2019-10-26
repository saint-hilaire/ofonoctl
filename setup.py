from setuptools import setup

setup(
    name='ofonoctl',
    version='0.1.1',
    packages=['ofonoctl'],
    url='https://git.sr.ht/~martijnbraam/ofonoctl',
    license='MIT',
    author='Martijn Braam',
    author_email='martijn@brixit.nl',
    description='test/control application for the ofono deamon',
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7'
    ],
    install_requires=[
        'tabulate'
    ],
    entry_points={
        'console_scripts': [
            'ofonoctl=ofonoctl.__init__:main'
        ]
    }
)
