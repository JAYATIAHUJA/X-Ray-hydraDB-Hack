import "@testing-library/jest-dom/vitest";

// Node 22+ may leave localStorage undefined unless --localstorage-file is set.
const memoryStore = new Map<string, string>();
const localStorageMock: Storage = {
  get length() {
    return memoryStore.size;
  },
  clear() {
    memoryStore.clear();
  },
  getItem(key: string) {
    return memoryStore.has(key) ? memoryStore.get(key)! : null;
  },
  key(index: number) {
    return [...memoryStore.keys()][index] ?? null;
  },
  removeItem(key: string) {
    memoryStore.delete(key);
  },
  setItem(key: string, value: string) {
    memoryStore.set(key, String(value));
  }
};
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: localStorageMock
});

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
