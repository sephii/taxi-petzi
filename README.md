# Petzi backend for Taxi

This is the Petzi backend for [Taxi](https://github.com/sephii/taxi). It
exposes the `petzi` protocol to push entries to a Google spreadsheet.

## Installation

``` sh
taxi plugin install petzi
```

## Usage

First you’ll need to generate a credentials file to be able to query the
spreadsheets Google API. To do so, [follow the official
guide](https://developers.google.com/workspace/guides/create-credentials), and
then follow the "Create Desktop application credentials" and download the JSON
file with credentials.

Once you have your JSON file with credentials, open your configuration file
using `taxi config`, and add a backend using the `petzi` protocol for your
backend. Use the path to the credentials JSON file and set the `sheet_id` in the
query string.  For example:

```
[backends]
petzi = petzi:///home/sephi/credentials.json?sheet_id=22324_Xg40_x9iWrERPCeIhBFcfHuTWbzxtjrfwvZIQA
```

## Contributing

To setup a development environment, create a virtual environment and run the
following command in it:

``` sh
pip install -e .
```

To use a specific version of Taxi, eg. if you need to also make changes to Taxi,
install it in the virtual environment in editable mode:

``` sh
pip install -e /path/to/taxi
```

To run the tests, install the test requirements, and then run the `pytest` command:

``` sh
pip install -r requirements_test.txt
pytest
```
