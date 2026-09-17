import { expect, test } from "@playwright/test";
import { translateCompetition } from "../src/lib/formatters";

test("new national league canonical labels resolve by competition_id", () => {
  expect(translateCompetition("Austrian Bundesliga", "austria_bundesliga")).toBe("奥甲");
  expect(translateCompetition("Bundesliga", "bundesliga")).toBe("德甲");
  expect(translateCompetition("2. Bundesliga", "germany_2_bundesliga")).toBe("德乙");
  expect(translateCompetition("Swiss Super League", "switzerland_super_league")).toBe("瑞士超");
  expect(translateCompetition("Scottish Premiership", "scotland_premiership")).toBe("苏超");
  expect(translateCompetition("Süper Lig", "turkey_super_lig")).toBe("土超");
  expect(translateCompetition("La Liga 2", "spain_segunda_division")).toBe("西乙");
});

test("austria_bundesliga must not resolve to the German Bundesliga label", () => {
  // 奥甲不得回落到「德甲」；德甲的 bundesliga 仍为「德甲」
  expect(translateCompetition("Austrian Bundesliga", "austria_bundesliga")).not.toBe("德甲");
  expect(translateCompetition("Bundesliga", "bundesliga")).toBe("德甲");
});

test("ambiguous English names are not added to the name-based fallback", () => {
  // 无 competition_id 时按英文名查表；ambiguous "Bundesliga"/"Super League" 不新增，
  // 因此奥地利/瑞士联赛无 canonical 时保持英文名，而非落到错误译名
  expect(translateCompetition("Austrian Bundesliga")).toBe("Austrian Bundesliga");
  expect(translateCompetition("Swiss Super League")).toBe("Swiss Super League");
});
