import { describe, expect, it } from "vitest";

import { phoneProblem, validPhone } from "../phone";

/** Spec 064 (3.2): an international number, with its country prefix. */
describe("validPhone", () => {
  it.each(["+34600123456", "+34 600 123 456", "+56 (9) 1234-5678", "  +56911112222  ", "+12025550123"])("takes %s", (phone) => {
    expect(validPhone(phone)).toBe(true);
  });

  it.each([
    ["", "empty"],
    ["   ", "only spaces"],
    ["600123456", "no country prefix"],
    ["0034600123456", "a prefix written with zeros"],
    ["+34 600", "fewer than 8 digits"],
    ["+1234567890123456", "more than 15 digits"],
    ["+34 6oo 123 456", "letters"],
    ["+34+600123456", "a second plus"],
    ["+", "only the plus"],
  ])("refuses %j (%s)", (phone) => {
    expect(validPhone(phone)).toBe(false);
  });
});

/** Spec 064 (3.3, WCAG 3.3.3): the field says what is actually wrong. */
describe("phoneProblem", () => {
  it.each([
    ["", "required"],
    ["   ", "required"],
    ["600123456", "prefix"],
    ["0034600123456", "prefix"],
    ["+34 6oo 123 456", "chars"],
    ["+34+600123456", "chars"],
    ["+", "length"],
    ["+56 9 1234", "length"],
    ["+1234567890123456", "length"],
    ["+34 600 123 456", null],
  ])("%j → %s", (phone, problem) => {
    expect(phoneProblem(phone)).toBe(problem);
  });
});
