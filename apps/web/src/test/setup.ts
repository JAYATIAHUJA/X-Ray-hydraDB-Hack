import "@testing-library/jest-dom/vitest";

const gradient = { addColorStop: () => undefined };
const context = {
  arc: () => undefined,
  beginPath: () => undefined,
  clearRect: () => undefined,
  createRadialGradient: () => gradient,
  fill: () => undefined,
  fillText: () => undefined,
  lineTo: () => undefined,
  measureText: (text: string) => ({ width: text.length * 7 }),
  moveTo: () => undefined,
  roundRect: () => undefined,
  setLineDash: () => undefined,
  setTransform: () => undefined,
  stroke: () => undefined
};

Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  configurable: true,
  value: () => context
});
Object.defineProperty(HTMLCanvasElement.prototype, "clientWidth", {
  configurable: true,
  get: () => 600
});
Object.defineProperty(HTMLCanvasElement.prototype, "clientHeight", {
  configurable: true,
  get: () => 400
});
HTMLCanvasElement.prototype.getBoundingClientRect = () => ({
  bottom: 400,
  height: 400,
  left: 0,
  right: 600,
  top: 0,
  width: 600,
  x: 0,
  y: 0,
  toJSON: () => ({})
});
HTMLCanvasElement.prototype.setPointerCapture = () => undefined;
