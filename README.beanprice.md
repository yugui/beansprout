# Writing Source Maps in Ledger Files for bean-price

Source maps in Beancount ledger files allow you to specify which price sources should be used to fetch prices for specific commodities. This is done through the `price` metadata field in Commodity directives.

## Basic Syntax

The source map is defined in the `price` metadata field of a Commodity directive using the following syntax:

```beancount
YYYY-MM-DD commodity SYMBOL
  name: "Full name of the commodity"
  price: "QUOTE_CURRENCY:SOURCE/SYMBOL"
```

Where:
- `QUOTE_CURRENCY` is the currency you want the price quoted in (e.g., USD, EUR)
- `SOURCE` is the price source module (e.g., yahoo, coinbase)
- `SYMBOL` is the ticker symbol used by that source

## Examples

### Basic Example - Stock Price

```beancount
2020-01-01 commodity AAPL
  name: "Apple Inc."
  price: "USD:yahoo/AAPL"
```

This tells bean-price to fetch the price of AAPL in USD using the Yahoo Finance source.

### Multiple Quote Currencies

You can specify multiple quote currencies for the same commodity:

```beancount
2020-01-01 commodity AAPL
  name: "Apple Inc."
  price: "USD:yahoo/AAPL CAD:yahoo/AAPL.TO"
```

This fetches AAPL prices in both USD and CAD (using the Toronto exchange symbol for the CAD price).

### Multiple Sources (Fallbacks)

You can specify multiple sources for the same currency as fallbacks:

```beancount
2020-01-01 commodity BTC
  name: "Bitcoin"
  price: "USD:coinbase/BTC,coinmarketcap/BTC"
```

This will try to fetch BTC prices in USD from Coinbase first, and if that fails, it will try CoinMarketCap.

### Inverted Rates

For currency exchange rates, you might need to invert the rate. Use the `^` symbol before the ticker:

```beancount
2020-01-01 commodity CAD
  name: "Canadian Dollar"
  price: "USD:yahoo/^CADUSD=X"
```

This fetches the USD/CAD rate and inverts it to get the CAD/USD rate.

## Available Sources

The beanprice package includes several built-in sources:

- `yahoo` - Yahoo Finance (stocks, ETFs, mutual funds, currencies)
- `coinbase` - Coinbase (cryptocurrencies)
- `coinmarketcap` - CoinMarketCap (cryptocurrencies)
- `alphavantage` - Alpha Vantage (stocks, currencies)
- `oanda` - Oanda (currencies)
- And more...

## Using bean-price Command

Once you've defined source maps in your ledger file, you can use the `bean-price` command to fetch prices:

```bash
# Fetch latest prices for all active commodities
./bean_price.py your_ledger.beancount

# Fetch prices for a specific date
./bean_price.py --date 2023-01-15 your_ledger.beancount

# Fetch prices for all commodities, including inactive ones
./bean_price.py --inactive your_ledger.beancount

# Update prices from the last known price up to today
./bean_price.py --update your_ledger.beancount
```

## Advanced Features

### Custom Update Rate

When using `--update`, you can specify how often to fetch prices:

```bash
# Fetch prices for weekdays only (default)
./bean_price.py --update --update-rate weekday your_ledger.beancount

# Fetch prices daily (including weekends)
./bean_price.py --update --update-rate daily your_ledger.beancount

# Fetch prices weekly (Fridays only)
./bean_price.py --update --update-rate weekly your_ledger.beancount
```

### Handling Undeclared Commodities

For commodities without a Commodity directive, you can use a default source:

```bash
# Use Yahoo Finance as the default source for undeclared commodities
./bean_price.py --undeclared your_ledger.beancount
```

### Caching

bean-price caches results to avoid excessive API calls. You can control this behavior:

```bash
# Disable caching
./bean_price.py --no-cache your_ledger.beancount

# Clear the cache before fetching
./bean_price.py --clear-cache your_ledger.beancount
```

## Custom Price Sources

If you need to fetch prices from sources not included in beanprice, you can create custom price sources by:

1. Creating a Python module that implements the `Source` interface from `beanprice.source`
2. Placing it in a location where Python can import it
3. Referencing it in your source map using the full module path

For example, if you created a custom source in `mypricesources.myexchange`, you would reference it as:

```beancount
2020-01-01 commodity CUSTOM
  name: "Custom Asset"
  price: "USD:mypricesources.myexchange/CUSTOM"
```

The custom source must implement at least the `get_latest_price` and `get_historical_price` methods as defined in the `beanprice.source.Source` interface.
