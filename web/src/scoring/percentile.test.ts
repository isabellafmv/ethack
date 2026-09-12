import { describe, expect, it } from "vitest";
import { median, percentileRank, weightedMeanSkippingNulls } from "./percentile";

describe("percentileRank", () => {
  it("ranks higher_is_better so the best value scores 100 and the worst scores 0", () => {
    const dist = [10, 20, 30, 40, 50];
    expect(percentileRank(50, dist, "higher_is_better")).toBe(100);
    expect(percentileRank(10, dist, "higher_is_better")).toBe(0);
    expect(percentileRank(30, dist, "higher_is_better")).toBe(50); // the median sits at 50
  });

  it("inverts for lower_is_better so the smallest value scores 100", () => {
    const dist = [10, 20, 30, 40, 50];
    expect(percentileRank(10, dist, "lower_is_better")).toBe(100);
    expect(percentileRank(50, dist, "lower_is_better")).toBe(0);
  });

  it("a lone company in its sector is trivially both best and worst: scores 100", () => {
    expect(percentileRank(42, [42], "higher_is_better")).toBe(100);
    expect(percentileRank(42, [42], "lower_is_better")).toBe(100);
  });

  it("puts a value tied with the whole distribution at 50", () => {
    const dist = [5, 5, 5, 5];
    expect(percentileRank(5, dist, "higher_is_better")).toBe(50);
  });

  it("returns null against an empty distribution -- nothing to rank against", () => {
    expect(percentileRank(42, [], "higher_is_better")).toBeNull();
  });

  it("returns null for a non-finite value", () => {
    expect(percentileRank(NaN, [1, 2, 3], "higher_is_better")).toBeNull();
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
