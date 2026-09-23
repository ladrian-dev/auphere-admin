import { renderToStaticMarkup } from "react-dom/server";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";

import { Checkbox } from "../checkbox";
import { Form, FormControl, FormField, FormItem, FormLabel } from "../form";

function Fixture() {
  const form = useForm<{ on: boolean }>({ defaultValues: { on: true } });
  return (
    <Form {...form}>
      <FormField
        control={form.control}
        name="on"
        render={({ field }) => (
          <FormItem>
            <FormControl>
              <Checkbox checked={field.value} onCheckedChange={(c) => field.onChange(c)} />
            </FormControl>
            <FormLabel>Permitir escalar a una persona</FormLabel>
          </FormItem>
        )}
      />
    </Form>
  );
}

describe("FormControl + a non-native control (Base UI checkbox)", () => {
  it("names the control in the server-rendered HTML, before hydration", () => {
    // axe ``aria-toggle-field-name`` (serious) fired on /tools and
    // /agent/settings whenever it scanned before React hydrated: the
    // <span role="checkbox"> only got its aria-labelledby client-side.
    const html = renderToStaticMarkup(<Fixture />);
    const control = /<span[^>]*role="checkbox"[^>]*>/.exec(html)?.[0];
    expect(control).toBeDefined();
    const labelledby = /aria-labelledby="([^"]+)"/.exec(control!)?.[1];
    expect(labelledby).toBeTruthy();
    expect(html).toContain(`id="${labelledby}"`);
    expect(html).toContain("Permitir escalar a una persona</label>");
  });
});
