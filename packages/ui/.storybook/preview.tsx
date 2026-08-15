import type { Preview } from "@storybook/react-vite";
import * as React from "react";

import "./storybook.css";

const preview: Preview = {
  parameters: {
    layout: "padded",
    a11y: { test: "error" },
    backgrounds: { disable: true },
  },
  globalTypes: {
    theme: {
      description: "Theme",
      toolbar: { icon: "mirror", items: ["light", "dark"], dynamicTitle: true },
    },
  },
  initialGlobals: { theme: "light" },
  decorators: [
    (Story, ctx) => {
      React.useEffect(() => {
        document.documentElement.setAttribute("data-theme", String(ctx.globals.theme ?? "light"));
      }, [ctx.globals.theme]);
      return (
        <div className="min-h-screen bg-background p-6 text-foreground">
          <Story />
        </div>
      );
    },
  ],
};

export default preview;
