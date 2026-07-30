import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

Object.defineProperty(window, "scrollTo", {
  value: () => undefined,
  writable: true,
});

Object.defineProperty(URL, "createObjectURL", {
  value: () => "blob:docintel-test",
  writable: true,
});

Object.defineProperty(URL, "revokeObjectURL", {
  value: () => undefined,
  writable: true,
});

Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  value: () => ({}),
  writable: true,
});
