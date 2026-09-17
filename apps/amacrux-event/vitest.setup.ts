import "@testing-library/jest-dom/vitest";

if (typeof window !== "undefined") {
  window.scrollTo = () => {};
}

if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

// jsdom no implementa <dialog>; el componente Dialog usa showModal/close.
if (typeof HTMLDialogElement !== "undefined") {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & { showModal?: () => void; close?: () => void };
  if (!proto.showModal) proto.showModal = function () { this.setAttribute("open", ""); };
  if (!proto.close) proto.close = function () { this.removeAttribute("open"); };
}
