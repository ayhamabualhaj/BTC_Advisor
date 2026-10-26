import datetime
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.data.collectors import binance, bybit, etf_flows, fred, okx_liquidations, yahoo
from apps.data.collectors.base import CollectorError, Point, date_known_by, to_ms
from apps.data.models import MarketData
from apps.data.repositories import market_data_repository
from apps.data.services import collection_service

D = datetime.date


def ms(day, hour=0):
    return to_ms(day) + hour * 3_600_000


class DatingTests(SimpleTestCase):
    def test_value_stamped_at_midnight_belongs_to_previous_day(self):
        self.assertEqual(date_known_by(ms(D(2026, 7, 2))), D(2026, 7, 1))

    def test_value_stamped_during_the_day_belongs_to_that_day(self):
        self.assertEqual(date_known_by(ms(D(2026, 7, 2), 8)), D(2026, 7, 2))


class BinanceTests(SimpleTestCase):
    def test_candle_is_dated_by_its_open_day(self):
        candle = [ms(D(2025, 1, 1)), "1", "3", "0.5", "2", "100", 0]
        points = binance.parse_candles([candle])
        self.assertIn(Point(D(2025, 1, 1), "close", 2.0), points)
        self.assertEqual(len(points), 5)

    def test_todays_unfinished_candle_is_skipped(self):
        today = datetime.datetime.now(datetime.UTC).date()
        self.assertEqual(binance.parse_candles([[ms(today), "1", "1", "1", "1", "1"]]), [])


class BybitTests(SimpleTestCase):
    def funding(self, day, hour, rate):
        return {"fundingRate": str(rate), "fundingRateTimestamp": str(ms(day, hour))}

    def test_three_settlements_average_into_one_day(self):
        day, next_day = D(2025, 1, 1), D(2025, 1, 2)
        rows = [self.funding(day, 8, 0.0001), self.funding(day, 16, 0.0002), self.funding(next_day, 0, 0.0003)]
        [point] = bybit.parse_funding(rows)
        self.assertEqual(point.date, day)
        self.assertAlmostEqual(point.value, 0.0002)

    def test_partial_day_is_dropped(self):
        self.assertEqual(bybit.parse_funding([self.funding(D(2025, 1, 1), 8, 0.0001)]), [])

    def test_snapshots_use_their_own_day(self):
        rows = [{"timestamp": str(ms(D(2025, 1, 3))), "openInterest": "62000"}]
        self.assertEqual(bybit.parse_snapshots(rows, "openInterest", "open_interest"),
                         [Point(D(2025, 1, 3), "open_interest", 62000.0)])

    def test_windows_cover_the_whole_range_without_overlap(self):
        chunks = list(bybit.windows(D(2025, 1, 1), D(2025, 4, 1)))
        self.assertEqual(chunks[0][0], ms(D(2025, 1, 1)))
        self.assertEqual(chunks[-1][1], ms(D(2025, 4, 2)) - 1)
        for (_, end), (start, _) in zip(chunks, chunks[1:]):
            self.assertEqual(start, end + 1)


class OkxLiquidationTests(SimpleTestCase):
    def order(self, day, hour, side, size, price=100_000):
        return {"ts": str(ms(day, hour)), "posSide": side, "sz": str(size), "bkPx": str(price)}

    def test_only_complete_days_are_summed(self):
        details = [
            self.order(D(2026, 7, 1), 20, "long", 10),  # oldest day: cut off, dropped
            self.order(D(2026, 7, 2), 1, "long", 10),
            self.order(D(2026, 7, 2), 5, "long", 5),
            self.order(D(2026, 7, 2), 6, "short", 1),
        ]
        points = okx_liquidations.parse_liquidations(details, D(2026, 7, 1), D(2026, 7, 2))
        self.assertEqual(points, [
            Point(D(2026, 7, 2), "long_liquidations_usd", 15_000.0),
            Point(D(2026, 7, 2), "short_liquidations_usd", 1_000.0),
        ])


class YahooTests(SimpleTestCase):
    def test_closes_are_dated_by_new_york_session(self):
        # 2026-07-01 09:30 New York is 13:30 UTC.
        stamp = int(datetime.datetime(2026, 7, 1, 13, 30, tzinfo=datetime.UTC).timestamp())
        result = {"meta": {"gmtoffset": -14400}, "timestamp": [stamp, stamp + 86400],
                  "indicators": {"quote": [{"close": [101.5, None]}]}}
        self.assertEqual(yahoo.parse_chart(result, "dxy_close"), [Point(D(2026, 7, 1), "dxy_close", 101.5)])


class FredTests(SimpleTestCase):
    def test_daily_values_are_shifted_one_day_and_gaps_skipped(self):
        rows = [{"date": "2026-07-01", "value": "4.33"}, {"date": "2026-07-02", "value": "."}]
        self.assertEqual(fred.parse_daily(rows, "fed_funds_effective"),
                         [Point(D(2026, 7, 2), "fed_funds_effective", 4.33)])

    def test_monthly_value_is_dated_by_its_release(self):
        rows = [{"date": "2026-06-01", "value": "320.1"}, {"date": "2026-07-01", "value": "321.0"}]
        releases = [D(2026, 6, 11), D(2026, 7, 15)]
        # June's CPI comes out on July 15; July's has no release yet so it is left out.
        self.assertEqual(fred.parse_monthly(rows, releases, "cpi"), [Point(D(2026, 7, 15), "cpi", 320.1)])

    @override_settings(FRED_API_KEY="")
    def test_missing_key_is_a_clear_error(self):
        with self.assertRaisesMessage(CollectorError, "FRED_API_KEY"):
            fred.collect(D(2026, 7, 1), D(2026, 7, 2))


class EtfFlowTests(SimpleTestCase):
    CSV = [
        "Date,IBIT,FBTC,Total",
        "01 Jul 2026,100.0,(20.5),79.5",
        "02 Jul 2026,-,-,\"(1,234.0)\"",
        "03 Jul 2026,-,-,-",
        "Total,,,1000",
    ]

    def test_flows_parse_brackets_as_outflows_dated_the_next_day(self):
        # A trading day's flows are complete only after the US close.
        self.assertEqual(etf_flows.parse_csv(self.CSV), [
            Point(D(2026, 7, 2), "etf_net_flow_musd", 79.5),
            Point(D(2026, 7, 3), "etf_net_flow_musd", -1234.0),
        ])

    def test_csv_without_total_column_is_rejected(self):
        with self.assertRaises(CollectorError):
            etf_flows.parse_csv(["Date,IBIT", "01 Jul 2026,1"])


class RepositoryTests(TestCase):
    def test_saving_twice_updates_instead_of_duplicating(self):
        market_data_repository.save_points("binance", [Point(D(2026, 7, 1), "close", 1.0)])
        market_data_repository.save_points("binance", [Point(D(2026, 7, 1), "close", 2.0)])
        self.assertEqual(MarketData.objects.get().value, 2.0)


class CollectionServiceTests(TestCase):
    def test_one_failing_source_does_not_stop_others(self):
        fake_ok = mock.Mock(collect=mock.Mock(return_value=[Point(D(2026, 7, 1), "close", 1.0)]))
        fake_bad = mock.Mock(collect=mock.Mock(side_effect=CollectorError("down")))
        with mock.patch.dict(collection_service.COLLECTORS, {"binance": fake_ok, "yahoo": fake_bad}, clear=True):
            result = collection_service.collect(D(2026, 7, 1), D(2026, 7, 1))
        self.assertEqual(result.saved, {"binance": 1})
        self.assertEqual(result.errors, {"yahoo": "down"})

    def test_missing_days_for_crypto_counts_weekends(self):
        days = [D(2026, 7, 1), D(2026, 7, 2), D(2026, 7, 5)]  # Fri 3rd and Sat 4th missing
        market_data_repository.save_points("binance", [Point(day, "close", 1.0) for day in days])
        gaps = collection_service.missing_days(D(2026, 7, 1), D(2026, 7, 5), ["binance"])
        self.assertEqual(gaps, {("binance", "close"): [D(2026, 7, 3), D(2026, 7, 4)]})

    def test_missing_days_for_markets_ignores_weekends(self):
        days = [D(2026, 7, 2), D(2026, 7, 3), D(2026, 7, 6)]  # Thu, Fri, Mon
        market_data_repository.save_points("yahoo", [Point(day, "dxy_close", 1.0) for day in days])
        self.assertEqual(collection_service.missing_days(D(2026, 7, 1), D(2026, 7, 6), ["yahoo"]), {})

    def test_fred_business_days_are_expected_one_day_late(self):
        days = [D(2026, 7, 3), D(2026, 7, 4), D(2026, 7, 7)]  # Thu, Fri, Mon values dated Fri, Sat, Tue
        market_data_repository.save_points("fred", [Point(day, "treasury_2y", 3.5) for day in days])
        self.assertEqual(collection_service.missing_days(D(2026, 7, 3), D(2026, 7, 7), ["fred"]), {})
