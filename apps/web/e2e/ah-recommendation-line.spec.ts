import { expect, test } from "@playwright/test";
import {
  ahRecommendationTeamLabel,
  formatAhMarketHandicap,
  formatAhRecommendationHandicap,
} from "../src/lib/pricingDisplay";

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
  // Market handicap preserves the home-perspective sign: negative = home gives,
  // positive = home receives. No inversion.
  expect(formatAhMarketHandicap("0.75")).toBe("+0.75");
  expect(formatAhMarketHandicap("-0.75")).toBe("-0.75");
  expect(formatAhMarketHandicap("0")).toBe("0");
  expect(formatAhMarketHandicap("2")).toBe("+2");
  expect(formatAhMarketHandicap(null)).toBeNull();
});

test("the handicap line names the team the line belongs to", () => {
  const home = "毕尔巴鄂竞技";
  const away = "埃尔切";

  // 2026-09-13 Athletic Club vs Elche: the away side received the 1.25 the
  // recommendation was settled on, so the line must read "埃尔切 +1.25" and
  // never be attachable to the home team.
  expect(`${ahRecommendationTeamLabel("AWAY", home, away)}${formatAhRecommendationHandicap("AWAY", "1.25")}`).toBe(
    "埃尔切 +1.25",
  );
  expect(`${ahRecommendationTeamLabel("HOME", home, away)}${formatAhRecommendationHandicap("HOME", "-1.25")}`).toBe(
    "毕尔巴鄂竞技 -1.25",
  );

  // Missing Chinese label falls back to the side, never to a bare sign.
  expect(ahRecommendationTeamLabel("AWAY", home, "")).toBe("客队 ");
  expect(ahRecommendationTeamLabel("HOME", null, away)).toBe("主队 ");

  // Non-AH markets keep their own wording.
  expect(ahRecommendationTeamLabel("OVER", home, away)).toBe("");
});

