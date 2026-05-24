#!/usr/bin/env python3
"""Tests for the price completion plugin."""

import datetime
import unittest
from decimal import Decimal

import beancount
from beancount.core import data
from beansprout.plugins.price_completion import (
    PriceCalculationResult,
    TemporalPriceGraph,
    parse_config,
    price_completion,
)


class TestTemporalPriceGraph(unittest.TestCase):
    """Tests for the TemporalPriceGraph class."""

    def setUp(self):
        """Set up test fixtures."""
        self.graph = TemporalPriceGraph(temporal_base=1.0, temporal_scale=0.1)

    def test_add_price_entry(self):
        """Test adding price entries to the graph."""
        price_entry = data.Price(meta={},
                                 date=datetime.date(2023, 1, 1),
                                 currency="BTC",
                                 amount=beancount.Amount(
                                     Decimal("50000"), "USD"))

        self.graph.add_price_entry(price_entry)

        # Check that commodities were added
        self.assertIn("BTC", self.graph.commodities)
        self.assertIn("USD", self.graph.commodities)

        # Check that historical prices were recorded
        self.assertIn(("BTC", "USD"), self.graph.historical_prices)
        self.assertEqual(len(self.graph.historical_prices[("BTC", "USD")]), 1)

    def test_build_graph_for_date_current_day(self):
        """Test building graph for current day prices."""
        # Add a price entry
        price_entry = data.Price(meta={},
                                 date=datetime.date(2023, 1, 1),
                                 currency="BTC",
                                 amount=beancount.Amount(
                                     Decimal("50000"), "USD"))
        self.graph.add_price_entry(price_entry)

        # Build graph for the same date
        self.graph.build_graph_for_date(datetime.date(2023, 1, 1))

        # Check that edges were created with weight 1.0
        self.assertIn("BTC", self.graph.graph)
        self.assertIn("USD", self.graph.graph)

        # Check BTC -> USD edge
        btc_edges = self.graph.graph["BTC"]
        self.assertEqual(len(btc_edges), 1)
        target, weight, price_value, price_date, metadata = btc_edges[0]
        self.assertEqual(target, "USD")
        self.assertEqual(weight, 1.0)
        self.assertEqual(price_value, Decimal("50000"))

        # Check USD -> BTC edge (inverse)
        usd_edges = self.graph.graph["USD"]
        self.assertEqual(len(usd_edges), 1)
        target, weight, price_value, price_date, metadata = usd_edges[0]
        self.assertEqual(target, "BTC")
        self.assertEqual(weight, 1.0)
        self.assertEqual(price_value, Decimal("1") / Decimal("50000"))

    def test_build_graph_for_date_historical(self):
        """Test building graph using historical prices."""
        # Add a price entry from an earlier date
        price_entry = data.Price(meta={},
                                 date=datetime.date(2023, 1, 1),
                                 currency="BTC",
                                 amount=beancount.Amount(
                                     Decimal("50000"), "USD"))
        self.graph.add_price_entry(price_entry)

        # Build graph for a later date
        target_date = datetime.date(2023, 1, 5)
        self.graph.build_graph_for_date(target_date)

        # Check that edges were created with temporal penalty
        btc_edges = self.graph.graph["BTC"]
        self.assertEqual(len(btc_edges), 1)
        target, weight, price_value, price_date, metadata = btc_edges[0]
        self.assertEqual(target, "USD")
        self.assertGreater(weight, 1.0)  # Should have temporal penalty

        # Calculate expected weight: 1.0 + 0.1 * log(4)
        import math
        expected_weight = 1.0 + 0.1 * math.log(4)
        self.assertAlmostEqual(weight, expected_weight, places=6)

    def test_find_shortest_paths(self):
        """Test finding shortest paths using Dijkstra's algorithm."""
        # Create a simple graph: USD -> BTC -> ETH
        btc_price = data.Price(meta={},
                               date=datetime.date(2023, 1, 1),
                               currency="BTC",
                               amount=beancount.Amount(Decimal("50000"),
                                                       "USD"))
        eth_price = data.Price(meta={},
                               date=datetime.date(2023, 1, 1),
                               currency="ETH",
                               amount=beancount.Amount(Decimal("2"), "BTC"))

        self.graph.add_price_entry(btc_price)
        self.graph.add_price_entry(eth_price)
        self.graph.build_graph_for_date(datetime.date(2023, 1, 1))

        # Find shortest paths from USD
        paths = self.graph.find_shortest_paths("USD")

        # Should find paths to both BTC and ETH
        self.assertIn("BTC", paths)
        self.assertIn("ETH", paths)

        # Check BTC path (direct)
        btc_weight, btc_path = paths["BTC"]
        self.assertEqual(btc_weight, 1.0)
        self.assertEqual(btc_path, ["USD", "BTC"])

        # Check ETH path (indirect through BTC)
        eth_weight, eth_path = paths["ETH"]
        self.assertEqual(eth_weight, 2.0)  # Two hops
        self.assertEqual(eth_path, ["USD", "BTC", "ETH"])

    def test_calculate_derived_price(self):
        """Test calculating derived prices along paths."""
        # Create a simple graph: USD -> BTC -> ETH
        btc_price = data.Price(meta={},
                               date=datetime.date(2023, 1, 1),
                               currency="BTC",
                               amount=beancount.Amount(Decimal("50000"),
                                                       "USD"))
        eth_price = data.Price(meta={},
                               date=datetime.date(2023, 1, 1),
                               currency="ETH",
                               amount=beancount.Amount(Decimal("2"), "BTC"))

        self.graph.add_price_entry(btc_price)
        self.graph.add_price_entry(eth_price)
        self.graph.build_graph_for_date(datetime.date(2023, 1, 1))

        # Calculate derived price for USD -> BTC -> ETH
        path = ["USD", "BTC", "ETH"]
        price_result = self.graph.calculate_derived_price(
            path, datetime.date(2023, 1, 1))

        # Expected: (1/50000) * (1/2) = 1/100000 = 0.00001
        expected_price = Decimal("1") / Decimal("100000")
        self.assertIsNotNone(price_result)
        self.assertEqual(price_result.price, expected_price)
        self.assertIsInstance(price_result.closest_metadata, dict)
        self.assertTrue(price_result.has_current_date_edge)

    def test_metadata_propagation(self):
        """Test that metadata is correctly propagated from closest edge."""
        # Create prices with metadata
        btc_price = data.Price(meta={
            "filename": "test.beancount",
            "lineno": 10
        },
                               date=datetime.date(2023, 1, 1),
                               currency="BTC",
                               amount=beancount.Amount(Decimal("50000"),
                                                       "USD"))
        eth_price = data.Price(meta={
            "filename": "test.beancount",
            "lineno": 20
        },
                               date=datetime.date(2023, 1, 1),
                               currency="ETH",
                               amount=beancount.Amount(Decimal("2"), "BTC"))

        self.graph.add_price_entry(btc_price)
        self.graph.add_price_entry(eth_price)
        self.graph.build_graph_for_date(datetime.date(2023, 1, 1))

        # Calculate derived price for USD -> BTC -> ETH
        path = ["USD", "BTC", "ETH"]
        price_result = self.graph.calculate_derived_price(
            path, datetime.date(2023, 1, 1))

        # Should have metadata from ETH price (closest edge)
        self.assertIsNotNone(price_result)
        self.assertEqual(price_result.closest_metadata.get("filename"),
                         "test.beancount")
        self.assertEqual(price_result.closest_metadata.get("lineno"), 20)
        self.assertTrue(price_result.has_current_date_edge)


class TestParseConfig(unittest.TestCase):
    """Tests for the parse_config function."""

    def test_empty_config(self):
        """Test parsing empty configuration."""
        config = parse_config("")
        self.assertEqual(config["temporal_base"], 1.0)
        self.assertEqual(config["temporal_scale"], 0.1)

    def test_valid_config(self):
        """Test parsing valid configuration."""
        config = parse_config("temporal_base=2.0,temporal_scale=0.2")
        self.assertEqual(config["temporal_base"], 2.0)
        self.assertEqual(config["temporal_scale"], 0.2)

    def test_partial_config(self):
        """Test parsing partial configuration."""
        config = parse_config("temporal_base=3.0")
        self.assertEqual(config["temporal_base"], 3.0)
        self.assertEqual(config["temporal_scale"], 0.1)  # Default

    def test_invalid_config(self):
        """Test parsing invalid configuration."""
        config = parse_config("temporal_base=invalid,temporal_scale=0.3")
        self.assertEqual(config["temporal_base"], 1.0)  # Default
        self.assertEqual(config["temporal_scale"], 0.3)


class TestPriceCompletion(unittest.TestCase):
    """Tests for the price completion plugin."""

    def test_basic_price_completion(self):
        """Test basic price completion functionality."""
        # Create test entries
        entries = [
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("50000"), "USD")),
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="ETH",
                       amount=beancount.Amount(Decimal("2"), "BTC")),
        ]

        # Set up options with operating currencies
        options_map = {"operating_currency": ["USD", "JPY"]}

        # Run price completion
        new_entries, errors = price_completion(entries, options_map, "")

        # Check that new price entries were created
        self.assertEqual(len(errors), 0)
        self.assertGreater(len(new_entries), len(entries))

        # Find the derived ETH/USD price
        derived_prices = [
            e for e in new_entries
            if isinstance(e, data.Price) and e not in entries
        ]

        # Should have created ETH/USD price
        eth_usd_prices = [
            p for p in derived_prices
            if p.currency == "ETH" and p.amount.currency == "USD"
        ]
        self.assertEqual(len(eth_usd_prices), 1)

        # Check the derived price value
        eth_usd_price = eth_usd_prices[0]
        # Expected: (1/50000) * 2 = 0.00004 ETH per USD, so 1/0.00004 = 25000 USD per ETH
        # Wait, let me recalculate: ETH costs 2 BTC, BTC costs 50000 USD, so ETH costs 100000 USD
        # Actually, the price entry format is: currency "ETH" amount "X USD"
        # So we want ETH in USD: 2 BTC * 50000 USD/BTC = 100000 USD
        expected_price = Decimal("2") * Decimal("50000")
        self.assertEqual(eth_usd_price.amount.number, expected_price)

    def test_no_operating_currencies(self):
        """Test behavior when no operating currencies are specified."""
        entries = [
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("50000"), "USD")),
        ]

        options_map = {}

        # Run price completion
        new_entries, errors = price_completion(entries, options_map, "")

        # Should not create any new entries
        self.assertEqual(len(new_entries), len(entries))
        self.assertEqual(len(errors), 0)

    def test_existing_prices_not_duplicated(self):
        """Test that existing prices are not duplicated."""
        entries = [
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("50000"), "USD")),
            # This price already exists, should not be duplicated
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("50000"), "USD")),
        ]

        options_map = {"operating_currency": ["USD"]}

        # Run price completion
        new_entries, errors = price_completion(entries, options_map, "")

        # Should not create duplicate BTC/USD prices
        btc_usd_prices = [
            e for e in new_entries if isinstance(e, data.Price)
            and e.currency == "BTC" and e.amount.currency == "USD"
        ]
        self.assertEqual(len(btc_usd_prices), 2)  # Only the original entries


class TestTemporalPriceCompletion(unittest.TestCase):
    """Tests for temporal price completion scenarios."""

    def test_temporal_weight_calculation(self):
        """Test that temporal weights are calculated correctly for historical prices."""
        graph = TemporalPriceGraph(temporal_base=1.0, temporal_scale=0.1)

        # Add a historical price
        price_entry = data.Price(meta={},
                                 date=datetime.date(2023, 1, 1),
                                 currency="BTC",
                                 amount=beancount.Amount(
                                     Decimal("50000"), "USD"))
        graph.add_price_entry(price_entry)

        # Build graph for 5 days later
        target_date = datetime.date(2023, 1, 6)
        graph.build_graph_for_date(target_date)

        # Check that temporal weight was applied
        btc_edges = graph.graph["BTC"]
        self.assertEqual(len(btc_edges), 1)
        target, weight, price_value, price_date, metadata = btc_edges[0]
        self.assertEqual(target, "USD")

        # Expected weight: 1.0 + 0.1 * log(5)
        import math
        expected_weight = 1.0 + 0.1 * math.log(5)
        self.assertAlmostEqual(weight, expected_weight, places=6)

    def test_historical_price_reuse_with_fresh_edge(self):
        """Test that historical prices are reused when mixed with fresh edges."""
        entries = [
            # Day 1: ETH->BTC price (historical)
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="ETH",
                       amount=beancount.Amount(Decimal("2"), "BTC")),
            # Day 3: BTC->USD price (fresh)
            data.Price(meta={},
                       date=datetime.date(2023, 1, 3),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("51000"), "USD")),
        ]

        options_map = {"operating_currency": ["USD"]}

        # Run price completion
        new_entries, errors = price_completion(entries, options_map, "")

        # Should complete ETH/USD price for day 3 using historical ETH->BTC and fresh BTC->USD
        self.assertEqual(len(errors), 0)

        # Find ETH/USD prices for day 3
        day3_eth_prices = [
            e for e in new_entries if isinstance(e, data.Price)
            and e.date == datetime.date(2023, 1, 3) and e.currency == "ETH"
            and e.amount.currency == "USD" and e not in entries
        ]

        # Should have generated one because path has fresh BTC->USD edge
        self.assertEqual(len(day3_eth_prices), 1)

        # Price should be 2 * 51000 = 102000 (using historical ETH rate with fresh BTC rate)
        self.assertEqual(day3_eth_prices[0].amount.number, Decimal("102000"))

    def test_multiple_operating_currencies(self):
        """Test price completion with multiple operating currencies."""
        entries = [
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("50000"), "USD")),
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="USD",
                       amount=beancount.Amount(Decimal("130"), "JPY")),
        ]

        options_map = {"operating_currency": ["USD", "JPY", "EUR"]}

        # Run price completion
        new_entries, errors = price_completion(entries, options_map, "")

        self.assertEqual(len(errors), 0)

        # Should have created BTC/JPY price
        btc_jpy_prices = [
            e for e in new_entries
            if isinstance(e, data.Price) and e.currency == "BTC"
            and e.amount.currency == "JPY" and e not in entries
        ]
        self.assertEqual(len(btc_jpy_prices), 1)

        # BTC price in JPY should be 50000 * 130 = 6,500,000
        expected_btc_jpy = Decimal("50000") * Decimal("130")
        self.assertAlmostEqual(float(btc_jpy_prices[0].amount.number),
                               float(expected_btc_jpy),
                               places=10)

        # Should have created JPY/USD price (inverse)
        jpy_usd_prices = [
            e for e in new_entries
            if isinstance(e, data.Price) and e.currency == "JPY"
            and e.amount.currency == "USD" and e not in entries
        ]
        self.assertEqual(len(jpy_usd_prices), 1)

        # JPY price in USD should be 1/130
        expected_jpy_usd = Decimal("1") / Decimal("130")
        self.assertEqual(jpy_usd_prices[0].amount.number, expected_jpy_usd)

    def test_unreachable_commodities(self):
        """Test behavior with unreachable commodities."""
        entries = [
            # USD-BTC connection
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("50000"), "USD")),
            # Isolated EUR-GBP connection (no path to USD)
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="EUR",
                       amount=beancount.Amount(Decimal("0.9"), "GBP")),
        ]

        options_map = {"operating_currency": ["USD"]}

        # Run price completion
        new_entries, errors = price_completion(entries, options_map, "")

        self.assertEqual(len(errors), 0)

        # Should not create EUR/USD or GBP/USD prices (unreachable)
        derived_prices = [
            e for e in new_entries
            if isinstance(e, data.Price) and e not in entries
        ]
        eur_usd_prices = [
            p for p in derived_prices
            if p.currency == "EUR" and p.amount.currency == "USD"
        ]
        gbp_usd_prices = [
            p for p in derived_prices
            if p.currency == "GBP" and p.amount.currency == "USD"
        ]

        self.assertEqual(len(eur_usd_prices), 0)
        self.assertEqual(len(gbp_usd_prices), 0)

    def test_configurable_temporal_parameters(self):
        """Test that temporal parameters can be configured for weight calculation."""
        graph = TemporalPriceGraph(temporal_base=2.0, temporal_scale=0.5)

        # Add a historical price
        price_entry = data.Price(meta={},
                                 date=datetime.date(2023, 1, 1),
                                 currency="BTC",
                                 amount=beancount.Amount(
                                     Decimal("50000"), "USD"))
        graph.add_price_entry(price_entry)

        # Build graph for 10 days later
        target_date = datetime.date(2023, 1, 11)
        graph.build_graph_for_date(target_date)

        # Check that custom temporal parameters were applied
        btc_edges = graph.graph["BTC"]
        self.assertEqual(len(btc_edges), 1)
        target, weight, price_value, price_date, metadata = btc_edges[0]
        self.assertEqual(target, "USD")

        # Expected weight with custom parameters: 2.0 + 0.5 * log(10)
        import math
        expected_weight = 2.0 + 0.5 * math.log(10)
        self.assertAlmostEqual(weight, expected_weight, places=6)

        # Verify the temporal parameters are stored correctly
        self.assertEqual(graph.temporal_base, 2.0)
        self.assertEqual(graph.temporal_scale, 0.5)

    def test_circular_references_handled(self):
        """Test that circular price references don't cause infinite loops."""
        entries = [
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="A",
                       amount=beancount.Amount(Decimal("2"), "B")),
            data.Price(meta={},
                       date=datetime.date(2023, 1, 1),
                       currency="B",
                       amount=beancount.Amount(Decimal("3"), "C")),
            data.Price(
                meta={},
                date=datetime.date(2023, 1, 1),
                currency="C",
                amount=beancount.Amount(Decimal("0.5"), "A")  # Creates cycle
            ),
        ]

        options_map = {"operating_currency": ["A"]}

        # Should not crash due to circular references
        new_entries, errors = price_completion(entries, options_map, "")

        # Should complete successfully
        self.assertEqual(len(errors), 0)
        self.assertGreaterEqual(len(new_entries), len(entries))


class TestMetadataPropagation(unittest.TestCase):
    """Tests for metadata propagation in price completion."""

    def test_generated_prices_have_metadata(self):
        """Test that generated prices include metadata from source entries."""
        entries = [
            data.Price(meta={
                "filename": "btc.beancount",
                "lineno": 100
            },
                       date=datetime.date(2023, 1, 1),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("50000"), "USD")),
            data.Price(meta={
                "filename": "eth.beancount",
                "lineno": 200
            },
                       date=datetime.date(2023, 1, 1),
                       currency="ETH",
                       amount=beancount.Amount(Decimal("2"), "BTC")),
        ]

        options_map = {"operating_currency": ["USD"]}

        # Run price completion
        new_entries, errors = price_completion(entries, options_map, "")

        self.assertEqual(len(errors), 0)

        # Find the generated ETH/USD price
        eth_usd_prices = [
            e for e in new_entries
            if isinstance(e, data.Price) and e.currency == "ETH"
            and e.amount.currency == "USD" and e not in entries
        ]
        self.assertEqual(len(eth_usd_prices), 1)

        # Check that it has metadata from the closest edge (ETH price)
        eth_price = eth_usd_prices[0]
        self.assertEqual(eth_price.meta.get("filename"), "eth.beancount")
        self.assertEqual(eth_price.meta.get("lineno"), 200)

    def test_direct_path_metadata(self):
        """Test metadata for direct path (single hop) completion."""
        entries = [
            data.Price(meta={
                "filename": "rates.beancount",
                "lineno": 42
            },
                       date=datetime.date(2023, 1, 1),
                       currency="USD",
                       amount=beancount.Amount(Decimal("130"), "JPY")),
        ]

        options_map = {"operating_currency": ["USD", "JPY"]}

        # Run price completion
        new_entries, errors = price_completion(entries, options_map, "")

        self.assertEqual(len(errors), 0)

        # Find the generated JPY/USD price (inverse)
        jpy_usd_prices = [
            e for e in new_entries
            if isinstance(e, data.Price) and e.currency == "JPY"
            and e.amount.currency == "USD" and e not in entries
        ]
        self.assertEqual(len(jpy_usd_prices), 1)

        # Check that it has metadata from the source USD/JPY price
        jpy_price = jpy_usd_prices[0]
        self.assertEqual(jpy_price.meta.get("filename"), "rates.beancount")
        self.assertEqual(jpy_price.meta.get("lineno"), 42)


class TestDateValidation(unittest.TestCase):
    """Tests for date validation in price completion."""

    def test_all_historical_edges_no_completion(self):
        """Test that no completion occurs when all edges are historical."""
        entries = [
            # Day 1: BTC and ETH prices
            data.Price(meta={
                "filename": "old.beancount",
                "lineno": 10
            },
                       date=datetime.date(2023, 1, 1),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("50000"), "USD")),
            data.Price(meta={
                "filename": "old.beancount",
                "lineno": 20
            },
                       date=datetime.date(2023, 1, 1),
                       currency="ETH",
                       amount=beancount.Amount(Decimal("2"), "BTC")),
            # Day 5: Only unrelated price (no BTC or ETH prices on this day)
            data.Price(meta={
                "filename": "new.beancount",
                "lineno": 30
            },
                       date=datetime.date(2023, 1, 5),
                       currency="USDT",
                       amount=beancount.Amount(Decimal("1.00"), "USD")),
        ]

        options_map = {"operating_currency": ["USD"]}

        # Run price completion for day 5
        new_entries, errors = price_completion(entries, options_map, "")

        self.assertEqual(len(errors), 0)

        # Should NOT generate ETH/USD price for day 5 because all path edges are from day 1
        day5_eth_prices = [
            e for e in new_entries if isinstance(e, data.Price)
            and e.date == datetime.date(2023, 1, 5) and e.currency == "ETH"
            and e.amount.currency == "USD" and e not in entries
        ]
        self.assertEqual(len(day5_eth_prices), 0)

        # Should NOT generate BTC/USD price for day 5 either
        day5_btc_prices = [
            e for e in new_entries if isinstance(e, data.Price)
            and e.date == datetime.date(2023, 1, 5) and e.currency == "BTC"
            and e.amount.currency == "USD" and e not in entries
        ]
        self.assertEqual(len(day5_btc_prices), 0)

    def test_mixed_fresh_historical_edges_completion(self):
        """Test that completion occurs when path has both fresh and historical edges."""
        entries = [
            # Day 1: ETH price (historical)
            data.Price(meta={
                "filename": "old.beancount",
                "lineno": 10
            },
                       date=datetime.date(2023, 1, 1),
                       currency="ETH",
                       amount=beancount.Amount(Decimal("2"), "BTC")),
            # Day 3: BTC price (fresh for day 3)
            data.Price(meta={
                "filename": "new.beancount",
                "lineno": 20
            },
                       date=datetime.date(2023, 1, 3),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("51000"), "USD")),
        ]

        options_map = {"operating_currency": ["USD"]}

        # Run price completion for day 3
        new_entries, errors = price_completion(entries, options_map, "")

        self.assertEqual(len(errors), 0)

        # SHOULD generate ETH/USD price for day 3 because path ETH->BTC->USD has fresh BTC edge
        day3_eth_prices = [
            e for e in new_entries if isinstance(e, data.Price)
            and e.date == datetime.date(2023, 1, 3) and e.currency == "ETH"
            and e.amount.currency == "USD" and e not in entries
        ]
        self.assertEqual(len(day3_eth_prices), 1)

        # Price should be 2 * 51000 = 102000
        expected_eth_usd = Decimal("2") * Decimal("51000")
        self.assertEqual(day3_eth_prices[0].amount.number, expected_eth_usd)

    def test_all_fresh_edges_completion(self):
        """Test that completion occurs when all edges are fresh."""
        entries = [
            # Day 3: Both BTC and ETH prices (all fresh)
            data.Price(meta={
                "filename": "fresh.beancount",
                "lineno": 10
            },
                       date=datetime.date(2023, 1, 3),
                       currency="BTC",
                       amount=beancount.Amount(Decimal("51000"), "USD")),
            data.Price(meta={
                "filename": "fresh.beancount",
                "lineno": 20
            },
                       date=datetime.date(2023, 1, 3),
                       currency="ETH",
                       amount=beancount.Amount(Decimal("2"), "BTC")),
        ]

        options_map = {"operating_currency": ["USD"]}

        # Run price completion for day 3
        new_entries, errors = price_completion(entries, options_map, "")

        self.assertEqual(len(errors), 0)

        # SHOULD generate ETH/USD price because all edges are fresh
        day3_eth_prices = [
            e for e in new_entries if isinstance(e, data.Price)
            and e.date == datetime.date(2023, 1, 3) and e.currency == "ETH"
            and e.amount.currency == "USD" and e not in entries
        ]
        self.assertEqual(len(day3_eth_prices), 1)

        # Price should be 2 * 51000 = 102000
        expected_eth_usd = Decimal("2") * Decimal("51000")
        self.assertEqual(day3_eth_prices[0].amount.number, expected_eth_usd)

    def test_single_fresh_edge_completion(self):
        """Test that completion occurs with just one fresh edge in direct path."""
        entries = [
            # Day 3: Only USD->JPY rate (fresh, direct path)
            data.Price(meta={
                "filename": "rates.beancount",
                "lineno": 10
            },
                       date=datetime.date(2023, 1, 3),
                       currency="USD",
                       amount=beancount.Amount(Decimal("130"), "JPY")),
        ]

        options_map = {"operating_currency": ["USD", "JPY"]}

        # Run price completion for day 3
        new_entries, errors = price_completion(entries, options_map, "")

        self.assertEqual(len(errors), 0)

        # SHOULD generate JPY/USD price because it's a direct fresh edge
        day3_jpy_prices = [
            e for e in new_entries if isinstance(e, data.Price)
            and e.date == datetime.date(2023, 1, 3) and e.currency == "JPY"
            and e.amount.currency == "USD" and e not in entries
        ]
        self.assertEqual(len(day3_jpy_prices), 1)

        # Price should be 1/130
        expected_jpy_usd = Decimal("1") / Decimal("130")
        self.assertEqual(day3_jpy_prices[0].amount.number, expected_jpy_usd)

    def test_has_current_date_edge_flag(self):
        """Test the has_current_date_edge flag directly."""
        graph = TemporalPriceGraph()

        # Add historical price
        historical_price = data.Price(meta={
            "filename": "old.beancount",
            "lineno": 10
        },
                                      date=datetime.date(2023, 1, 1),
                                      currency="BTC",
                                      amount=beancount.Amount(
                                          Decimal("50000"), "USD"))
        graph.add_price_entry(historical_price)

        # Add current price
        current_price = data.Price(meta={
            "filename": "new.beancount",
            "lineno": 20
        },
                                   date=datetime.date(2023, 1, 5),
                                   currency="ETH",
                                   amount=beancount.Amount(
                                       Decimal("1600"), "USD"))
        graph.add_price_entry(current_price)

        # Build graph for day 5
        graph.build_graph_for_date(datetime.date(2023, 1, 5))

        # Test path with current edge: USD -> ETH (current)
        current_path = ["USD", "ETH"]
        current_result = graph.calculate_derived_price(
            current_path, datetime.date(2023, 1, 5))
        self.assertIsNotNone(current_result)
        self.assertTrue(current_result.has_current_date_edge)

        # Test path with historical edge: USD -> BTC (historical)
        historical_path = ["USD", "BTC"]
        historical_result = graph.calculate_derived_price(
            historical_path, datetime.date(2023, 1, 5))
        self.assertIsNotNone(historical_result)
        self.assertFalse(historical_result.has_current_date_edge)


if __name__ == "__main__":
    unittest.main()
