#!/usr/bin/env python3
"""
Market value price analyzer.
Takes extracted prices and computes statistics + buy/pass recommendation.

Usage:
  echo '{"prices": [900, 950, 1059, 1100, 1300], "candidate_price": 950, "tax_rate": 0.1025, "shipping": 30}' | python3 analyze_prices.py
  python3 analyze_prices.py --prices '900,950,1059,1100,1300' --candidate 950 --tax 0.1025 --shipping 30
  python3 analyze_prices.py --prices '900,950,1059,1100,1300' --candidate 950 --tax 0.1025 --shipping 30 --max-loss 80
"""
import sys
import json
import argparse
import statistics


def analyze(prices: list[float], candidate_price: float | None = None,
            tax_rate: float = 0.0, shipping: float = 0.0,
            broker_fee: float = 0.0, max_loss: float | None = None,
            resale_fee_pct: float = 0.13) -> dict:
    """Analyze market prices and optionally evaluate a candidate purchase."""
    if not prices:
        return {"error": "No prices provided"}

    prices_sorted = sorted(prices)
    n = len(prices_sorted)

    # Basic stats
    result = {
        "count": n,
        "min": prices_sorted[0],
        "max": prices_sorted[-1],
        "mean": round(statistics.mean(prices_sorted), 2),
        "median": round(statistics.median(prices_sorted), 2),
    }

    if n >= 2:
        result["stdev"] = round(statistics.stdev(prices_sorted), 2)

    # Percentiles (interpolated)
    if n >= 4:
        p25_idx = (n - 1) * 0.25
        p75_idx = (n - 1) * 0.75
        lo, hi = int(p25_idx), int(p25_idx) + 1
        result["p25"] = round(prices_sorted[lo] + (prices_sorted[min(hi, n-1)] - prices_sorted[lo]) * (p25_idx - lo), 2)
        lo, hi = int(p75_idx), int(p75_idx) + 1
        result["p75"] = round(prices_sorted[lo] + (prices_sorted[min(hi, n-1)] - prices_sorted[lo]) * (p75_idx - lo), 2)

    # Market value ranges
    result["market_range"] = {
        "low": result.get("p25", prices_sorted[0]),
        "mid": result["median"],
        "high": result.get("p75", prices_sorted[-1]),
    }

    # Candidate evaluation
    if candidate_price is not None:
        all_in = candidate_price + shipping + broker_fee
        if tax_rate > 0:
            all_in += candidate_price * tax_rate
        all_in = round(all_in, 2)

        # Expected resale (median minus platform fees)
        expected_resale_gross = result["median"]
        expected_resale_net = round(expected_resale_gross * (1 - resale_fee_pct), 2)

        potential_loss = round(all_in - expected_resale_net, 2)

        eval_result = {
            "candidate_price": candidate_price,
            "tax": round(candidate_price * tax_rate, 2),
            "shipping": shipping,
            "broker_fee": broker_fee,
            "all_in": all_in,
            "expected_resale_gross": expected_resale_gross,
            "resale_fee_pct": resale_fee_pct,
            "expected_resale_net": expected_resale_net,
            "potential_loss": potential_loss,
        }

        # Recommendation
        if all_in <= result["market_range"]["low"]:
            eval_result["verdict"] = "GREAT_BUY"
            eval_result["reason"] = f"All-in ${all_in} is at or below P25 (${result['market_range']['low']})"
        elif all_in <= result["median"]:
            eval_result["verdict"] = "GOOD_BUY"
            eval_result["reason"] = f"All-in ${all_in} is below median (${result['median']})"
        elif all_in <= result["market_range"]["high"]:
            eval_result["verdict"] = "MARKET_RATE"
            eval_result["reason"] = f"All-in ${all_in} is between median and P75 — no resale cushion"
        else:
            eval_result["verdict"] = "OVERPAY"
            eval_result["reason"] = f"All-in ${all_in} exceeds P75 (${result['market_range']['high']})"

        # Max loss check
        if max_loss is not None:
            eval_result["max_loss_limit"] = max_loss
            if potential_loss > max_loss:
                eval_result["verdict"] = "PASS"
                eval_result["reason"] = f"Potential loss ${potential_loss} exceeds max acceptable loss ${max_loss}"
            eval_result["within_loss_limit"] = potential_loss <= max_loss

        # Suggested max bid (work backward from median resale net + acceptable loss)
        if max_loss is not None:
            max_all_in = expected_resale_net + max_loss
            if tax_rate > 0:
                max_bid = (max_all_in - shipping - broker_fee) / (1 + tax_rate)
            else:
                max_bid = max_all_in - shipping - broker_fee
            eval_result["suggested_max_bid"] = round(max_bid, 2)
            eval_result["suggested_max_all_in"] = round(max_all_in, 2)

        result["evaluation"] = eval_result

    return result


def main():
    parser = argparse.ArgumentParser(description="Analyze market value from comparable prices")
    parser.add_argument("--prices", type=str, help="Comma-separated prices")
    parser.add_argument("--candidate", type=float, help="Candidate purchase price")
    parser.add_argument("--tax", type=float, default=0.0, help="Tax rate (e.g. 0.1025 for 10.25%%)")
    parser.add_argument("--shipping", type=float, default=0.0, help="Shipping cost")
    parser.add_argument("--broker-fee", type=float, default=0.0, help="Broker/handling fee")
    parser.add_argument("--max-loss", type=float, help="Max acceptable loss on resale")
    parser.add_argument("--resale-fee", type=float, default=0.13, help="Platform resale fee %% (default 13%% for eBay)")
    args = parser.parse_args()

    # Try CLI args first, then stdin JSON
    if args.prices:
        prices = [float(p.strip()) for p in args.prices.split(",") if p.strip()]
        result = analyze(
            prices=prices,
            candidate_price=args.candidate,
            tax_rate=args.tax,
            shipping=args.shipping,
            broker_fee=args.broker_fee,
            max_loss=args.max_loss,
            resale_fee_pct=args.resale_fee,
        )
    else:
        data = json.load(sys.stdin)
        result = analyze(
            prices=data["prices"],
            candidate_price=data.get("candidate_price"),
            tax_rate=data.get("tax_rate", 0.0),
            shipping=data.get("shipping", 0.0),
            broker_fee=data.get("broker_fee", 0.0),
            max_loss=data.get("max_loss"),
            resale_fee_pct=data.get("resale_fee_pct", 0.13),
        )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
