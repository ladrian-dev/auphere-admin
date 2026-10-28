import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { TodayDate } from "../today-date";

/**
 * Prototipo aprobado: «Ladrian Studio · lunes 26 de octubre» bajo el saludo. La
 * fecha es la del navegador (el partner puede estar en otra zona que el servidor).
 */
describe("TodayDate", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 26, 10, 0));
  });
  afterEach(() => vi.useRealTimers());

  it("dice el día de la semana y la fecha, sin año", () => {
    render(
      <LocaleProvider locale="es">
        <TodayDate />
      </LocaleProvider>,
    );
    expect(screen.getByText("lunes, 26 de octubre")).toBeInTheDocument();
  });

  it("en inglés", () => {
    render(
      <LocaleProvider locale="en">
        <TodayDate />
      </LocaleProvider>,
    );
    expect(screen.getByText("Monday, October 26")).toBeInTheDocument();
  });
});
