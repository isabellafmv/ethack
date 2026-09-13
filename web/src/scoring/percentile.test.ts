import { describe, expect, it } from "vitest";
import { median, percentileRank, universeRankPercentile, weightedMeanSkippingNulls } from "./percentile";

describe("percentileRank (sector_percentile: count(<=v)/n, mirrors _sector_percentile_vs_measured)", () => {
  it("ranks higher_is_better so the best value scores close to 100 and the worst scores 100/n", () => {
    const dist = [10, 20, 30, 40, 50];
    expect(percentileRank(50, dist, "higher_is_better")).toBe(100); // count(<=50)=5 -> 5/5=1 -> 100
    expect(percentileRank(10, dist, "higher_is_better")).toBe(20); // count(<=10)=1 -> 1/5=0.2 -> 20
    expect(percentileRank(30, dist, "higher_is_better")).toBe(60); // count(<=30)=3 -> 3/5=0.6 -> 60
  });

  it("inverts for lower_is_better so the smallest value scores highest, but not exactly 100", () => {
    const dist = [10, 20, 30, 40, 50];
    expect(percentileRank(10, dist, "lower_is_better")).toBe(80); // pct=0.2 -> 100*(1-0.2)
    expect(percentileRank(50, dist, "lower_is_better")).toBe(0); // pct=1 -> 100*(1-1)
  });

  it("a lone company in its sector counts as 100% <= itself: higher_is_better scores 100, lower_is_better scores 0", () => {
    expect(percentileRank(42, [42], "higher_is_better")).toBe(100);
    expect(percentileRank(42, [42], "lower_is_better")).toBe(0);
  });

  it("a tied block all shares the block's own upper-edge percentile, not an average", () => {
    const dist = [5, 5, 5, 5];
    expect(percentileRank(5, dist, "higher_is_better")).toBe(100); // count(<=5)=4 -> 4/4=1
  });

  it("returns null against an empty distribution -- nothing to rank against", () => {
    expect(percentileRank(42, [], "higher_is_better")).toBeNull();
  });

  it("returns null for a non-finite value", () => {
    expect(percentileRank(NaN, [1, 2, 3], "higher_is_better")).toBeNull();
  });
});

describe("universeRankPercentile (universe_percentile: pandas rank(pct=True, method='average'))", () => {
  it("ranks higher_is_better so the best value scores 100 and the worst scores 100/n", () => {
    const dist = [10, 20, 30, 40, 50];
    expect(universeRankPercentile(50, dist, "higher_is_better")).toBe(100);
    expect(universeRankPercentile(10, dist, "higher_is_better")).toBe(20);
    expect(universeRankPercentile(30, dist, "higher_is_better")).toBe(60);
  });

  it("a tied block shares the AVERAGE rank of the block, unlike percentileRank's upper edge", () => {
    const dist = [5, 5, 5, 5];
    // all four tie for ranks 1-4, average rank 2.5, pct = 2.5/4 = 0.625
    expect(universeRankPercentile(5, dist, "higher_is_better")).toBe(62.5);
  });

  it("a lone company scores 100 either way (avgRank=1, n=1)", () => {
    expect(universeRankPercentile(42, [42], "higher_is_better")).toBe(100);
    expect(universeRankPercentile(42, [42], "lower_is_better")).toBe(0);
  });

  it("returns null against an empty distribution", () => {
    expect(universeRankPercentile(42, [], "higher_is_better")).toBeNull();
  });

  it("returns null for a non-finite value", () => {
    expect(universeRankPercentile(NaN, [1, 2, 3], "higher_is_better")).toBeNull();
  });
});

describe("median", () => {
  it("averages the two middle values for an even-length list", () => {
    expect(median([1, 2, 3, 4])).toBe(2.5);
  });
  it("returns the middle value for an odd-length list", () => {
    expect(median([3, 1, 2])).toBe(2);
  });
  it("returns null for an empty list", () => {
    expect(median([])).toBeNull();
  });
});

describe("weightedMeanSkippingNulls", () => {
  it("computes a plain weighted mean when everything is present", () => {
    expect(
      weightedMeanSkippingNulls([
        { value: 10, weight: 1 },
        { value: 20, weight: 1 },
      ])
    ).toBe(15);
  });

  it("renormalises weights across only the non-null entries", () => {
    // A missing sub-score must not drag the aggregate toward zero -- its
    // weight is redistributed, not defaulted to a bad value.
    const result = weightedMeanSkippingNulls([
      { value: 100, weight: 1 },
      { value: null, weight: 1 },
    ]);
    expect(result).toBe(100);
  });

  it("returns null when nothing is available at all", () => {
    expect(
      weightedMeanSkippingNulls([
        { value: null, weight: 1 },
        { value: null, weight: 2 },
      ])
    ).toBeNull();
  });

  it("ignores a zero or negative weight even when the value is present", () => {
    const result = weightedMeanSkippingNulls([
      { value: 10, weight: 1 },
      { value: 999, weight: 0 },
    ]);
    expect(result).toBe(10);
  });
});
