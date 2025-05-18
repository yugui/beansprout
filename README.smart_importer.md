# Smart Importer Integration

This document describes the integration of the `smart_importer` package into Beansprout.

## Overview

The `smart_importer` package is a machine learning tool that predicts account names for Beancount transactions. It replaces the custom account predictor that was previously used in Beansprout.

## Features

- Automatically predicts account names for transactions based on existing entries
- Uses machine learning to improve predictions over time
- Configurable weights for different prediction factors
- Seamless integration with the `merge` command

## Usage

The smart importer is enabled by default. When you run the `bean-sprout merge` command, it will automatically use the smart importer to predict account names for transactions.

```bash
bean-sprout merge path/to/documents
```

### Training Data

The smart importer is trained on existing entries. By default, it will look for a file named `ledger.beancount` in the current directory. You can also specify a different file using the `--existing-file` option:

```bash
bean-sprout merge path/to/documents --existing-file path/to/ledger.beancount
```

### Configuration

You can configure the smart importer using environment variables:

- `BEANSPROUT_USE_SMART_IMPORTER`: Set to "0" to disable the smart importer (default: "1")
- `BEANSPROUT_SMART_IMPORTER_WEIGHTS`: A Python dictionary string that defines weights for different prediction factors (default: None)

Example:

```bash
# Disable smart importer
export BEANSPROUT_USE_SMART_IMPORTER=0

# Set custom weights
export BEANSPROUT_SMART_IMPORTER_WEIGHTS="{'narration': 0.8, 'payee': 1.5, 'date': 0.1}"
```

## How It Works

The smart importer uses the `PredictPostings` decorator from the `smart_importer` package to predict account names for transactions. It is applied to all importers during initialization.

When you run the `merge` command:

1. The smart importer loads existing entries from the specified file (or `ledger.beancount` by default)
2. It trains a machine learning model on these entries
3. When new transactions are extracted, it predicts account names based on the model
4. The predictions are applied to the transactions before they are written to files

## Comparison with the Previous Account Predictor

The smart importer offers several advantages over the previous custom account predictor:

- More sophisticated machine learning algorithms
- Better prediction accuracy
- Configurable weights for different prediction factors
- Maintained by the community, reducing the maintenance burden
- Seamless integration with the Beancount ecosystem

## Troubleshooting

If you encounter issues with the smart importer:

1. Try disabling it by setting `BEANSPROUT_USE_SMART_IMPORTER=0`
2. Check that your existing entries file is valid and contains enough data for training
3. Try adjusting the weights using the `BEANSPROUT_SMART_IMPORTER_WEIGHTS` environment variable

## References

- [smart_importer GitHub repository](https://github.com/beancount/smart_importer)
- [smart_importer documentation](https://smart-importer.readthedocs.io/)
