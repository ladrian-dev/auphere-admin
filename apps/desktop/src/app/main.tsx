import { createRoot } from "react-dom/client";

import { App } from "./App";
import { ErrorBoundary } from "./feedback/error-boundary";
import "./styles.css";

// El armazón va **fuera** de `App`: si lo que lanza es el propio `App` al
// montar —que es el caso que más duele, porque deja la ventana en negro antes
// de que se vea nada— un boundary dentro de él no llegaría a existir.
createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
