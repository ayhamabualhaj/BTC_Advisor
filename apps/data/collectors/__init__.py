"""One module per data source. Each fetches raw data and returns a list of Points.

Dating rule (protects backtests from look-ahead): a Point's date is the last UTC day by
whose end the value was known. A decision for day D uses only Points dated D or earlier.
"""
