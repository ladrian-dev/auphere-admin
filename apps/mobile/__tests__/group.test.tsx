import { fireEvent, render, screen } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { Group, Row } from "@/ui/group";

/**
 * Spec 042 (T005, R6.1, R6.2, R6.4, R4.7): the grouped list. One way to go
 * somewhere else, one way to leave the app, and a row that leads nowhere
 * looks like it.
 */
it("kind=push draws the chevron and responds", async () => {
  const onPress = jest.fn();
  await render(
    <Group>
      <Row label="Ver consumo" kind="push" onPress={onPress} />
    </Group>,
  );
  expect(screen.getByTestId("row-indicator-push")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Ver consumo" }));
  expect(onPress).toHaveBeenCalled();
});

it("kind=external draws the external-link icon and says where it leads", async () => {
  await render(
    <Group>
      <Row label="Abrir la consola web" hint="El detalle técnico y la exportación" kind="external" onPress={jest.fn()} />
    </Group>,
  );
  expect(screen.getByTestId("row-indicator-external")).toBeTruthy();
  expect(screen.getByText("El detalle técnico y la exportación")).toBeTruthy();
  expect(screen.getByRole("button", { name: /Abrir la consola web/ })).toBeTruthy();
});

it("without a kind there is no indicator and nothing to press (the absence is designed)", async () => {
  await render(
    <Group title="Dinero">
      <Row label="Saldo disponible" value="30,13 €" />
    </Group>,
  );
  expect(screen.queryByTestId("row-indicator-push")).toBeNull();
  expect(screen.queryByTestId("row-indicator-external")).toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.getByLabelText("Saldo disponible: 30,13 €")).toBeTruthy();
});

it("the shape and the action go together: onPress needs a kind", () => {
  // @ts-expect-error — a row that responds has to say how it looks (R6.1, R6.4).
  const row = <Row label="x" onPress={() => undefined} />;
  expect(row).toBeTruthy();
});

it("with large text the label and the value stack instead of being cut (R4.7)", async () => {
  const RN = require("react-native");
  const spy = jest.spyOn(RN, "useWindowDimensions");
  const directionAt = async (fontScale: number) => {
    spy.mockReturnValue({ width: 375, height: 667, scale: 2, fontScale });
    await render(
      <Group>
        <Row label="Gasto del mes" value="1.234,56 €" testID="row" />
      </Group>,
    );
    return StyleSheet.flatten(screen.getByTestId("row-body").props.style).flexDirection;
  };
  expect(await directionAt(1)).toBe("row");
  expect(await directionAt(2)).toBe("column");
  expect(screen.getByText("1.234,56 €").props.numberOfLines).toBeUndefined();
  spy.mockRestore();
});
