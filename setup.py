#!/usr/bin/env python
from setuptools import find_packages, setup

from taxi_petzi import __version__

with open("README.md") as f:
    readme = f.read()

install_requires = [
    "google-api-python-client",
    "google-auth-httplib2",
    "google-auth-oauthlib",
    "taxi>=6.1.0",
]

setup(
    name="taxi_petzi",
    version=__version__,
    packages=find_packages(),
    description="Taxi backend for Petzi",
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Sylvain Fankhauser",
    author_email="sephi@fhtagn.top",
    url="https://github.com/sephii/taxi-petzi",
    install_requires=install_requires,
    license="wtfpl",
    python_requires=">=3.7",
    entry_points={
        "taxi.backends": "petzi = taxi_petzi.backend:PetziBackend",
    },
    classifiers=[
        "Programming Language :: Python :: 3.7",
    ],
)
