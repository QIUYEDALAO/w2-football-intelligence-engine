import { expect, test } from "@playwright/test";
import { formatAhMarketHandicap, formatAhRecommendationHandicap } from "../src/lib/pricingDisplay";

test("recommendations preserve the selected team's handicap sign", () => {
  for (const side of ["HOME", "AWAY"]) {
    expect(formatAhRecommendationHandicap(side, "0.75")).toBe("+0.75");
    expect(formatAhRecommendationHandicap(side, "-0.75")).toBe("-0.75");
    expect(formatAhRecommendationHandicap(side, "0")).toBe("0");
    expect(formatAhRecommendationHandicap(side, "1")).toBe("+1");
    expect(formatAhRecommendationHandicap(side, null)).toBeNull();
  }
  expect(formatAhRecommendationHandicap("UNKNOWN", "0.75")).toBeNull();
  expect(formatAhRecommendationHandicap("HOME", "invalid")).toBeNull();
  expect(formatAhMarketHandicap("0.75")).toBe("-0.75");
});
